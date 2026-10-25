import unittest
from web.evidence import batch, summary, mutation_rows, diff_values, verified_manifest, latency_rows


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

    def test_nulls_not_converted_to_success_or_zero(self):
        self.assertIsNone(summary([])["rate"])
        self.assertEqual(summary([{"status":"not_verified"}])["executed"],0)
        self.assertEqual(latency_rows([{"id":"x","executed":[{"total_latency_ms":None}]}]),[])

    def test_nested_diff_retains_missing_and_added_fields(self):
        rows=diff_values({"date":"a","trains":[{"id":1}]},{"date":"b","trains":[{"id":2},3]})
        self.assertEqual({r["字段"] for r in rows},{"$.date","$.trains[0].id","$.trains[1]"})
