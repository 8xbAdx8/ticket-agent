"""最小接入的离线验收；假凭据 + MockTransport，不执行真实 API。"""
import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import test_deepseek_agent as fixtures


class ProviderSelectionTests(unittest.TestCase):
    def probe(self, extra):
        with tempfile.TemporaryDirectory() as folder:
            env = {k:v for k,v in os.environ.items() if not k.startswith(("AGENT_", "DEEPSEEK_"))
                   and not k.endswith(("_API_KEY", "_TOKEN"))}
            env.update(AGENT_TRACE_DIR=folder, PYTHONIOENCODING="utf-8", **extra)
            # 网络入口一旦被触及就失败，不能靠缺失/假 Key 让供应商拒绝来冒充离线。
            code = '''import socket,json
def forbidden(*args,**kwargs): raise AssertionError("network forbidden")
socket.socket.connect=forbidden
socket.create_connection=forbidden
import config
from target.agent import Agent
if config.PROVIDER=="mock":
    agent=Agent()
    data={"provider":config.PROVIDER,"engine":agent.engine,"model_provider":agent.provider.name}
else:
    data={"provider":config.PROVIDER,"engine":config.ENGINE,"model":config.MODEL_NAME,
          "base":config.BASE_URL,"canonical_key":config.API_KEY=="offline-canonical-placeholder"}
print(json.dumps(data))'''
            return json.loads(subprocess.check_output([sys.executable,"-c",code],env=env,encoding="utf-8"))

    def test_default_is_unchanged_legacy_mock(self):
        self.assertEqual(self.probe({}), {"provider":"mock","engine":"legacy","model_provider":"mock"})

    def test_deepseek_selects_existing_langchain_and_canonical_key_only(self):
        result = self.probe({"AGENT_PROVIDER":"deepseek", "DEEPSEEK_API_KEY":"offline-canonical-placeholder",
                             "AGENT_API_KEY":"offline-unused-legacy-placeholder"})
        self.assertEqual(result, {"provider":"deepseek","engine":"langchain","model":"deepseek-flash",
                                  "base":"https://api.deepseek.com","canonical_key":True})


@unittest.skipUnless(fixtures.AVAILABLE, "需要 DeepSeek SDK；仍只使用离线传输")
class MinimalDeepSeekTests(unittest.TestCase):
    setUp = fixtures.DeepSeekAgentTests.setUp
    tearDown = fixtures.DeepSeekAgentTests.tearDown
    agent = fixtures.DeepSeekAgentTests.agent
    response = fixtures.DeepSeekAgentTests.response
    call = fixtures.DeepSeekAgentTests.call

    def test_missing_key_fails_before_client_or_transport(self):
        from target.agent import Agent
        from target.deepseek_runtime import DeepSeekError
        with patch.object(config,"API_KEY",""), patch("target.deepseek_runtime.guarded_client") as client:
            with self.assertRaisesRegex(DeepSeekError,"missing_DEEPSEEK_API_KEY"):
                Agent()
        client.assert_not_called()
        self.assertEqual(self.payloads, [])
        self.assertFalse((self.folder/"budget.db").exists())

    def test_fake_key_construction_never_sends_or_reserves(self):
        from target.agent import Agent
        from langchain_deepseek import ChatDeepSeek
        with patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("no real transport")) as send:
            agent = Agent()  # 构造真实 SDK 对象，但不执行 chat。
            try:
                self.assertIsInstance(agent.provider, ChatDeepSeek)
                self.assertEqual(set(agent.langchain_engine.tool_names), {"query_tickets","search_policy"})
            finally:
                agent.provider.root_client.close()
        send.assert_not_called()
        self.assertFalse((self.folder/"budget.db").exists())

    def test_two_readonly_schemas_and_tool_feedback_use_mocktransport(self):
        from langchain_deepseek import ChatDeepSeek
        agent = self.agent([
            self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":"锁座支付规则"})]}),
            self.response({"content":"政策检索结果，依据 P11。"})])
        result = agent.chat("minimal","锁座支付规则")
        self.assertIsInstance(agent.provider, ChatDeepSeek)
        self.assertEqual({t["function"]["name"] for t in self.payloads[0]["tools"]}, {"query_tickets","search_policy"})
        self.assertEqual(result["tool_sequence"], ["search_policy"])
        self.assertTrue(result["steps"][0]["calls"][0]["ok"])
        self.assertTrue(any(m["role"]=="tool" for m in self.payloads[1]["messages"]))

    def test_six_tools_and_waitlist_alias_cannot_enter_live(self):
        from target.agent import Agent
        from target.deepseek_runtime import DeepSeekError, Settings, guarded_client
        from target import tools
        blocked = set(tools.TOOL_NAMES)-{"query_tickets","search_policy"}
        self.assertEqual(blocked, {"lock_seat","create_order","pay_order","cancel_order","query_order","monitor_seat"})
        for name in sorted(blocked):
            with self.subTest(name=name), self.assertRaisesRegex(DeepSeekError,"read_only_tools_required"):
                Agent(tool_names=[name])
        with self.assertRaises(ValueError):
            Agent(tool_names=["waitlist"])  # 不是现有工具，也没有创建别名。
        with guarded_client(Settings.from_env(),transport=fixtures.httpx.MockTransport(
                lambda request:self.fail("non-readonly request reached transport"))) as client:
            for name in sorted(blocked|{"waitlist"}):
                with self.subTest(name=name), self.assertRaisesRegex(DeepSeekError,"read_only_tools_required"):
                    client.post("https://api.deepseek.com/chat/completions",json={
                        "model":"deepseek-flash","thinking":{"type":"disabled"},"max_tokens":16,
                        "tools":[{"function":{"name":name}}]})
        self.assertFalse((self.folder/"budget.db").exists())

    def test_normal_trace_and_logs_redact_secret_in_all_public_fields(self):
        import io
        secret = config.API_KEY  # 测试夹具固定的假凭据，不读取用户真实Key。
        raw_final = "政策说明 " + secret
        agent = self.agent([
            self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":secret})]}),
            self.response({"content":raw_final})])
        log = io.StringIO()
        handler = logging.StreamHandler(log)
        logging.getLogger().addHandler(handler)
        try:
            result = agent.chat("minimal-secret", "检索政策 " + secret)
        finally:
            logging.getLogger().removeHandler(handler)
            handler.close()
        self.assertFalse(secret in json.dumps(result), "credential must not enter returned trace")
        self.assertFalse(secret in log.getvalue(), "credential must not enter logs")
        for path in config.TRACE_DIR.glob("*.jsonl"):
            self.assertFalse(secret in path.read_text(encoding="utf-8"), "credential must not enter trace files")
        self.assertEqual(result,json.loads((config.TRACE_DIR/"traces.jsonl").read_text(encoding="utf-8")))
        self.assertEqual(result["tool_sequence"], ["search_policy"])
        self.assertTrue(result["steps"][0]["calls"][0]["ok"])

    def test_loaded_credential_stays_redacted_if_environment_is_cleared(self):
        from target.deepseek_runtime import safe_text
        secret = config.API_KEY
        with patch.dict(os.environ,{"DEEPSEEK_API_KEY":""}):
            self.assertFalse(secret in safe_text("diagnostic " + secret), "loaded credential must stay redacted")


if __name__ == "__main__":
    unittest.main()
