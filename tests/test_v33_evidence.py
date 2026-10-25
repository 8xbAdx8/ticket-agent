import unittest
import tempfile
import json
import hashlib
from pathlib import Path
from web.evidence import batch, summary, mutation_rows, mutation_totals, diff_values, verified_manifest, latency_rows, read_audit_records,b_aux_batch


class EvidenceTests(unittest.TestCase):
    def test_original_evidence_hashes_and_separate_denominators(self):
        self.assertTrue(all(verified_manifest()[1].values()))
        for engine, count, na in (("legacy",101,2),("langchain",100,3)):
            s=summary(batch(engine)["rows"])
            self.assertEqual((s["passed"],s["failed"],s["executed"],s["not_applicable"],s["defined"]),(count,0,count,na,103))

    def test_selected_matrix_never_hides_extra_probe_miss(self):
        selected=mutation_rows(False)
        self.assertEqual((len(selected),sum(r["killed"] for r in selected)),(69,69))
        probe=[r for r in mutation_rows() if r["origin"]=="额外探测"]
        states={r["case_id"]:r for r in probe}
        self.assertEqual(states["T04"]["status"],"missed")
        self.assertEqual(states["R01"]["status"],"not_applicable")
        self.assertFalse(states["F15"]["c5"])
        self.assertFalse(states["M12"]["c5"])
        self.assertIsNone(mutation_totals()[-1]["detected"])
        self.assertIsNone(mutation_totals()[-1]["tested"])

    def test_nulls_not_converted_to_success_or_zero(self):
        self.assertIsNone(summary([])["rate"])
        self.assertEqual(summary([{"status":"not_verified"}])["executed"],0)
        self.assertEqual(latency_rows([{"id":"x","executed":[{"total_latency_ms":None}]}]),[])

    def test_nested_diff_retains_missing_and_added_fields(self):
        rows=diff_values({"date":"a","trains":[{"id":1}]},{"date":"b","trains":[{"id":2},3]})
        self.assertEqual({r["字段"] for r in rows},{"$.date","$.trains[0].id","$.trains[1]"})

    def test_blob_digest_and_missing_evidence_are_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=json.dumps({"trace_id":"full","fault_report":{"executions":[]}}).encode()
            (root/"blob.json").write_bytes(raw)
            record={"trace_id":"summary","full_evidence":{"available":True,"path":"blob.json","sha256":hashlib.sha256(raw).hexdigest()}}
            (root/"audit_runs.jsonl").write_text(json.dumps(record),encoding="utf-8")
            self.assertEqual(read_audit_records(root/"audit_runs.jsonl")[0][0]["trace_id"],"full")
            record["full_evidence"]["sha256"]="bad"
            (root/"audit_runs.jsonl").write_text(json.dumps(record),encoding="utf-8")
            self.assertIn("display_warning",read_audit_records(root/"audit_runs.jsonl")[0][0])

    def test_b_specialist_populations_stay_separate(self):
        data=b_aux_batch("新增代码专项（47 检查）")
        counts=summary(data["rows"])
        self.assertEqual((counts["defined"],counts["passed"],counts["not_applicable"]),(47,45,2))
        self.assertEqual(data["original_generated"],"2026-10-16")
        self.assertEqual(summary(b_aux_batch("M8 并发幂等（10 检查）")["rows"])["passed"],10)
