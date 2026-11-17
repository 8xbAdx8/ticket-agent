"""V3.10 regression contracts for the reported interaction/run/card defects."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from tests.v39.test_v394_defaults import session

from web import interaction
from web.run_view import phase_states
from web.railway_cards import names_for
from web.result_rows import iter_rows, as_row, batches
from tests.v39.test_service import sim


def test_interaction_history_is_a_real_public_contract():
    assert callable(interaction.history)
    source = Path(interaction.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(isinstance(n, ast.FunctionDef) and n.name == "history" for n in tree.body)


def test_conversation_uses_the_module_level_interaction_import():
    source = Path(__file__).resolve().parents[2] / "web/conversation.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = any(isinstance(n, ast.ImportFrom) and n.module == "web"
                   and any(a.name == "interaction" for a in n.names) for n in tree.body)
    assert imported
    # A local assignment named interaction would make Python treat the name as
    # local and could reproduce the reported UnboundLocalError.
    local_assignments = [n for n in ast.walk(tree)
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))]
    for fn in local_assignments:
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == "interaction":
                raise AssertionError("conversation.py shadows the interaction module")


def test_quick_ticket_shortcut_carries_explicit_gtfs_station_codes():
    source = Path(interaction.__file__).read_text(encoding="utf-8")
    assert "出发站编码AOH" in source and "到达站编码HGH" in source
    assert "请先询问尚未提供的路线和出行日期" not in source


def test_railway_tool_result_closes_the_query_phase():
    events = [
        {"event_type": "tool_proposed", "tool": "railway_query_trips"},
        {"event_type": "railway_tool_result", "tool": "railway_query_trips",
         "status": "succeeded", "executed": True, "duration_ms": 3},
    ]
    states = {row["key"]: row for row in phase_states(events)}
    assert states["query"]["status"] == "done"
    assert "查询静态车次" in states["query"]["detail"]


def test_interaction_observer_keeps_railway_tool_in_run_record(session):
    row, fresh = interaction.begin(session, "查询车次", "r1", "quick:查余票")
    assert fresh
    interaction.observe(session, row, {
        "session_id": session.sid, "run_id": "run-1", "event_type": "railway_tool_result",
        "tool": "railway_query_trips", "status": "succeeded", "executed": True,
    })
    assert row["tools"] == [{"tool": "railway_query_trips", "call_id": None, "status": "succeeded"}]
    assert row["stage"] == "工具已返回结果"


def test_card_projection_resolves_station_names_from_static_ids():
    session = SimpleNamespace(railway_queries=[], results=[[{
        "ok": True, "tool": "railway_query_trips",
        "args": {"origin_stop_id": "AOH", "destination_stop_id": "HGH"},
        "result": {"data": []},
    }]])
    names = names_for(session)
    assert names.get("AOH") == "上海虹桥"
    assert names.get("HGH") == "杭州东"


def test_railway_tool_result_grounds_contextual_followups():
    from target.followups import contextual_candidates
    event = {
        "event_type": "railway_tool_result", "status": "succeeded", "executed": True,
        "tool": "railway_query_trips", "run_id": "r", "session_id": "s",
        "event_id": "e", "args": {"service_date": "2026-11-05", "origin_stop_id": "AOH",
        "destination_stop_id": "HGH"},
        "output": {"query_parameters": {"service_date": "2026-11-05", "origin_stop_id": "AOH",
        "destination_stop_id": "HGH"}, "data": [
            {"trip_short_name": "G7541", "trip_id": "T1"},
            {"trip_short_name": "G1321", "trip_id": "T2"}]},
    }
    trace = {"session_id": "s", "user_msg": "查询2026-11-05 上海虹桥到杭州东的铁路车次", "reply": "查询完成"}
    options, facts = contextual_candidates(trace, [event], {"trace_id": "r"})
    assert len(options) >= 2
    assert any("G7541" in row["question"] or "上海虹桥" in row["question"] for row in options)
    assert facts["intent"] == "railway_query"


def test_large_page_is_projected_to_three_rows_but_trace_counts_stay():
    import json
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from target.v39.model_result import messages
    rows=[{"trip_id": "T"+str(i), "trip_short_name": "G"+str(i)} for i in range(50)]
    result={"data": rows, "returned_count": 50, "total_count": 109, "has_more": True,
            "next_cursor": "50", "dataset_version": "v1", "database_sha256": "d", "source_sha256": "s"}
    values=[HumanMessage("查询车次"), AIMessage("", tool_calls=[dict(id="c1", name="railway_query_trips", args={"cursor": "0"})]),
            ToolMessage(json.dumps(result, ensure_ascii=False), name="railway_query_trips", tool_call_id="c1")]
    out=messages(values)
    projected=json.loads(out[-1].content)
    assert projected["returned_count"]==50 and projected["total_count"]==109
    assert len(projected["data"])==3 and projected["shown_count"]==3
    assert len(json.loads(values[-1].content)["data"])==50


def test_budget_exhaustion_has_actionable_user_message():
    from web.user_copy import error_message
    text=error_message("observed_token_budget_exhausted")
    assert "安全预算" in text and "已完成" in text


def test_result_adapters_accept_dict_flat_list_nested_list_and_none():
    row = {"tool": "railway_query_trips", "ok": True, "result": {"data": []}}
    assert list(iter_rows(row)) == [row]
    assert list(iter_rows([row])) == [row]
    assert list(iter_rows([[row]])) == [row]
    assert list(iter_rows([[[row]]])) == [row]
    assert list(iter_rows([None, [], row, [row]])) == [row, row]
    assert as_row([[row]]) is row
    assert as_row([]) is None
    assert batches([row]) == [[row]]
    assert batches([[row], [row]]) == [[row], [row]]


def test_names_for_survives_legacy_flat_and_nested_result_containers():
    row = {"ok": True, "tool": "railway_query_trips",
           "args": {"origin_stop_id": "AOH", "destination_stop_id": "HGH"},
           "result": {"data": []}}
    for results in ([row], [[row]], [[[row]]], [None, [row]]):
        session = SimpleNamespace(railway_queries=[], results=results)
        names = names_for(session)
        assert names.get("AOH") == "上海虹桥" and names.get("HGH") == "杭州东"


def test_policy_statement_success_refund_is_not_an_execution_claim():
    from target.rag_faithfulness import _execution_claims
    _, findings = _execution_claims("按D9 CHANGED_REFUND_P01，每乘客最多一次成功退款[P01]。", [])
    assert findings == []
    _, findings = _execution_claims("已成功退款 [P01]。", [])
    assert any(f["claim"] == "已成功退款" for f in findings)


def test_display_guard_accepts_train_seen_in_prior_quote():
    from web.conversation import unsafe_ticket_result
    record={"reply":"车次 G7541 | 二等座","user_msg":"确认下单"}
    audit={"public_trace":record,"judgement":{"hallucination":{"hallucination_detected":True,
        "findings":[{"train":"G7541","classification":"unsupported_claim"}]}}}
    session=SimpleNamespace(results=[[{"tool":"railway_quote_fare","result":{"quote":{"trip_id":"5l000G75410A"}}}]],railway_queries=[],audits=[audit])
    assert unsafe_ticket_result(session,record) is False
    session2=SimpleNamespace(results=[],railway_queries=[],audits=[audit])
    assert unsafe_ticket_result(session2,record) is True


def test_policy_decision_id_is_not_a_train_claim():
    from target.diagnostics import detect_hallucinated_trains
    result=detect_hallucinated_trains("按 D9 CHANGED_REFUND_P01，政策版本 V3.9.1-D9-B-P01-1。", {"G7541"})
    assert result["hallucination_detected"] is False
    assert all(f["train"] != "D9" for f in result["findings"])


def test_ui_confirmation_marker_supports_persisted_order_claim(sim):
    from target.v39.business_claim_guard import check
    from tests.v39.test_service import create
    service,ctx,proposal,result=create(sim)
    service.page_event(ctx,"UI_CONFIRMED_PROPOSAL",{"proposal_id":proposal["proposal_id"]},result,True,0)
    order=service.order(ctx,result["order_id"])
    assert check("已创建订单。",[],ctx,service.store.path,service.now())["status"]=="supported"
