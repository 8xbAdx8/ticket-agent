import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from target.diagnostics import detect_hallucinated_trains, sanitize, metrics, mutation_events, save_audit, read_audits


class DiagnosticTests(unittest.TestCase):
    def test_detects_explicit_nonexistent_train(self):
        r=detect_hallucinated_trains("为您查到G9999，有余票。",["G7301"])
        self.assertTrue(r["hallucination_detected"])
        self.assertEqual(r["findings"][0]["train"],"G9999")

    def test_user_input_is_not_automatically_agent_hallucination(self):
        for reply in ("你输入的G9999，请确认。","引用用户原话：G9999","G9999不存在，未找到该车次。"):
            self.assertFalse(detect_hallucinated_trains(reply,["G7301"],user_message="G9999")["hallucination_detected"])
        self.assertTrue(detect_hallucinated_trains("G9999有余票",["G7301"],user_message="G9999")["hallucination_detected"])

    def test_valid_and_indeterminate_clauses_are_separate(self):
        self.assertEqual(detect_hallucinated_trains("G7301有余票",["G7301"])["status"],"clear")
        self.assertEqual(detect_hallucinated_trains("也许G9999",["G7301"])["status"],"indeterminate")
        self.assertEqual(detect_hallucinated_trains("例如G9999有票",["G7301"])["status"],"indeterminate")

    def test_missing_authority_does_not_fabricate_verdict(self):
        self.assertIsNone(detect_hallucinated_trains("G9999有票",None)["hallucination_detected"])

    def test_secret_headers_reasoning_and_personal_fields(self):
        import config
        with patch.object(config,"API_KEY","offline-secret-marker"),patch.dict("os.environ",{"DEEPSEEK_API_KEY":"offline-secret-marker"}):
            r=sanitize({"Authorization":"Bearer actual","reasoning_content":"hidden", "text":"offline-secret-marker 13800000001", "passengers":["真实姓名"]})
        text=json.dumps(r,ensure_ascii=False)
        self.assertNotIn("offline-secret-marker",text)
        self.assertNotIn("真实姓名",text)
        self.assertNotIn("hidden",text)
        self.assertNotIn("13800000001",text)

    def test_statuses_disabled_and_error(self):
        r=mutation_events({"mutations":{"date_offset":1},"injection_events":[{"mutation":"date_offset","stage":"tool_arguments","status":"failed","original":{},"mutated":{},"reason":"bad date"}]},"t")
        self.assertEqual(len(r),8)
        self.assertEqual(r[0]["status"],"error")
        self.assertEqual(r[1]["status"],"disabled")

    def test_metrics_never_turn_unknown_into_zero(self):
        r=metrics([{"judgement":{"dimensions":{"injection_applied":True,"platform_defect_detected":False}}}])
        self.assertEqual(r["injection_applied"]["denominator"],1)
        self.assertIsNone(r["agent_recovered"]["rate"])

    def test_large_evidence_is_hash_addressed_and_replay_detects_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            value={"schema_version":"ticket-agent-audit/3.2","trace_id":"t","timestamp":"now","fault_report":{"large":"x"*50000},"judgement":{}}
            save_audit(value,root)
            self.assertEqual(read_audits(root)[0],value)
            blob=next((root/"audit_blobs").glob("*.json"));blob.write_text("{}")
            self.assertEqual(read_audits(root)[0]["schema_version"],"unreadable")

    def test_old_trace_without_sidecar_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/"traces.jsonl").write_text('{"reply":"old"}\n')
            self.assertEqual(read_audits(temp),[])

    def test_malformed_sidecar_is_indeterminate(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/"audit_runs.jsonl").write_text('[]\nnot-json\n\n',encoding="utf-8")
            self.assertEqual([r["judgement"]["quality_verdict"] for r in read_audits(temp)],["indeterminate"]*2)
