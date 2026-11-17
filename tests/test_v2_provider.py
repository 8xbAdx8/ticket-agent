"""模拟 SDK 的 Function Calling 回传/异常/上限自测；不是远端模型运行。"""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest.mock import patch
import config
from data.seed import build_db
from target.agent import Agent
from target.providers import OpenAIProvider


def response(name=None, args=None, call_id="stub_call", content="适配器自测完成"):
    calls = [NS(id=call_id, function=NS(name=name, arguments=json.dumps(args)))] if name else []
    return NS(choices=[NS(message=NS(content=None if name else content, tool_calls=calls))],
              usage=NS(prompt_tokens=10, completion_tokens=5))


class V2ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db, self.trace = config.DB_PATH, config.TRACE_DIR
        config.DB_PATH = Path(self.tmp.name)/"test.db"
        config.TRACE_DIR = Path(self.tmp.name)/"trace"
        build_db()
        with patch.object(config,"API_KEY","local-adapter-test-placeholder"):
            self.provider = OpenAIProvider()
        self.day = (config.today()+timedelta(days=1)).isoformat()

    def tearDown(self):
        self.provider.client.close()
        config.DB_PATH, config.TRACE_DIR = self.db, self.trace
        self.tmp.cleanup()

    def test_sdk_function_result_returns_matching_call_id_and_usage(self):
        args = dict(from_city="上海",to_city="杭州",date=self.day,kind="高铁",seat_type="二等座")
        with patch.object(self.provider.client.chat.completions,"create",side_effect=[response("query_tickets",args,call_id="server_id_123"),response()]) as create:
            result = Agent(self.provider).chat("adapter","查票")
        self.assertEqual(result["provider"], "openai")  # 自测结果是 stub，不写入真实模型证据
        self.assertEqual(result["tokens"], {"prompt":20,"completion":10})
        request = create.call_args_list[1].kwargs["messages"]
        tool = next(m for m in request if m["role"]=="tool")
        self.assertEqual(tool["tool_call_id"], "server_id_123")
        self.assertGreater(json.loads(tool["content"])["count"], 0)
        self.assertEqual(result["finish_reason"], "stop")

    def test_sdk_tool_error_is_returned_to_model(self):
        args = dict(train_no="missing",date=self.day,seat_type="二等座",passengers=["张三"])
        with patch.object(self.provider.client.chat.completions,"create",side_effect=[response("lock_seat",args,call_id="error_id"),response(content="锁座失败，未创建订单")]) as create:
            result = Agent(self.provider).chat("adapter-error","锁座")
        self.assertFalse(result["steps"][0]["calls"][0]["ok"])
        tool = next(m for m in create.call_args_list[1].kwargs["messages"] if m["role"]=="tool")
        self.assertEqual(tool["tool_call_id"], "error_id")
        self.assertIn("error", json.loads(tool["content"]))

    def test_sdk_repeated_requests_hit_configured_limit(self):
        args = dict(from_city="上海",to_city="杭州",date=self.day)
        with patch.object(config,"MAX_STEPS",2), patch.object(self.provider.client.chat.completions,"create",side_effect=[response("query_tickets",args,call_id=f"loop_{i}") for i in range(2)]) as create:
            result = Agent(self.provider).chat("adapter-loop","查票")
        self.assertEqual(create.call_count, 2)
        self.assertEqual(result["finish_reason"], "max_steps_exceeded")
