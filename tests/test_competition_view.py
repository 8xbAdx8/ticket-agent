"""Offline checks for B-backed coverage, separated populations and evidence links."""
import json
import unittest
from unittest.mock import patch

import config
from streamlit.testing.v1 import AppTest

from web.competition_view import ENGINES, matrix_rows, overview_data
from web.evidence import DIMENSIONS, batch, cases, dimension_rows, summary, verified_manifest
from target.diagnostics import sanitize


class CompetitionDataTests(unittest.TestCase):
    def test_kpis_are_independent_record_counts(self):
        view = overview_data()
        self.assertEqual(len(view["catalog"]), 103)
        self.assertEqual([r["defined"] for r in view["catalog_dimensions"]], [15, 25, 15, 12, 18, 12, 6])
        for engine, expected in (("legacy", 101), ("langchain", 100)):
            with self.subTest(engine=engine):
                item = view["engines"][engine]
                self.assertEqual(item["summary"], summary(batch(engine)["rows"]))
                self.assertEqual(item["summary"]["executed"], expected)
                self.assertEqual(item["summary"]["passed"], expected)
        self.assertEqual(sum(v["summary"]["executed"] for v in view["engines"].values()), 201)
        self.assertEqual(view["mutation_summary"]["defined"], 69)
        self.assertEqual(view["mutation_summary"]["passed"], 69)
        self.assertEqual(view["metadata"], verified_manifest()[0])
        self.assertTrue(all(view["sha256_match"].values()))

    def test_matrix_matches_catalog_and_each_engine(self):
        view = overview_data()
        rows = matrix_rows(view)
        self.assertEqual(len(rows), 14)
        for engine, name in ENGINES.items():
            for result in dimension_rows(batch(engine)["rows"]):
                with self.subTest(engine=engine, dimension=result["dimension"]):
                    row = next(r for r in rows if r["维度"] == result["dimension"] and r["引擎"] == name)
                    self.assertEqual(row["实际执行"], result["executed"])
                    self.assertEqual(row["不适用"], result["not_applicable"])
                    self.assertEqual(row["用例数"], len([c for c in cases() if c["dimension"] == result["dimension"]]))

    def test_failed_unknown_and_inapplicable_are_not_passes(self):
        records = [{"id": str(i), "dimension": DIMENSIONS[0], "status": state}
                   for i, state in enumerate(("passed", "failed", "not_verified", "indeterminate", "not_applicable", "skipped", "missing"))]
        fake = {"rows": records, "read_errors": {"missing": False, "invalid": 0, "truncated": False}}
        with patch("web.competition_view.batch", return_value=fake):
            view = overview_data()
        for item in view["engines"].values():
            self.assertEqual(item["summary"]["executed"], 2)
            self.assertEqual(item["summary"]["rate"], .5)
            row = item["dimensions"][0]
            self.assertTrue(all(row[k] == 1 for k in ("passed", "failed", "not_verified", "indeterminate", "not_applicable", "skipped", "missing")))
        row = matrix_rows(view)[0]
        self.assertEqual([row[k] for k in ("通过", "失败", "未验证", "无法判定", "不适用", "跳过", "状态缺失")], [1] * 7)


class CompetitionUITests(unittest.TestCase):
    def setUp(self):
        self.settings = patch.multiple(config, PROVIDER="mock", ENGINE="legacy", LC_TOOLSET="all", USE_HTTP_MOCK=False, USE_VECTOR_RAG=False)
        self.settings.start()
        self.models = patch("web.runtime.Agent")
        self.agent = self.models.start()
        self.app = AppTest.from_file(str(config.BASE_DIR / "web/app.py"), default_timeout=30).run()
        self.app.radio(key="workspace_mode").set_value("测试工作台").run()
        self.clean()

    def tearDown(self):
        self.agent.assert_not_called()
        self.models.stop()
        self.settings.stop()

    def clean(self):
        self.assertEqual([e.message for e in self.app.exception], [])

    def test_default_nonempty_b_snapshot_and_separate_engine_totals(self):
        markup = "\n".join(m.value for m in self.app.markdown)
        self.assertIn("比赛七维度覆盖总览", markup)
        self.assertIn("103 条测试用例", markup)
        self.assertIn(">201<", markup)
        self.assertIn("69 / 69", markup)
        for dimension in DIMENSIONS:
            self.assertIn(dimension, markup)
        self.assertEqual(self.app.selectbox(key="competition_source").value, "B 独立测试")
        self.assertFalse(any("暂无本浏览器实验记录" in e.value for e in self.app.info))
        caption = "\n".join(e.value for e in self.app.caption)
        meta, _ = verified_manifest()
        self.assertIn(meta["execution_date"], caption)
        self.assertIn(meta["code_commit"], caption)
        self.assertNotIn("本轮 Live 已通过", markup)

    def test_all_fourteen_links_filter_engine_dimension_and_raw_evidence(self):
        for engine in ENGINES:
            for index, dimension in enumerate(DIMENSIONS):
                with self.subTest(engine=engine, dimension=dimension):
                    self.app.button(key=f"competition_evidence_{engine}_{index}").click().run()
                    self.clean()
                    self.assertEqual(self.app.radio(key="workspace_page").value, "质量分析")
                    self.assertEqual(self.app.radio(key="quality_source").value, "B 历史测试")
                    self.assertEqual(self.app.radio(key="quality_section").value, "七维度")
                    self.assertEqual(self.app.selectbox(key="quality_batch").value, engine)
                    self.assertEqual(self.app.selectbox(key="quality_dimension").value, dimension)
                    expected = [r for r in batch(engine)["rows"] if r["dimension"] == dimension]
                    self.assertEqual(self.app.selectbox(key="quality_case").options, [r["id"] for r in expected])
                    rendered = [json.loads(j.value) for j in self.app.json]
                    self.assertIn(sanitize(expected[0]), rendered)
                    # Both original assertions and saved public Trace turns survive the link.
                    self.assertTrue(any(isinstance(r, dict) and "checks" in r and "executed" in r for r in rendered))
                    self.app.radio(key="workspace_page").set_value("测试总览").run()
                    self.clean()

    def test_engine_switch_and_dimension_switch_reset_stale_case(self):
        self.app.button(key="competition_evidence_legacy_0").click().run()
        self.app.selectbox(key="quality_case").select("F15").run()
        self.app.selectbox(key="quality_dimension").select("工具调用").run()
        self.clean()
        self.assertTrue(self.app.selectbox(key="quality_case").value.startswith("T"))
        self.app.selectbox(key="quality_batch").select("langchain").run()
        self.clean()
        self.assertEqual(self.app.selectbox(key="quality_dimension").value, "工具调用")

    def test_secondary_batches_and_themes_remain_accessible(self):
        for source in ("当前测试实验室（实时）", "A 历史离线自测", "A 当前隔离实验", "B 独立测试"):
            self.app.selectbox(key="competition_source").select(source).run()
            self.clean()
        for theme in ("深色", "浅色"):
            self.app.radio(key="theme").set_value(theme).run()
            self.clean()
            self.assertTrue(any("比赛七维度覆盖总览" in m.value for m in self.app.markdown))

    def test_old_browser_batch_preference_does_not_restore_empty_default(self):
        app = AppTest.from_string(
            'import streamlit as st\n'
            'st.session_state["dashboard_owner"] = "当前测试实验室（实时）"\n'
            'from web.competition_view import competition_page\n'
            'competition_page([])\n'
        ).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="competition_source").value, "B 独立测试")
        self.assertTrue(any("比赛七维度覆盖总览" in m.value for m in app.markdown))

    def test_missing_manifest_reports_unavailable_instead_of_fabricating_scores(self):
        with patch("web.competition_view.overview_data", side_effect=FileNotFoundError()):
            self.app.run()
        self.clean()
        self.assertTrue(any("未生成成绩" in e.value for e in self.app.error))
        self.assertFalse(any("双引擎实际执行次数" in m.value for m in self.app.markdown))

    def test_manifest_mismatch_is_visible(self):
        view = overview_data()
        view["sha256_match"]["execution.jsonl"] = False
        with patch("web.competition_view.overview_data", return_value=view):
            self.app.run()
        self.clean()
        self.assertTrue(any("哈希不一致" in e.value for e in self.app.error))


if __name__ == "__main__":
    unittest.main()
