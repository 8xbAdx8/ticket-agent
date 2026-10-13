"""成员 A 前端自测：卡片与业务事实一致，回放/交互不重复执行。"""
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import config
from data.seed import build_db
from target import mock_core
from streamlit.testing.v1 import AppTest
from web.presentation import ticket_cards, order_card, policy_cards, collect_results


class LiveUIBase:
    engine = "legacy"

    def setUp(self):
        if self.engine == "langchain":
            try:
                import langchain
            except ImportError:
                self.skipTest("原 V2 环境没有 LangChain，框架 UI 在 V3 环境验证")
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = patch.multiple(config, DB_PATH=Path(self.tmp.name)/"tickets.db",
            TRACE_DIR=Path(self.tmp.name)/"traces", ENGINE=self.engine, LC_TOOLSET="all",
            PROVIDER="mock", USE_HTTP_MOCK=False, USE_VECTOR_RAG=False, MAX_STEPS=8)
        self.settings.start()
        build_db()
        self.app = AppTest.from_file(str(config.BASE_DIR/"web/app.py"), default_timeout=30).run()
        self.assertEqual(len(self.app.exception), 0)

    def tearDown(self):
        if hasattr(self, "settings"):
            self.settings.stop()
            self.tmp.cleanup()
        mock_core.clear_faults()

    def button(self, label):
        return next(b for b in self.app.button if b.label == label)

    def send(self, message):
        self.app.text_input[0].set_value(message)
        self.button("发送").click().run()
        self.assertEqual(len(self.app.exception), 0)
        return self.app.session_state["history"][-1], self.app.session_state["business_results"][-1]

    def traces(self):
        return [json.loads(x) for x in (config.TRACE_DIR/"traces.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_cards_match_full_tool_results_and_no_extra_calls(self):
        record, results = self.send("查明天上海到杭州的高铁")
        self.assertEqual(record["tool_sequence"], ["query_tickets"])
        self.assertEqual(set(record), {"session_id", "provider", "model", "user_msg", "steps", "tool_sequence", "reply", "finish_reason", "tokens", "total_latency_ms"})
        for call in record["steps"][0]["calls"]:
            self.assertEqual(set(call), {"tool", "args", "ok", "latency_ms", "result_preview"})
        self.assertTrue(record["steps"][0]["calls"][0]["result_preview"].endswith("..."))
        trains = results[0]["result"]["trains"]
        self.assertEqual(trains, mock_core.query_tickets("上海", "杭州", (config.today()+timedelta(days=1)).isoformat(), "二等座", "高铁")["trains"])
        markup = "\n".join(m.value for m in self.app.markdown)
        self.assertEqual(markup.count('class="ticket-card"'), len(trains))
        self.assertIn(trains[-1]["train_no"], markup)
        self.app.run()  # 查看参数/切换页签只是重绘，不执行 chat。
        self.assertEqual(len(self.traces()), 1)
        self.assertEqual(self.traces()[0], record)

    def test_order_policy_payment_and_clear(self):
        order, results = self.send("订明天上海到杭州的高铁")
        self.assertEqual(order["tool_sequence"], ["query_tickets", "lock_seat", "create_order"])
        created = results[-1]["result"]
        self.assertEqual(created["status"], "pending")
        self.assertIn(created["order_id"], "\n".join(m.value for m in self.app.markdown))
        policy, results = self.send("锁座后多久必须完成支付？")
        self.assertEqual(policy["tool_sequence"], ["search_policy"])
        selector = next(s for s in self.app.selectbox if s.label == "工具参数与结果")
        self.assertEqual(selector.options, ["1. search_policy"])
        self.assertTrue(any(h["doc_id"] == "P11" for h in results[0]["result"]["hits"]))
        _, paid = self.send("支付我刚才的订单")
        self.assertEqual(paid[-1]["result"]["status"], "paid")
        _, duplicate = self.send("支付我刚才的订单")
        self.assertTrue(duplicate[-1]["result"]["duplicate_pay"])
        self.assertIn("本次没有重复扣款", "\n".join(m.value for m in self.app.markdown))
        self.assertEqual(len(self.traces()), 4)
        previous_sid = self.app.session_state["sid"]
        self.button("清空会话").click().run()
        self.assertNotEqual(previous_sid, self.app.session_state["sid"])
        self.assertEqual(self.app.session_state["history"], [])
        self.assertEqual(self.app.session_state["business_results"], [])
        self.assertEqual(len(self.traces()), 4)
        self.assertTrue(any(s.label == "选择回放记录" for s in self.app.selectbox))

    def test_failure_does_not_show_ticket_cards(self):
        self.send("查明天上海到杭州的高铁")
        mock_core.set_fault("query_tickets", "error")
        record, results = self.send("查明天上海到杭州的高铁")
        self.assertTrue(any(not c["ok"] for s in record["steps"] for c in s["calls"]))
        self.assertTrue(all(not r["ok"] for r in results))
        markup = "\n".join(m.value for m in self.app.markdown)
        self.assertNotIn('class="ticket-card"', markup)
        self.assertNotIn('class="ticket-agent-processing"', markup)
        self.assertGreater(len(self.app.error), 0)

    def test_chat_exception_does_not_present_previous_turn_as_new_result(self):
        self.send("查明天上海到杭州的高铁")
        agent = self.app.session_state["agent"]
        with patch.object(agent, "chat", side_effect=RuntimeError("test-only error")):
            self.app.text_input[0].set_value("查询另一条路线")
            self.button("发送").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(len(self.app.session_state["history"]), 1)
        markup = "\n".join(m.value for m in self.app.markdown)
        self.assertNotIn('class="ticket-card"', markup)
        self.assertNotIn('class="ticket-agent-processing"', markup)
        self.assertGreater(len(self.app.error), 0)


class LegacyLiveUITests(LiveUIBase, unittest.TestCase):
    pass


class LangChainLiveUITests(LiveUIBase, unittest.TestCase):
    engine = "langchain"


class PresentationSafetyTests(unittest.TestCase):
    def test_initialization_failure_still_allows_trace_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            record = {"session_id": "old", "user_msg": "旧记录", "tool_sequence": [], "finish_reason": "stop"}
            (folder/"traces.jsonl").write_text(json.dumps(record), encoding="utf-8")
            with patch.object(config, "TRACE_DIR", folder), patch("target.agent.Agent", side_effect=ValueError("test-only unavailable provider")):
                app = AppTest.from_file(str(config.BASE_DIR/"web/app.py"),default_timeout=20).run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(next(b for b in app.button if b.label=="发送").disabled)
            self.assertTrue(any(s.label=="选择回放记录" for s in app.selectbox))
            self.assertGreater(len(app.json), 0)

    def test_untrusted_tool_text_is_escaped(self):
        malicious = '<img src=x onerror="alert(1)">'
        for markup in (ticket_cards({"trains": [{"train_no": malicious, "seats_left": 0}]}),
                       order_card({"order_id": malicious, "status": "pending"}),
                       policy_cards({"hits": [{"content": malicious}]})):
            self.assertNotIn("<img", markup)
            self.assertIn("&lt;img", markup)

    def test_mismatched_full_result_is_not_presented(self):
        from types import SimpleNamespace
        agent = SimpleNamespace(langchain_engine=SimpleNamespace(last_events=[
            {"event": "tool_end", "tool": "query_tickets", "result": {"trains": []}}]))
        self.assertEqual(collect_results(agent, "s", 0, {"steps": [{"calls": [{"tool": "pay_order", "ok": True}]}]}), [])


if __name__ == "__main__":
    unittest.main()
