"""ChatOpenAI SDK 边界桩验证：没有远端请求，不是真实模型结果。"""
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import config
from data.seed import build_db
from target.agent import Agent
from target import providers
try:
    import langchain_openai
    AVAILABLE = True
except ModuleNotFoundError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE,"LangChain 仅安装在独立 V3 环境")
class LangChainLiveAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(config,"DB_PATH",Path(self.tmp.name)/"tickets.db"),
                        patch.object(config,"TRACE_DIR",Path(self.tmp.name)/"traces"),
                        patch.object(config,"PROVIDER","openai"),patch.object(config,"API_KEY","local-sdk-stub"),
                        patch.object(config,"BASE_URL","https://example.invalid/v1"),
                        patch.object(config,"MODEL_NAME","sdk-stub"),patch.object(config,"LC_TOOLSET","read_only"),
                        patch.object(config,"USE_HTTP_MOCK",False),
                        patch.object(config,"today",return_value=date(2026,10,13)),
                        patch.object(config,"now",return_value=datetime(2026,10,13,10,0))]
        for p in self.patches:
            p.start()
        providers.clear_mutations()
        build_db()
        self.agent = Agent(engine="langchain")
        self.addCleanup(self.agent.provider.root_client.close)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def response(self, message, reason="stop"):
        body = {"id":"sdk-response","object":"chat.completion","created":1,"model":"sdk-stub",
                "choices":[{"index":0,"message":{"role":"assistant",**message},"finish_reason":reason}],
                "usage":{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}}
        return SimpleNamespace(parse=lambda:body)

    def test_sdk_request_tool_schema_call_id_feedback_and_tokens(self):
        args = dict(from_city="上海",to_city="杭州",date="2026-10-14")
        first = self.response({"content":None,"tool_calls":[{"id":"server-call-1","type":"function",
                                "function":{"name":"query_tickets","arguments":json.dumps(args)}}]},"tool_calls")
        last = self.response({"content":"SDK 桩收到真实模拟库存工具结果。"})
        with patch.object(self.agent.provider.client.with_raw_response,"create",side_effect=[first,last]) as create:
            r = self.agent.chat("sdk","查明天上海到杭州的高铁")
        self.assertEqual(create.call_count,2)
        payloads = [c.kwargs for c in create.call_args_list]
        self.assertEqual({t["function"]["name"] for t in payloads[0]["tools"]},{"query_tickets","search_policy"})
        tool = next(m for m in payloads[1]["messages"] if m["role"]=="tool")
        self.assertEqual(tool["tool_call_id"],"server-call-1")
        self.assertGreater(json.loads(tool["content"])["count"],0)
        self.assertEqual(r["tool_sequence"],["query_tickets"])
        self.assertEqual(r["tokens"],{"prompt":14,"completion":6})
        self.assertEqual(r["finish_reason"],"stop")
        # provider 表示所用适配器；此测试使用 SDK 桩，不能作为 live 证据。
        self.assertEqual(r["provider"],"langchain_live")

    def test_sdk_error_is_safe_and_next_turn_can_recover(self):
        with patch.object(self.agent.provider.client.with_raw_response,"create",side_effect=RuntimeError("private-token-or-path")):
            r = self.agent.chat("sdk","查票")
        self.assertIn("RuntimeError",r["reply"])
        self.assertNotIn("private-token",r["reply"])
        with patch.object(self.agent.provider.client.with_raw_response,"create",return_value=self.response({"content":"SDK 桩恢复"})):
            r = self.agent.chat("sdk","继续")
        self.assertEqual(r["reply"],"SDK 桩恢复")


if __name__ == "__main__":
    unittest.main()
