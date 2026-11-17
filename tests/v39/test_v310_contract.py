"""V3.10 prompt/tool/payment/follow-up contracts."""
from types import SimpleNamespace

import pytest
from tests.v39.test_service import sim


EXPECTED_RAILWAY_TOOLS = (
    "railway_search_stations",
    "railway_query_trips",
    "railway_trip_stops",
    "railway_check_inventory",
    "railway_quote_fare",
    "railway_create_order",
    "railway_get_order",
    "railway_pay_order",
    "railway_cancel_order",
    "railway_refund_order",
    "railway_change_order",
)


def test_v310_tool_registry_has_no_fabricated_lock_tool():
    from target.v39.registry import NAMES, ACTIONS
    assert NAMES == EXPECTED_RAILWAY_TOOLS
    assert "railway_lock_seat" not in NAMES
    assert "lock_seat" not in NAMES
    assert "railway_create_order" in ACTIONS


def test_unknown_railway_lock_is_actionable_not_frozen():
    from target.execution_config import CURRENT, tool_denial
    token = CURRENT.set(SimpleNamespace(tool_whitelist=("railway_create_order",),
                                        write_policy={}, execution_mode="developer_custom"))
    try:
        message = tool_denial("railway_lock_seat")
        assert "没有独立锁座" in message
        assert "建单" in message and "自动" in message
        assert "冻结" not in message
    finally:
        CURRENT.reset(token)


def test_v310_prompt_suffix_describes_auto_hold_without_lock_tool():
    from pathlib import Path
    source = Path("web/v39_bridge.py").read_text(encoding="utf-8")
    assert "没有独立锁座工具" in source
    assert "railway_lock_seat" in source
    assert "自动创建hold" in source
    assert "不得声称已经锁座" in source


def test_v310_create_order_has_no_hold_before_confirmation_and_one_after(sim):
    from target.v39.service import Service
    s, ctx = sim
    inventory = s.inventory(ctx, trip_id="T", service_date="2026-11-06",
                            origin_stop_id="X", destination_stop_id="Z",
                            seat_class="SECOND", quantity=1)
    assert inventory["available"] == 20
    quote = s.quote(ctx, trip_id="T", service_date="2026-11-06",
                    origin_stop_id="X", destination_stop_id="Z",
                    seat_class="SECOND", passenger_count=1)["quote"]
    proposal = s.propose(ctx, "CREATE_ORDER", dict(
        quote_id=quote["quote_id"], passengers=["三三"], contact=ctx.owner_phone))
    with s.store.transaction() as c:
        assert c.execute("SELECT count(*) FROM v39_orders").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM v39_holds").fetchone()[0] == 0
    result = s.confirm(ctx, proposal["proposal_id"])
    assert result["status"] == "PENDING_PAYMENT"
    order = s.order(ctx, result["order_id"])
    assert order["order_status"] == "PENDING_PAYMENT"
    with s.store.transaction() as c:
        hold = c.execute("SELECT hold_id,status FROM v39_holds WHERE order_id=?", (result["order_id"],)).fetchone()
    assert hold is not None and hold["status"] == "ACTIVE" and hold["hold_id"].startswith("H")
    assert s.confirm(ctx, proposal["proposal_id"]) == result
    with s.store.transaction() as c:
        assert c.execute("SELECT count(*) FROM v39_orders").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM v39_holds").fetchone()[0] == 1


def test_v310_qr_only_for_matching_active_pay_proposal():
    from web.v39_payment import eligible
    order = {"order_id": "V39-x", "order_status": "PENDING_PAYMENT",
             "payment_status": "UNPAID", "total_fen": 3000,
             "hold_expired_at_read": False}
    snapshot = {"updated_at": "2026-11-05T00:00:00+00:00", "orders": [order]}
    proposal = {"action": "PAY", "state": "PENDING",
                "expires_at": "2026-11-05T00:05:00+00:00",
                "payload": {"order_id": "V39-x", "expected_total_fen": 3000}}
    found = eligible(snapshot, proposal)
    assert found is not None and str(found[1]) == "30"
    assert eligible({**snapshot, "updated_at": "2026-11-05T00:06:00+00:00"}, proposal) is None
    assert eligible(snapshot, {**proposal, "action": "REFUND"}) is None
    assert eligible(snapshot, {**proposal, "payload": {"order_id": "V39-x", "expected_total_fen": 1}}) is None
    assert eligible({**snapshot, "orders": [{**order, "order_status": "PAID"}]}, proposal) is None


def test_v310_qr_payload_has_no_personal_data():
    from target.payment_qr import payment_payload
    payload = payment_payload("V39-x", 30, "30.00")
    assert set(payload) == {"order_id", "amount", "amount_yuan", "currency", "amount_unit", "demo"}
    assert payload["demo"] is True
    assert "乘客" not in str(payload) and "phone" not in str(payload)


def test_every_turn_has_deterministic_followup_fallback(sim, monkeypatch):
    from web import conversation
    record = {"tool_sequence": ["railway_query_trips"], "user_msg": "查票"}
    questions = conversation._fallback_questions(SimpleNamespace(), record)
    assert 2 <= len(questions) <= 3
    failed = conversation._fallback_questions(SimpleNamespace(), {}, {"run_id": "r", "error": {"category": "timeout"}})
    assert 2 <= len(failed) <= 3
    # The fallback is not a five/ten-round gate: repeated turns keep a usable set.
    for _ in range(20):
        assert 2 <= len(conversation._fallback_questions(SimpleNamespace(), record)) <= 3


def test_followup_accepts_fallback_and_dedupes_only_same_parent():
    from unittest.mock import patch
    from types import SimpleNamespace
    from web.conversation import _consume_followup
    session=SimpleNamespace(sid='s',live=False,read_only=False,history=[],pending_action=lambda:None)
    q='查看本次路线的最短运行时间';rid='run-1'
    state={'followup_questions_s_run-1':[q],'user_followup_request':{'sid':'s','run_id':rid,'question':q,'request_id':'r1','followup_id':'f1'}}
    with patch('web.conversation.st.session_state',state):
        req=_consume_followup(session,False)
    assert req and req['question']==q and req['generation_method']=='rule_fallback'
    state={'followup_questions_s_run-1':[q],'followup_sent_s_run-1':None,'user_followup_request':{'sid':'s','run_id':rid,'question':q,'request_id':'r2'}}
    with patch('web.conversation.st.session_state',state):
        assert _consume_followup(session,False) is not None
        state['followup_sent_s_run-1']=True
        assert _consume_followup(session,False) is None
    state={'followup_questions_s_run-2':[q],'user_followup_request':{'sid':'s','run_id':'run-2','question':q,'request_id':'r3'}}
    with patch('web.conversation.st.session_state',state):
        assert _consume_followup(session,False) is not None
