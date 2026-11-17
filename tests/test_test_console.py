"""Test console: cases, RAG dimensions, mutation verdicts, batch comparison."""
import json
import tempfile
import unittest
from pathlib import Path

from web import test_console as console


def write_batch(folder, results=None, pytest_log="1 passed", report=None):
    directory = Path(folder)
    directory.mkdir(parents=True, exist_ok=True)
    if results is not None:
        (directory / "results.json").write_text(json.dumps({"results": results}), encoding="utf-8")
    if pytest_log is not None:
        (directory / "pytest.log").write_text(pytest_log, encoding="utf-8")
    if report is not None:
        (directory / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return directory


class CaseTests(unittest.TestCase):
    def test_case_stats_keep_every_bucket_visible(self):
        rows = [{"用例": "a", "状态": "通过"}, {"用例": "b", "状态": "通过"},
                {"用例": "c", "状态": "失败"}, {"用例": "d", "状态": "跳过"},
                {"用例": "e", "状态": "未记录"}]
        stats = console.case_stats(rows)
        self.assertEqual(stats, {"总计": 5, "通过": 2, "失败": 1, "跳过": 1, "未记录": 1})

    def test_case_rows_keep_recorded_status_and_never_invent_one(self):
        with tempfile.TemporaryDirectory() as folder:
            write_batch(folder, [
                {"case_id": "tests/test_a.py::A::test_ok", "stage": "call", "status": "passed", "duration_s": 0.123},
                {"case_id": "tests/test_a.py::A::test_bad", "stage": "setup", "status": "failed",
                 "assertion_evidence": "E   AssertionError: expected paid"},
                {"case_id": "tests/test_a.py::A::test_odd", "stage": "call", "status": "mystery"},
            ])
            rows = console.case_rows(folder)
        self.assertEqual([r["状态"] for r in rows], ["通过", "失败", "未记录"])
        self.assertEqual(rows[1]["阶段"], "前置条件")
        self.assertEqual(rows[0]["耗时（秒）"], 0.123)

    def test_missing_results_file_yields_no_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(console.case_rows(folder), [])

    def test_filter_matches_status_and_keyword(self):
        rows = [{"用例": "tests/test_a.py::test_x", "状态": "通过", "断言证据": ""},
                {"用例": "tests/test_b.py::test_y", "状态": "失败", "断言证据": "AssertionError: paid"}]
        self.assertEqual(len(console.filter_cases(rows, "失败", "")), 1)
        self.assertEqual(len(console.filter_cases(rows, "全部", "paid")), 1)
        self.assertEqual(len(console.filter_cases(rows, "全部", "test_b")), 1)

    def test_source_reader_rejects_paths_outside_tests(self):
        for case in ("../x.py::t", "web/app.py::t", "/etc/passwd::t"):
            with self.subTest(case=case):
                self.assertIsNone(console.case_source(case))

    def test_source_reader_returns_the_real_test_body(self):
        source = console.case_source("tests/test_run_phases.py::PhaseStateTests::test_no_events_is_unknown_not_success")
        self.assertIsNotNone(source)
        self.assertEqual(source["file"], "tests/test_run_phases.py")
        self.assertIn("def test_no_events_is_unknown_not_success", source["source"])

    def test_detail_reports_missing_source_instead_of_guessing(self):
        row = {"用例": "tests/does_not_exist.py::t", "阶段": "用例执行", "状态": "失败", "耗时（秒）": 1,
               "断言证据": "E   AssertionError: boom"}
        with tempfile.TemporaryDirectory() as folder:
            write_batch(folder, pytest_log="log body")
            detail = console.case_detail(row, folder)
        self.assertIn("未找到测试源码", detail["预期行为来源"])
        self.assertEqual(detail["实际结果"], "AssertionError: boom")
        self.assertEqual(detail["进程日志"], "log body")


class RagDimensionTests(unittest.TestCase):
    def test_unmeasured_dimensions_are_never_reported_as_passing(self):
        dims = {d["评估项"]: d for d in console.rag_dimensions({})}
        self.assertEqual(dims["检索命中"]["状态"], "未评估")
        self.assertEqual(dims["引用支持"]["状态"], "未评估")
        self.assertEqual(dims["回答正确"]["状态"], "未评估")
        self.assertNotIn("通过", [d["状态"] for d in dims.values()])

    def test_retrieval_is_measured_but_answer_stays_unassessed(self):
        rag = {"metrics": {"keyword": {"positive_samples": 57, "negative_samples": 8,
                                       "no_answer_false_recall": 8, "recall1": 0.93}},
               "answer_faithfulness": "not_evaluated_no_generation"}
        dims = {d["评估项"]: d for d in console.rag_dimensions(rag)}
        self.assertEqual(dims["检索命中"]["状态"], "已评估")
        self.assertEqual(dims["检索命中"]["分母"], "57 条正样本")
        self.assertEqual(dims["回答正确"]["状态"], "未评估")
        self.assertIn("not_evaluated_no_generation", dims["回答正确"]["依据"])
        self.assertEqual(dims["无答案拒答"]["状态"], "仅检索层代理指标")
        self.assertIn("误召回 8", dims["无答案拒答"]["依据"])

    def test_mode_rows_round_floats_and_keep_missing_as_none(self):
        rows = console.rag_mode_rows({"metrics": {"keyword": {"recall1": 0.9298245614035088, "positive_samples": 57},
                                                  "vector": {"positive_samples": 0}}})
        self.assertEqual(rows[0]["recall@1"], 0.9298)
        self.assertIsNone(rows[0]["MRR"])
        self.assertIsNone(rows[1]["recall@1"])


class MutationTests(unittest.TestCase):
    def test_missing_verdict_is_never_counted_as_detected(self):
        self.assertEqual(console.mutation_state(None), "未记录")
        self.assertEqual(console.mutation_state(True), "已检出")
        self.assertEqual(console.mutation_state(False), "未检出")
        self.assertEqual(console.mutation_state(None, True), "不适用")

    def test_summary_counts_only_explicit_detections(self):
        summary = console.mutation_summary()
        self.assertTrue(summary)
        for row in summary:
            self.assertLessEqual(row["已检出"], row["选定组合"] if row["选定组合"] is not None else 0)


class ComparisonTests(unittest.TestCase):
    def report(self, suite="s1", source="x1", status="passed", passed=10):
        return {"suite_sha256": suite, "source_sha256": source, "steps": [
            {"id": "pytest", "name": "pytest", "status": status,
             "details": {"passed": passed, "failed": 0, "skipped": 0}}]}

    def test_same_fingerprints_are_comparable(self):
        result = console.compare(self.report(), self.report(status="failed", passed=9))
        self.assertTrue(result["comparable"])
        self.assertEqual(result["pytest"][0]["passed"], 10)
        self.assertEqual(result["pytest"][1]["passed"], 9)

    def test_different_fingerprints_are_flagged_as_not_comparable(self):
        result = console.compare(self.report(), self.report(suite="s2"))
        self.assertFalse(result["same_suite"])
        self.assertFalse(result["comparable"])

    def test_meta_states_owner_and_scope(self):
        meta = dict(console.batch_meta({"batch_id": "b1", "owner": "A_offline_not_B_formal",
                                        "steps": [{"id": "pytest", "name": "pytest", "status": "passed"}],
                                        "configuration": {"mode": "offline"}}))
        self.assertIn("不是 B 正式测试成绩", meta["归属"])
        self.assertIn("pytest=通过", meta["测试范围"])
        self.assertIn("mode=offline", meta["运行环境"])


if __name__ == "__main__":
    unittest.main()
