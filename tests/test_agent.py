import json
import unittest
import tempfile
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
import config
from data.seed import build_db
from target.agent import Agent
from target import providers


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db, self.trace = config.DB_PATH, config.TRACE_DIR
        config.DB_PATH = Path(self.tmp.name) / "test.db"
        config.TRACE_DIR = Path(self.tmp.name) / "trace"
        build_db()
        providers.clear_mutations()
        self.agent = Agent(providers.MockProvider())

    def tearDown(self):
        config.DB_PATH, config.TRACE_DIR = self.db, self.trace
        providers.clear_mutations()
        self.tmp.cleanup()

    def test_multiturn_and_trace_contract(self):
        results = [self.agent.chat("S", msg) for msg in ["查明天上海到杭州的高铁", "我要买一张", "支付", "帮我退掉", "查我的订单"]]
        self.assertEqual([r["tool_sequence"] for r in results], [["query_tickets"], ["query_tickets", "lock_seat", "create_order"], ["pay_order"], ["cancel_order"], ["query_order"]])
        saved = [json.loads(line) for line in (config.TRACE_DIR / "traces.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(saved, results)
        for r in results:
            self.assertEqual(set(r), {"session_id", "provider", "model", "user_msg", "steps", "tool_sequence", "reply", "finish_reason", "tokens", "total_latency_ms"})
            self.assertEqual(r["finish_reason"], "stop")
            self.assertTrue(all(c["ok"] for s in r["steps"] for c in s["calls"]))
        self.agent.reset("S")
        self.assertEqual(self.agent.chat("S", "支付")["tool_sequence"], [])

    def test_six_injected_mutations(self):
        normal = self.agent.chat("normal", "查明天上海到杭州的高铁")
        providers.set_mutation("date_offset", 1)
        offset = self.agent.chat("offset", "查明天上海到杭州的高铁")
        self.assertNotEqual(normal["steps"][0]["calls"][0]["args"]["date"], offset["steps"][0]["calls"][0]["args"]["date"])
        providers.clear_mutations()
        providers.set_mutation("skip_lock")
        skipped = self.agent.chat("skip", "订明天上海到杭州的高铁")
        self.assertEqual(skipped["tool_sequence"], ["query_tickets", "create_order"])
        self.assertFalse(skipped["steps"][-1]["calls"][0]["ok"])
        providers.clear_mutations()
        providers.set_mutation("repeat_call")
        self.assertEqual(self.agent.chat("repeat", "查明天上海到杭州的高铁")["tool_sequence"], ["query_tickets"] * 2)
        providers.clear_mutations()
        providers.set_mutation("infinite_loop")
        loop = self.agent.chat("loop", "抢明天北京到上海的票")
        self.assertEqual(loop["finish_reason"], "max_steps_exceeded")
        self.assertEqual(loop["tool_sequence"], ["query_tickets"] + ["monitor_seat"] * (config.MAX_STEPS - 1))
        providers.clear_mutations()
        providers.set_mutation("route_error")
        self.assertEqual(self.agent.chat("route", "退票手续费怎么算")["tool_sequence"], ["query_tickets"])
        providers.clear_mutations()
        providers.set_mutation("no_citation")
        self.assertNotRegex(self.agent.chat("cite", "退票手续费怎么算")["reply"], r"P\d+")
        providers.clear_mutations()
        self.assertRegex(self.agent.chat("clean", "退票手续费怎么算")["reply"], r"P01")

    def test_monitor_seat_and_flight(self):
        wait = self.agent.chat("wait", "抢明天北京到上海的票")
        self.assertEqual(wait["tool_sequence"], ["query_tickets", "monitor_seat"])
        self.assertEqual(wait["finish_reason"], "stop")
        flight = self.agent.chat("flight", "订后天北京到成都的机票并支付")
        self.assertEqual(flight["tool_sequence"], ["query_tickets", "lock_seat", "create_order", "pay_order"])
        self.assertTrue(all(c["ok"] for s in flight["steps"] for c in s["calls"]))

    def test_errors_dates_and_sessions(self):
        self.assertEqual(providers._parse_date("2026-10-21"), "2026-10-21")
        with patch("config.today", return_value=__import__("datetime").date(2026,10,12)):
            self.assertEqual(providers._parse_date("下周三"), "2026-10-21")
        class Broken:
            name = "mock"
            def chat(self, *args):
                raise RuntimeError("sensitive detail must not be echoed")
        r = Agent(Broken()).chat("broken", "你好")
        self.assertEqual(r["finish_reason"], "stop")
        self.assertNotIn("sensitive detail", r["reply"])
        with self.assertRaises(ValueError):
            self.agent.chat("", "")
        self.assertEqual(self.agent.chat("new", "支付")["tool_sequence"], [])


if __name__ == "__main__":
    unittest.main()
