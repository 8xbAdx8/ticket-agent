"""Explicit LangSmith API adapter tests; every HTTP operation is intercepted locally."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from target.observability import export_run, export_payload, configuration_status
try:
    import httpx
    HTTP=True
except ImportError: HTTP=False


@unittest.skipUnless(HTTP,"httpx optional in legacy environments")
class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{"LANGCHAIN_API_KEY":"offline-langsmith-key","LANGCHAIN_TRACING_V2":"true",
            "LANGCHAIN_PROJECT":"ticket-agent-fixture","LANGCHAIN_ENDPOINT":"https://api.smith.langchain.com",
            "LANGSMITH_TRACING":"","LANGSMITH_API_KEY":"","LANGSMITH_PROJECT":"","LANGSMITH_ENDPOINT":"",
            "LANGCHAIN_WORKSPACE_ID":"","LANGSMITH_WORKSPACE_ID":"","DASHSCOPE_API_KEY":"offline-bailian-key"})
        self.env.start()
        self.record={"trace_id":"fixture-local","provider":"bailian_live","git_sha":"fixture-sha","mode":"live",
            "local_trace_saved":True,"user_msg":"contact person@example.invalid 13800000001 11010519491231002X offline-bailian-key",
            "reply":"来源 P11","tokens":None,"total_latency_ms":18,"finish_reason":"stop",
            "private_orders":[{"contact":"must-never-export"}],"raw_audit":"must-never-export",
            "events":[{"event":"model_response","response_model":"qwen-fixture","usage":{},"reasoning_content":"private thoughts",
                       "tool_calls":[{"name":"search_policy","id":"c1","args":{"question":"锁座政策","authorization":"sensitive"}}]},
                      {"event":"tool_end","tool":"search_policy","args":{"question":"锁座政策"},"ok":True,"executed":True,
                       "result":{"hits":[{"doc_id":"P11","content":"锁座15分钟","contact":"must-never-export"}],"orders":"must-never-export"}}]}

    def tearDown(self): self.env.stop(); self.tmp.cleanup()

    def forbidden(self,request): self.fail("network must never be reached in this branch")

    def test_disabled_no_http_and_status_not_verified(self):
        with patch.dict(os.environ,{"LANGCHAIN_TRACING_V2":"false"}):
            self.assertEqual(configuration_status()["state"],"user_disabled")
            result=export_run(self.record,consent=True,transport=httpx.MockTransport(self.forbidden))
        self.assertEqual(result["http_requests"],0); self.assertFalse(result["remote_verified"])

    def test_no_consent_no_http(self):
        result=export_run(self.record,transport=httpx.MockTransport(self.forbidden))
        self.assertEqual(result["remote_status"],"consent_required")

    def test_missing_key_no_http_no_mock(self):
        with patch.dict(os.environ,{"LANGCHAIN_API_KEY":""}):
            self.assertEqual(configuration_status()["state"],"not_configured")
            result=export_run(self.record,consent=True,transport=httpx.MockTransport(self.forbidden))
        self.assertEqual(result["remote_status"],"not_configured")

    def test_configuration_presence_is_not_remote_verification(self):
        status=configuration_status()
        self.assertEqual(status["state"],"configured_unverified")
        self.assertNotIn("offline-langsmith-key",json.dumps(status))
        with patch.dict(os.environ,{"LANGSMITH_API_KEY":"conflicting-fixture"}):
            self.assertEqual(configuration_status()["state"],"configuration_error")

    def test_field_allowlist_and_pii_and_reasoning_removed(self):
        payload=export_payload(self.record); text=json.dumps(payload)
        for secret in ("offline-bailian-key","person@example.invalid","13800000001","11010519491231002X","private thoughts","must-never-export"):
            self.assertNotIn(secret,text)
        self.assertIsNone(payload["outputs"]["tokens"])
        self.assertIn("P11",text)

    def test_post_then_readback_is_required_for_verified_state(self):
        calls=[]; saved={}
        def respond(request):
            calls.append(request.method)
            if request.method=="POST": saved.update(json.loads(request.content)); return httpx.Response(201,json={})
            return httpx.Response(200,json=saved)
        original=copy.deepcopy(self.record)
        receipt=export_run(self.record,consent=True,trace_dir=self.root,transport=httpx.MockTransport(respond))
        self.assertTrue(receipt["remote_verified"])
        self.assertEqual(calls,["POST","GET"])
        self.assertEqual(receipt["generation_requests"],0)
        self.assertEqual(self.record,original)
        self.assertEqual(saved["extra"]["metadata"]["trace_id"],"fixture-local")
        self.assertNotIn("offline-langsmith-key",(self.root/"langsmith_exports.jsonl").read_text())

    def test_accepted_post_without_readback_is_not_success(self):
        calls=[]
        def respond(r):
            calls.append(r.method)
            return httpx.Response(201,json={}) if r.method=="POST" else httpx.Response(404,json={})
        receipt=export_run(self.record,consent=True,transport=httpx.MockTransport(respond))
        self.assertFalse(receipt["remote_verified"]); self.assertEqual(receipt["remote_status"],"failed")
        self.assertEqual(calls,["POST","GET"])

    def test_mismatched_remote_run_is_not_verified(self):
        receipt=export_run(self.record,consent=True,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"id":"other"})))
        self.assertFalse(receipt["remote_verified"])

    def test_failure_no_retry_and_does_not_change_model_result(self):
        original=copy.deepcopy(self.record); calls=[]
        def respond(r): calls.append(r.method); raise httpx.ReadTimeout("unsafe secret")
        receipt=export_run(self.record,consent=True,transport=httpx.MockTransport(respond))
        self.assertEqual(calls,["POST"]); self.assertEqual(receipt["error"]["category"],"timeout")
        self.assertEqual(self.record,original)

    def test_local_save_required_before_remote_upload(self):
        self.record["local_trace_saved"]=False
        result=export_run(self.record,consent=True,transport=httpx.MockTransport(self.forbidden))
        self.assertEqual(result["remote_status"],"local_trace_required")

    def test_endpoint_and_alias_configuration_errors_never_send(self):
        for value in ("http://api.smith.langchain.com","https://secret@api.smith.langchain.com","https://api.smith.langchain.com?secret=x"):
            with patch.dict(os.environ,{"LANGCHAIN_ENDPOINT":value}):
                result=export_run(self.record,consent=True,transport=httpx.MockTransport(self.forbidden))
                self.assertEqual(result["http_requests"],0)
