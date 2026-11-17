"""A 的 DEF-06/07 定向离线回归；不更改 B 的正式用例或判据。"""
import json
import unittest
from unittest.mock import patch

from target import tools
from target.deepseek_runtime import DeepSeekError, validate_read_only_reply
from target.write_authorization import permissions, purchase_clarification
import test_langchain_orders as fixtures
import test_deepseek_agent as sdk_fixtures


class ReadOnlySubjectTests(unittest.TestCase):
    def test_policy_explanations_are_allowed(self):
        for text in (
            "政策规定锁座后需在 15 分钟内办理支付。",
            "订单需要在15分钟内完成支付。",
            "超时后系统会自动释放库存。",
            "政策规定锁座后需在15分钟内办理支付，超时自动释放库存。",
            "我可以为您解释支付政策。",
            "我来说明退票规则。",
        ):
            with self.subTest(text=text):
                validate_read_only_reply(text)

    def test_external_channels_are_allowed(self):
        for text in (
            "我无法为您办理退票，您可以通过12306官方渠道办理退票。",
            "我不能替您操作，您可以前往官方渠道办理。",
            "如需退票，请通过官方渠道办理。",
            "您可联系航空公司官方渠道办理退票。",
        ):
            with self.subTest(text=text):
                validate_read_only_reply(text)

    def test_own_promises_and_completion_are_rejected(self):
        for text in (
            "我可以为您办理退票", "我来帮您办理退票", "我将为您锁座",
            "我可以帮您支付", "已为您办理退票", "我已经帮您锁座成功",
            "我来帮您锁座", "我们能够替你支付", "本助手可以为您下单",
            "我可以通过12306官方渠道帮您办理退票。",
            "我无法办理退票但我将为您锁座。",
            "我不能付款，我可以帮你下单。",
            "您可以下单。", "是否需要支付？", "需要我帮您办理订票吗？",
            "需要我帮您进一步查询其他席别或办理订票吗？（订票需先锁座，且支付需您明确授权）",
            "需要我通过12306官方渠道帮您办理退票吗？",
        ):
            with self.subTest(text=text), self.assertRaisesRegex(DeepSeekError, "read_only_capability_violation"):
                validate_read_only_reply(text)

    def test_denials_are_allowed(self):
        for text in ("我无法为您执行退票。", "当前不能替您锁座。", "我不能直接为您支付。"):
            with self.subTest(text=text):
                validate_read_only_reply(text)


class PurchaseIntentTests(unittest.TestCase):
    def test_purchase_intent_is_separate_from_lock_authorization(self):
        for text in ("我要买一张，不要锁座直接下单", "我要买一张，不要锁座", "帮我订票，先不锁定座位"):
            with self.subTest(text=text):
                granted = permissions(text)
                self.assertIn("create_order", granted)  # 意图保留，业务前置条件另行检查。
                self.assertNotIn("lock_seat", granted)
                self.assertIn("必须先锁座", purchase_clarification(text))
        self.assertEqual(permissions("不要买了"), set())
        self.assertIn("已停止", purchase_clarification("不要买了"))
        self.assertIn("lock_seat", permissions("好，那就先锁座吧"))
        self.assertNotIn("create_order", permissions("可以，先锁座吧"))
        self.assertIsNone(purchase_clarification("订明天上海到杭州的票，不要支付"))


@unittest.skipUnless(sdk_fixtures.AVAILABLE, "需要 DeepSeek SDK；只用 MockTransport")
class ReadOnlySDKReplayTests(unittest.TestCase):
    setUp = sdk_fixtures.DeepSeekAgentTests.setUp
    tearDown = sdk_fixtures.DeepSeekAgentTests.tearDown
    agent = sdk_fixtures.DeepSeekAgentTests.agent
    response = sdk_fixtures.DeepSeekAgentTests.response

    def test_policy_final_text_is_not_replaced(self):
        raw = "政策规定锁座后需在15分钟内办理支付。"
        agent = self.agent([self.response({"content":raw})])
        result = agent.chat("policy", "解释政策")
        self.assertEqual(result["reply"], raw)
        self.assertEqual(result["tool_sequence"], [])
        self.assertEqual(agent.langchain_engine.last_events[-2]["text"], raw)

    def test_external_channel_final_text_is_not_replaced(self):
        raw = "我无法为您办理退票，您可以通过12306官方渠道办理退票。"
        result = self.agent([self.response({"content":raw})]).chat("external", "能退票吗")
        self.assertEqual(result["reply"], raw)
        self.assertEqual(result["tool_sequence"], [])


@unittest.skipUnless(fixtures.AVAILABLE, "需要 LangChain 离线环境")
class PurchaseFlowTests(unittest.TestCase):
    setUp = fixtures.LangChainOrderTests.setUp
    tearDown = fixtures.LangChainOrderTests.tearDown
    chat = fixtures.LangChainOrderTests.chat
    row = fixtures.LangChainOrderTests.row

    def test_conflict_clarifies_before_model_or_tools_and_preserves_context(self):
        self.chat("帮我查明天上海到杭州的高铁")
        before = self.row()["seats_left"]
        with patch.object(tools, "dispatch", wraps=tools.dispatch) as dispatch:
            result = self.chat("我要买一张，不要锁座直接给我下单")
        dispatch.assert_not_called()
        self.assertEqual(result["tool_sequence"], [])
        self.assertEqual(result["steps"], [])
        self.assertIn("购买意图", result["reply"])
        self.assertIn("必须先锁座", result["reply"])
        self.assertIn("是否同意", result["reply"])
        self.assertEqual(result["tokens"], {"prompt":0, "completion":0})
        self.assertEqual(self.row()["seats_left"], before)
        events = self.agent.langchain_engine.last_events
        self.assertEqual([e["event"] for e in events], ["authorization_clarification"])
        # 当前轮原始消息和澄清都进入框架记忆；下一轮明确同意后才执行。
        result = self.chat("好，那就先锁座吧")
        self.assertEqual(result["tool_sequence"], ["query_tickets", "lock_seat"])
        self.assertTrue(all(c["ok"] for s in result["steps"] for c in s["calls"]))
        self.assertEqual(self.row()["seats_left"], before-1)
        from target import mock_core
        self.assertEqual(mock_core.query_order()["count"], 0)
        inputs = self.agent.provider.received_messages[-1]
        self.assertTrue(any(m.content == "我要买一张，不要锁座直接给我下单" for m in inputs))
        self.assertTrue(any("必须先锁座" in str(m.content) for m in inputs))
        with open(fixtures.config.TRACE_DIR/"traces.jsonl", encoding="utf-8") as stream:
            traces = [json.loads(line) for line in stream]
        self.assertEqual(traces[-2]["tool_sequence"], [])
        self.assertEqual(traces[-1], result)

    def test_declined_purchase_does_not_call_model_or_tools(self):
        self.chat("查明天上海到杭州的高铁")
        with patch.object(tools, "dispatch", wraps=tools.dispatch) as dispatch:
            result = self.chat("不要买了")
        dispatch.assert_not_called()
        self.assertEqual(result["tool_sequence"], [])
        self.assertIn("已停止", result["reply"])

    def test_lock_only_confirmation_does_not_authorize_create_or_pay(self):
        self.chat("查明天上海到杭州的高铁")
        result = self.chat("可以，先锁座吧")
        self.assertEqual(result["tool_sequence"], ["query_tickets", "lock_seat"])
        self.assertIn("未下单、未支付", result["reply"])

    def test_readonly_mode_does_not_offer_to_purchase(self):
        from target.agent import Agent
        with patch.object(fixtures.config, "LC_TOOLSET", "read_only"):
            agent = Agent(engine="langchain")
        result = self.chat("我要买一张，不要锁座直接下单", agent)
        self.assertNotIn("是否同意先锁座", result["reply"])
        self.assertNotIn("lock_seat", result["tool_sequence"])
        self.assertNotIn("create_order", result["tool_sequence"])

    def test_lock_confirmation_without_route_requests_missing_conditions(self):
        self.chat("我要买一张，不要锁座直接下单")
        result = self.chat("好，那就先锁座吧")
        self.assertEqual(result["tool_sequence"], [])
        self.assertIn("出发地", result["reply"])


if __name__ == "__main__":
    unittest.main()
