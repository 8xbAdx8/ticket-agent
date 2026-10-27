"""纯离线安全测试：MockTransport 不连接 DeepSeek，不消耗 API 余额。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from target.deepseek_runtime import (Settings, RequestBudget, guarded_client, safe_error,
                                      DeepSeekError, validate_configuration)
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@unittest.skipUnless(HTTPX_AVAILABLE,"原 V2 环境未安装 httpx；安全传输测试在独立环境运行")
class DeepSeekRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(ledger_path=Path(self.tmp.name)/"budget.db")

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self):
        return {"model":"deepseek-flash","messages":[{"role":"user","content":"Hi"}],
                "max_tokens":16,"thinking":{"type":"disabled"}}

    def test_configuration_uses_only_canonical_key_and_defaults(self):
        env = dict(os.environ,AGENT_PROVIDER="deepseek",DEEPSEEK_API_KEY="offline-canonical",AGENT_API_KEY="offline-legacy")
        for key in ("AGENT_MODEL","AGENT_ENGINE","AGENT_BASE_URL","AGENT_TRACE_DIR"):
            env.pop(key,None)
        script = "import config,json; print(json.dumps({'canonical':config.API_KEY=='offline-canonical','model':config.MODEL_NAME,'engine':config.ENGINE,'base':config.BASE_URL,'separate_trace':config.TRACE_DIR.name=='deepseek_live'}))"
        data = json.loads(subprocess.check_output([sys.executable,"-c",script],env=env,text=True))
        self.assertEqual(data,{"canonical":True,"model":"deepseek-flash","engine":"langchain","base":"https://api.deepseek.com","separate_trace":True})

    def test_missing_key_endpoint_and_model_fail_closed(self):
        with patch.multiple(config,API_KEY="",BASE_URL="https://api.deepseek.com",MODEL_NAME="deepseek-flash"):
            with self.assertRaisesRegex(DeepSeekError,"missing_DEEPSEEK_API_KEY"):
                validate_configuration()
        for url in ("http://api.deepseek.com","https://api.deepseek.com.evil.invalid","https://secret@api.deepseek.com","https://api.deepseek.com?secret=x"):
            with patch.multiple(config,API_KEY="offline-only",BASE_URL=url,MODEL_NAME="deepseek-flash"):
                with self.assertRaisesRegex(DeepSeekError,"official_endpoint_required"):
                    validate_configuration()
        with patch.multiple(config,API_KEY="offline-only",BASE_URL="https://api.deepseek.com",MODEL_NAME="retired-model"):
            with self.assertRaisesRegex(DeepSeekError,"deepseek_flash_required"):
                validate_configuration()

    def test_more_than_five_requests_are_recorded_without_touching_old_ledger(self):
        sent=[]
        def respond(request):
            sent.append(True)
            return httpx.Response(200,json={"model":"deepseek-flash","usage":{"prompt_tokens":2,"completion_tokens":1}})
        with guarded_client(self.settings,transport=httpx.MockTransport(respond)) as client:
            for _ in range(7):client.post("https://api.deepseek.com/chat/completions",json=self.payload())
        self.assertEqual(len(sent),7)
        another=RequestBudget(self.settings)
        self.assertEqual(another.snapshot()["request_count"],7)
        self.assertEqual(another.snapshot()["requests"][-1]["prompt"],2)
        self.assertFalse(self.settings.ledger_path.exists())

    def test_unknown_usage_is_null_in_ledger_not_invented_zero(self):
        with guarded_client(self.settings,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"model":"deepseek-flash"}))) as client:
            client.post("https://api.deepseek.com/chat/completions",json=self.payload())
        row = RequestBudget(self.settings).snapshot()["requests"][0]
        self.assertIsNone(row["prompt"])
        self.assertIsNone(row["completion"])

    def test_zero_limit_allows_more_than_five_requests_and_keeps_recording(self):
        with patch.dict(os.environ, {"DEEPSEEK_MAX_REQUESTS":"0",
                                     "DEEPSEEK_THINKING":"disabled",
                                     "DEEPSEEK_BUDGET_PATH":str(self.settings.ledger_path)}):
            settings = Settings.from_env()
        self.assertEqual(settings.max_requests, 0)
        sent = []
        def respond(request):
            sent.append(True)
            return httpx.Response(200, json={"model":"deepseek-flash",
                "usage":{"prompt_tokens":2,"completion_tokens":1}})
        # Recreate the client with the same ledger, as happens after a restart.
        for count in (5, 2):
            with guarded_client(settings, transport=httpx.MockTransport(respond)) as client:
                for _ in range(count):
                    client.post("https://api.deepseek.com/chat/completions", json=self.payload())
        snapshot = RequestBudget(settings).snapshot()
        self.assertEqual(len(sent), 7)
        self.assertEqual(snapshot["reserved_requests"], 7)
        self.assertIsNone(snapshot["limit"])
        self.assertTrue(all(row["status"] == 200 and row["prompt"] == 2 for row in snapshot["requests"]))
        # An obsolete positive cap cannot re-enable request admission limits.
        RequestBudget(self.settings).reserve()
        self.assertEqual(RequestBudget(settings).snapshot()["request_count"], 8)

    def test_unlimited_requests_still_reject_write_tools_before_transport(self):
        settings = Settings(max_requests=0, ledger_path=self.settings.ledger_path)
        with guarded_client(settings, transport=httpx.MockTransport(lambda r:self.fail("禁止到达网络层"))) as client:
            for tool in ("lock_seat", "create_order", "pay_order", "cancel_order", "query_order", "monitor_seat"):
                body = dict(self.payload(), tools=[{"function":{"name":tool}}])
                with self.assertRaisesRegex(DeepSeekError, "read_only_tools_required"):
                    client.post("https://api.deepseek.com/chat/completions", json=body)
        self.assertEqual(RequestBudget(settings).snapshot()["reserved_requests"], 0)

    def test_default_and_obsolete_cap_values_are_unlimited(self):
        with patch.dict(os.environ,{"DEEPSEEK_THINKING":"disabled"}):
            for old in (None,"-1","6","invalid"):
                if old is None:os.environ.pop("DEEPSEEK_MAX_REQUESTS",None)
                else:os.environ["DEEPSEEK_MAX_REQUESTS"]=old
                self.assertEqual(Settings.from_env().max_requests,0)

    def test_balance_get_does_not_consume_generation_budget(self):
        with guarded_client(self.settings,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"is_available":True}))) as client:
            client.get("https://api.deepseek.com/user/balance")
        self.assertEqual(RequestBudget(self.settings).snapshot()["reserved_requests"],0)

    def test_read_only_thinking_output_and_host_guards(self):
        cases = [dict(self.payload(),tools=[{"function":{"name":"pay_order"}}]),
                 dict(self.payload(),thinking={"type":"enabled"}),dict(self.payload(),max_tokens=9999),
                 dict(self.payload(),stream=True)]
        with guarded_client(self.settings,transport=httpx.MockTransport(lambda r:self.fail("禁止到达网络层"))) as client:
            for body in cases:
                with self.assertRaises(DeepSeekError):
                    client.post("https://api.deepseek.com/chat/completions",json=body)
            with self.assertRaises(DeepSeekError):
                client.post("https://example.invalid/chat/completions",json=self.payload())
        self.assertEqual(RequestBudget(self.settings).snapshot()["reserved_requests"],0)

    def test_error_categories_do_not_leak_body_or_key(self):
        categories = {400:"invalid_format",401:"authentication_failed",402:"insufficient_balance",422:"invalid_parameters",
                      429:"rate_limited",500:"server_error",503:"service_unavailable"}
        for status,category in categories.items():
            response = httpx.Response(status,request=httpx.Request("POST","https://api.deepseek.com/chat/completions"))
            error = httpx.HTTPStatusError("private-token-and-reasoning",request=response.request,response=response)
            self.assertEqual(safe_error(error),{"category":category,"http_status":status})
        self.assertEqual(safe_error(httpx.ReadTimeout("private"))["category"],"timeout")
        self.assertEqual(safe_error(httpx.ConnectError("private"))["category"],"network_connection")
        outer = RuntimeError("private")
        outer.__cause__ = DeepSeekError("request_budget_exhausted")
        self.assertEqual(safe_error(outer)["category"],"request_budget_exhausted")

    def test_unsafe_limits_and_thinking_opt_in_are_rejected(self):
        with patch.dict(os.environ,{"DEEPSEEK_TIMEOUT":"0"}):
            with self.assertRaises(DeepSeekError):
                Settings.from_env()
        with patch.dict(os.environ,{"DEEPSEEK_THINKING":"enabled"}):
            with self.assertRaisesRegex(DeepSeekError,"thinking_mode_not_validated"):
                Settings.from_env()


if __name__=="__main__":
    unittest.main()
