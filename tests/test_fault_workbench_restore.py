"""Keep the original executable lab reachable from the fourth workbench page."""
from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import config
from target.diagnostics import IDS
from web import runtime
from web.evidence import MUTATIONS, read_audit_records
from web.workbench_config import WORKBENCH_PAGES


APP = Path(__file__).resolve().parents[1] / "web/app.py"


def open_boundary_page():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.radio(key="workspace_mode").set_value("测试工作台").run()
    navigation = app.radio(key="workspace_page")
    assert tuple(navigation.options) == WORKBENCH_PAGES
    navigation.set_value("边界与异常测试").run()
    assert not app.exception
    return app


@pytest.mark.parametrize("railway_feature", ["0", "1"])
def test_page04_executes_original_date_offset_and_replays_saved_trace(tmp_path, monkeypatch, railway_feature):
    monkeypatch.setenv("TICKET_WEB_OFFLINE_ONLY", "1")
    monkeypatch.setenv("RAILWAY_SIMULATION_ENABLED", railway_feature)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    app = open_boundary_page()
    assert app.selectbox(key="lab_engine").value == "Legacy Mock"
    assert [box.key.removeprefix("lab_mutation_") for box in app.checkbox
            if box.key and box.key.startswith("lab_mutation_")] == list(MUTATIONS)
    assert list(IDS.values()) == [f"M{i}" for i in range(1, 9)]
    assert not any(box.value for box in app.checkbox if box.key and box.key.startswith("lab_mutation_"))
    next(box for box in app.selectbox if box.label == "测试场景").select("M1 日期偏移").run()
    assert not app.checkbox(key="lab_mutation_date_offset").value
    assert not list(tmp_path.rglob("audit_runs.jsonl"))

    app.checkbox(key="lab_mutation_date_offset").check().run()
    next(button for button in app.button if button.label == "执行测试").click().run()
    assert not app.exception
    session = app.session_state["lab_session"]
    path = session.trace_dir / "audit_runs.jsonl"
    saved = path.read_bytes()
    records, errors = read_audit_records(path)
    assert len(records) == 1 and not any(errors.values())
    audit = records[0]
    assert audit["public_trace"]["session_id"] == session.sid
    assert audit["fault_report"]["mutations"] == {"date_offset": 1}
    event = next(row for row in audit["mutation_events"] if row["mutation_id"] == "M1")
    assert event["status"] == "applied"
    assert date.fromisoformat(event["after"]) - date.fromisoformat(event["before"]) == timedelta(days=1)
    assert any(row["call_id"] == event["related_tool_call_id"] and row["executed"] is True
               and row["tool"] == "query_tickets" and row["args"]["date"] == event["after"]
               for row in audit["fault_report"]["executions"])
    judgement = audit["judgement"]
    assert judgement["dimensions"]["platform_defect_detected"] is True
    assert next(check for check in judgement["assertions"]
                if check["assertion"] == "executed_query_date_matches_user")["passed"] is False
    assert any(audit["trace_id"] in row.value for row in app.caption)
    assert {f'"{event[field]}"' for field in ("before", "after")} <= {block.value for block in app.code}

    refreshed = open_boundary_page()
    refreshed.radio(key="c_lab_section").set_value("历史回放").run()
    next(field for field in refreshed.text_input if field.label == "实验会话 ID").set_value(session.sid).run()
    assert not refreshed.exception
    assert any(audit["trace_id"] in row.value for row in refreshed.caption)
    assert path.read_bytes() == saved


def test_page04_historical_defect_matrix_keeps_m8_quick_drilldown():
    app = open_boundary_page()
    app.radio(key="c_lab_section").set_value("M1–M8 缺陷统计").run()
    assert not app.exception
    assert app.selectbox(key="mutation_type").options[1:] == [
        "M1 日期偏移", "M2 跳过锁座", "M3 重复调用", "M4 无限循环", "M5 线路错误",
        "M6 缺少政策引用", "M7 虚构车次", "M8 并发重复订单",
    ]
    app.button(key="mutation_m8_evidence").click().run()
    assert not app.exception
    assert app.radio(key="c_lab_section").value == "M8 并发证据"
    assert any("B 独立后端验证" in caption.value for caption in app.caption)


def test_page04_m4_preset_exercises_monitor_instead_of_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("TICKET_WEB_OFFLINE_ONLY", "1")
    monkeypatch.setenv("RAILWAY_SIMULATION_ENABLED", "1")
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "ROOT", tmp_path)
    app = open_boundary_page()
    next(box for box in app.selectbox if box.label == "测试场景").select("M4 监控重入").run()
    app.checkbox(key="lab_mutation_infinite_loop").check().run()
    next(button for button in app.button if button.label == "执行测试").click().run()

    assert not app.exception
    session = app.session_state["lab_session"]
    records, errors = read_audit_records(session.trace_dir / "audit_runs.jsonl")
    assert len(records) == 1 and not any(errors.values())
    audit = records[0]
    assert any(event["mutation_id"] == "M4" and event["status"] == "applied"
               for event in audit["mutation_events"])
    tools = [row["tool"] for row in audit["fault_report"]["executions"] if row["executed"]]
    assert tools[0] == "query_tickets" and tools.count("monitor_seat") > 1
    assert audit["judgement"]["dimensions"]["platform_defect_detected"] is True
