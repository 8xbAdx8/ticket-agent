"""Coverage denominators, provenance and mutation evidence for the quality console."""
import json
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from web import evidence
from web.competition_view import coverage_text, matrix_rows, overview_data
from web.quality import MUTATION_DETAILS, mutation_metrics_row


def test_coverage_keeps_undecided_cases_in_the_denominator():
    states = ["PASS", "FAIL", "NOT_RUN", "SKIPPED", "NA", "UNKNOWN", "MISSING", "not_verified",
              "indeterminate", "future_state"]
    totals = evidence.summary([{"status": status} for status in states])
    assert totals["defined"] == 10
    assert totals["applicable"] == 9
    assert totals["executed"] == 2
    assert totals["coverage"] == pytest.approx(2 / 9)
    assert totals["rate"] == 0.5
    assert totals["unknown"] == 2
    assert totals["not_run"] == totals["skipped"] == totals["missing"] == 1
    assert sum(totals[status] for status in evidence.CASE_STATUSES) == 10
    assert coverage_text(evidence.summary([])) == "不适用"
    assert evidence.summary([{"status": "NA"}])["coverage"] is None
    assert evidence.summary([{"status": "MISSING"}])["coverage"] == 0


def test_batch_missing_evidence_is_distinct_from_an_explicit_not_run(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "B_SOURCE", tmp_path)
    cases = [{"id": name, "dimension": evidence.DIMENSIONS[0]} for name in ("ran", "not-run", "absent", "duplicate")]
    cases.append({"id": "inapplicable", "dimension": evidence.DIMENSIONS[0], "engines": ["langchain"]})
    (tmp_path / "case_catalog.json").write_text(json.dumps(cases), encoding="utf8")
    (tmp_path / "manifest.json").write_text(json.dumps({
        "execution_date": "2026-01-01", "code_commit": "snapshot",
        "files": {"execution_langchain.jsonl": {"sha256": "fixture-digest"}},
    }), encoding="utf8")
    records = [
        dict(cases[0], passed=False), dict(cases[1], status="NOT_RUN", passed=False),
        dict(cases[3], passed=True), dict(cases[3], passed=False), dict(cases[4], passed=True),
    ]
    (tmp_path / "execution.jsonl").write_text("\n".join(map(json.dumps, records)), encoding="utf8")
    rows = evidence.batch("legacy")["rows"]
    assert [row["status"] for row in rows] == ["failed", "not_run", "missing", "unknown", "not_applicable"]
    assert evidence.summary(rows)["coverage"] == 0.25
    assert evidence.verified_manifest()[1] == {"execution_langchain.jsonl": False}
    assert all(row["status"] == "missing" for row in evidence.batch("langchain")["rows"])


def test_historical_dimensions_keep_the_original_populations():
    view = overview_data()
    matrix = matrix_rows(view)
    assert len(matrix) == 14
    assert {row["维度"] for row in matrix} == set(evidence.DIMENSIONS)
    assert sum(row["实际执行"] for row in matrix) == 201
    assert sum(row["适用用例"] for row in matrix) == 201
    assert sum(row["不适用"] for row in matrix) == 5


def test_lab_provenance_keeps_live_configuration_stubs_and_test_only_separate():
    provider = {"provider": "bailian_live", "model": "same-model"}
    rows = evidence.lab_record_rows([
        dict(provider, trace_id="live"), dict(provider, trace_id="stub", evidence_kind="offline_sdk_stub"),
        dict(provider, trace_id="injected", mutation_events=[{"enabled": True}]),
        dict(provider, trace_id="ordinary", mutation_events=[{"enabled": False}]),
        dict(provider, trace_id="invalid-events", mutation_events=1),
    ])
    assert [row["scope"] for row in rows] == [
        "Live 配置（请求见 Trace）", "离线 Mock / 替身", "TEST_ONLY", "Live 配置（请求见 Trace）",
        "Live 配置（请求见 Trace）",
    ]


def test_offline_dashboard_reports_test_only_in_a_separate_cohort():
    one = {"trace_id": "ordinary", "provider": "mock", "judgement": {"quality_verdict": "fail"}}
    two = {"trace_id": "injected", "provider": "mock", "judgement": {"test_verdict": "pass"},
           "mutation_events": [{"enabled": True}]}
    entries = [{"kind": "当前工作空间", "record": record} for record in (one, two)]
    with patch("web.evidence.audit_catalog", return_value=entries), patch("target.execution_config.run_identity", return_value=None):
        app = AppTest.from_string(
            "from web.dashboard import dashboard_page\ndashboard_page(source='A 当前隔离实验')"
        ).run()
        assert not app.exception
        scope = app.selectbox(key="dashboard_audit_scope")
        assert set(scope.options) == {"TEST_ONLY", "离线 Mock / 替身"}
        scope.select("离线 Mock / 替身").run()
        assert not app.exception
        rows = next(item.value for item in app.markdown if "<td>ordinary</td>" in item.value)
        assert "<td>injected</td>" not in rows
        assert any("0 / 1" in item.value for item in app.markdown)
        app.selectbox(key="dashboard_audit_scope").select("TEST_ONLY").run()
        assert not app.exception
        assert any("1 / 1" in item.value for item in app.markdown)


def test_mutation_populations_and_types_do_not_share_misses(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "B_SOURCE", tmp_path)
    selected = {"total": 5, "rows": [
        {"mutation": "date_offset", "case_id": "A", "killed": False},
        {"mutation": "skip_lock", "case_id": "B", "status": "NOT_RUN"},
        {"mutation": "skip_lock", "case_id": "C", "killed": None},
        {"mutation": "skip_lock", "case_id": "D"},
    ]}
    probe = {"total": 2, "details": [
        {"case_id": "R01", "killed": False, "G9999_进入回复": False},
        {"case_id": "E", "killed": True, "failed_rules": ["C5"]},
    ]}
    for name, payload in (("mutation.json", selected), ("probe_m6_m8.json", probe)):
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf8")
    (tmp_path / "m8_idempotent.json").write_text('{"total": 10}', encoding="utf8")
    base = evidence.mutation_group("选定矩阵")
    extra = evidence.mutation_group("额外探测")
    base_ui, extra_ui = mutation_metrics_row("选定矩阵", base), mutation_metrics_row("额外探测", extra)
    assert (base_ui["记录总数"], base_ui["适用分母"], base_ui["漏检"]) == (5, 5, 1)
    assert (base_ui["未执行"], base_ui["未知"], base_ui["证据缺失"]) == (1, 1, 2)
    assert (extra_ui["记录总数"], extra_ui["适用分母"], extra_ui["漏检"], extra_ui["不适用"]) == (2, 1, 0, 1)
    assert extra_ui["适用项检出率"] == "100.0%"
    skip_lock = [row for row in base["rows"] if row["mutation"] == "skip_lock"]
    assert mutation_metrics_row("M2", base, skip_lock)["漏检"] == 0
    assert mutation_metrics_row("M2", base, skip_lock)["适用项检出率"] == "—"
    assert evidence.mutation_totals()[-1]["tested"] is None


def test_missing_mutation_source_stays_unknown_and_empty_group_has_no_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "B_SOURCE", tmp_path)
    (tmp_path / "mutation.json").write_text('{"total": 0, "rows": []}', encoding="utf8")
    selected = evidence.mutation_group("选定矩阵")
    missing = evidence.mutation_group("额外探测")
    assert mutation_metrics_row("空组", selected)["适用项检出率"] == "—"
    assert mutation_metrics_row("缺失组", missing)["记录总数"] == "未知"
    assert mutation_metrics_row("缺失组", missing)["漏检"] == "未知"
    assert evidence.mutation_rows() == []
    readable = {"rows": [{"status": "detected"}], "missing_records": None}
    assert mutation_metrics_row("分母未确定", readable)["适用项检出率"] == "—"


def test_mutation_ui_reports_source_counts_and_original_miss_and_na_records():
    selected = evidence.mutation_group("选定矩阵")
    probe = evidence.mutation_group("额外探测")
    assert set(MUTATION_DETAILS) == set(evidence.MUTATIONS)
    assert mutation_metrics_row("选定矩阵", selected)["已检出"] == 69
    summary = mutation_metrics_row("额外探测", probe)
    assert [summary[key] for key in ("记录总数", "适用分母", "已检出", "漏检", "不适用")] == [16, 15, 14, 1, 1]
    app = AppTest.from_string("from web.quality import mutation_matrix\nmutation_matrix()").run()
    assert not app.exception
    app.radio(key="mutation_population").set_value("额外探测").run()
    app.button(key="mutation_first_miss").click().run()
    assert not app.exception
    assert app.selectbox(key="mutation_case").value == ("hallucinated_train", "T04")
    original = next(row["original"] for row in probe["rows"] if row["case_id"] == "T04")
    assert json.loads(app.json[-1].value) == original
    assert any(original["reply_片段"] in item.value for item in app.text)
    app.selectbox(key="mutation_case").set_value(("hallucinated_train", "R01")).run()
    assert not app.exception
    assert any("未进入适用分母" in item.value for item in app.info)


def test_overview_ui_shows_blocked_and_counts_for_every_state():
    states = ["passed", "failed", "not_run", "skipped", "not_applicable", "unknown", "missing"]
    rows = [{"status": state, "dimension": evidence.DIMENSIONS[0], "id": state} for state in states]
    fake = {"rows": rows, "source": "fixture", "read_errors": {"missing": False, "invalid": 0, "truncated": False}}
    with patch("web.competition_view.batch", return_value=fake):
        app = AppTest.from_string("from web.competition_view import competition_page\ncompetition_page([])").run()
    assert not app.exception
    assert any("BLOCKED" in item.value for item in app.info)
    assert any("2 / 6（33.3%）" in item.value for item in app.markdown)
    captions = "\n".join(item.value for item in app.caption)
    for state in ("跳过", "未执行", "不适用", "未知", "证据缺失"):
        assert f"{state} 1" in captions
