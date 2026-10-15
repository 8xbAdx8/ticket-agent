"""检查脚本控制流的离线桩验证；无任何真实网络请求。"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
import config
from scripts.check_deepseek_api import main
from target.deepseek_runtime import guarded_client


class ConnectivityScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_case(self, responses, key="offline-script-key", expect_failure=False):
        requests = []
        def respond(request):
            requests.append(request.method)
            status, body = responses[len(requests)-1]
            return httpx.Response(status,json=body)
        out = self.folder/"output"
        env = {"DEEPSEEK_API_KEY":key,"DEEPSEEK_BUDGET_PATH":str(self.folder/"budget.db")}
        with patch.dict(os.environ,env), patch.multiple(config,API_KEY=key,MODEL_NAME="deepseek-flash",BASE_URL="https://api.deepseek.com"), \
             patch("sys.argv",["check_deepseek_api.py","--run","--connection-only","--out",str(out)]), \
             patch("target.deepseek_runtime.guarded_client",side_effect=lambda settings:guarded_client(settings,transport=httpx.MockTransport(respond))), \
             contextlib.redirect_stdout(io.StringIO()):
            if expect_failure:
                with self.assertRaises(SystemExit) as caught:
                    main()
                self.assertEqual(caught.exception.code,1)
            else:
                main()
        return json.loads((out/"report.json").read_text(encoding="utf-8")), requests

    def test_missing_key_skips_without_http_or_mock_fallback(self):
        report, requests = self.run_case([],key="")
        self.assertEqual(requests,[])
        self.assertEqual(report["status"],"skipped_missing_key")
        self.assertFalse(report["real_api_verified"])
        self.assertTrue(all(c["status"]=="skipped" for c in report["cases"]))

    def test_connection_only_records_sdk_stub_tokens_and_stops(self):
        report, requests = self.run_case([(200,{"is_available":True}),(200,{"model":"deepseek-flash",
            "choices":[{"message":{"content":"Hello"}}],"usage":{"prompt_tokens":4,"completion_tokens":1}})])
        self.assertEqual(requests,["GET","POST"])
        self.assertEqual(report["token_usage"],{"prompt":4,"completion":1})
        self.assertEqual(report["online_generation_requests_this_run"],1)
        self.assertFalse(report["function_calling_verified"])

    def test_authentication_failure_is_failed_not_skipped_and_no_hello(self):
        report, requests = self.run_case([(401,{"error":{"message":"offline-script-key private-body"}})],expect_failure=True)
        self.assertEqual(requests,["GET"])
        self.assertEqual(report["cases"][0]["name"],"balance")
        self.assertEqual(report["cases"][0]["status"],"failed")
        self.assertEqual(report["error"]["category"],"authentication_failed")
        self.assertNotIn("offline-script-key",json.dumps(report))
        self.assertNotIn("private-body",json.dumps(report))


if __name__=="__main__":
    unittest.main()
