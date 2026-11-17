"""V3.11-R1 test-side batch, lifecycle checkpoint and Oracle claim regression."""
from contextlib import closing
from pathlib import Path
import json
import uuid

import httpx

from target.scenario_r1_budget import R1Batch
from target.scenario_r1_lifecycle import R1Run
from tests.test_ai_scenario_v311 import ScriptedSDK, ROUTE, selection

import pytest


@pytest.fixture(autouse=True)
def _r1_sdk_env(monkeypatch):
    # Keep R1 tests independent of environment left by the V3.11 suite.
    values = dict(TICKET_DISABLE_LOCAL_SECRETS="1", TICKET_WEB_OFFLINE_ONLY="0",
                  DEEPSEEK_API_KEY="r1-sdk-test-key", DASHSCOPE_API_KEY="r1-sdk-test-key",
                  DEEPSEEK_MODEL="deepseek-flash", DASHSCOPE_MODEL="qwen3.8-flash",
                  DEEPSEEK_BASE_URL="https://api.deepseek.com",
                  DASHSCOPE_BASE_URL="https://cn-beijing.maas.qwencloudapi.com/compatible-mode/v1")
    for k, v in values.items():
        monkeypatch.setenv(k, v)


def make_batch():
    root = Path('artifacts/runtime/v310-v311-r1-test-' + uuid.uuid4().hex[:10])
    root.mkdir(parents=True)
    auth = dict(approved=True, http_limit=96, provider_limits=dict(deepseek=48, bailian=48), pilot_http_limit=24)
    (root / 'authorization.json').write_text(json.dumps(auth), encoding='utf-8')
    batch = R1Batch(root)
    batch.initialize_authorized(auth)
    return batch, root


def test_r1_batch_pilot_then_release_is_persistent():
    batch, root = make_batch()
    assert batch.status()['r1_limits']['http_limit'] == 24
    assert batch.status()['remaining_http_requests'] == 24
    batch.release_remaining(dict(pilot_reviewed=True, evidence=['test-only']))
    reopened = R1Batch(root)
    assert reopened.status()['r1_limits']['phase'] == 'released'
    assert reopened.status()['r1_limits']['http_limit'] == 96
    assert reopened.status()['remaining_http_requests'] == 96


def test_r1_offline_create_checkpoint_and_confirmation():
    batch, root = make_batch()
    sdk = ScriptedSDK()
    holder = {}
    sdk.tool('railway_query_trips', dict(ROUTE, limit=2))
    sdk.tool('railway_quote_fare', lambda world: dict(selection(world), passenger_count=2))
    sdk.tool('railway_create_order', lambda world: dict(
        quote_id=world['railway_quote_fare']['quote']['quote_id'],
        passengers=['合成甲', '合成乙'], contact=holder['phone']))
    sdk.answer('已生成建单提案，等待确认。')
    run = R1Run(root, 'deepseek', transport=httpx.MockTransport(sdk.handle))
    holder['phone'] = run.run.context.owner_phone
    row = run.turn('查询并生成两人建单提案', expectations={
        'required_tools': ['railway_query_trips', 'railway_quote_fare', 'railway_create_order']})
    assert row['passed'] and run.pending()[0]['action'] == 'CREATE_ORDER'
    confirmed = run.confirm('CREATE_ORDER')
    assert confirmed['passed'] and len(run.read()['tables']['orders']) == 1
    names = sorted(p.name for p in run.checkpoint_dir.glob('*.json'))
    assert names == ['000-PREPARE.json', '001-TURN.json', '002-CREATE_ORDER.json']


def test_conditional_future_reply_is_not_a_paid_claim():
    from target.scenario_business_oracle import reply_claims
    result = reply_claims('请在页面点击确认后 Service 才会执行支付并创建已支付状态', {'tables': {
        'orders': [], 'transactions': [], 'refund_requests': [], 'change_requests': [], 'holds': []}})
    assert result['status'] == 'N/A'


def test_r1_finalize_is_idempotent_and_never_overwrites():
    batch, root = make_batch()
    sdk = ScriptedSDK(); holder = {}
    sdk.tool("railway_query_trips", dict(ROUTE, limit=1))
    sdk.tool("railway_quote_fare", lambda w: dict(selection(w), passenger_count=1))
    sdk.tool("railway_create_order", lambda w: dict(
        quote_id=w["railway_quote_fare"]["quote"]["quote_id"],
        passengers=["合成甲"], contact=holder["phone"]))
    sdk.answer("建单提案待确认。")
    run = R1Run(root, "deepseek", transport=httpx.MockTransport(sdk.handle))
    holder["phone"] = run.run.context.owner_phone
    run.turn("查询并生成一人建单提案", expectations={"required_tools": [
        "railway_query_trips", "railway_quote_fare", "railway_create_order"]})
    run.confirm("CREATE_ORDER")
    first = run.finalize("PASS")
    assert first["idempotent"] is False
    before = run.checkpoint_dir.joinpath("summary.json").read_bytes()
    second = run.finalize("PASS")
    assert second["idempotent"] is True
    assert run.checkpoint_dir.joinpath("summary.json").read_bytes() == before
    try:
        run.finalize("FAIL")
    except ValueError as exc:
        assert str(exc) == "R1_FINALIZE_STATUS_CONFLICT"
    else:
        raise AssertionError("conflicting finalize must not overwrite")


def test_r1_effective_limits_are_96_total_and_48_each_after_release():
    batch, root = make_batch()
    batch.release_remaining(dict(pilot_reviewed=True, evidence=["test-only"]))
    body = dict(model="fixture", messages=[], max_tokens=16)
    raw = json.dumps(body).encode()
    for i in range(96):
        batch.reserve("limit-" + str(i), "deepseek" if i % 2 == 0 else "bailian", body, raw)
    state = batch.status()
    assert state["http_requests"] == 96
    assert state["remaining_http_requests"] == 0
    try:
        batch.reserve("limit-96", "deepseek", body, raw)
    except Exception as exc:
        assert "acceptance_http_budget_exhausted" in str(exc) or "R1_HTTP_LIMIT" in str(exc)
    else:
        raise AssertionError("97th request must be rejected")
    # The independent R1 trigger is also tested directly, so the two layers
    # cannot silently diverge.
    with closing(batch.connect()) as connection:
        try:
            connection.execute(
                "INSERT INTO requests(request_id,provider,payload_sha256,reserved_tokens,output_limit,transactional,attempt,started_at) VALUES(?,?,?,?,?,?,?,?)",
                ("guard-96", "deepseek", "x", 1, 16, 0, 0, "2026-11-10T00:00:00Z"))
        except Exception as exc:
            assert "R1_HTTP_LIMIT" in str(exc)
        else:
            raise AssertionError("R1 trigger must reject the 97th row")


def test_r1_pending_checkpoint_restores_read_only_and_keeps_proposal():
    from web.session_store import restore_session
    batch, root = make_batch()
    sdk = ScriptedSDK(); holder = {}
    sdk.tool("railway_query_trips", dict(ROUTE, limit=1))
    sdk.tool("railway_quote_fare", lambda w: dict(selection(w), passenger_count=1))
    sdk.tool("railway_create_order", lambda w: dict(
        quote_id=w["railway_quote_fare"]["quote"]["quote_id"],
        passengers=["合成甲"], contact=holder["phone"]))
    sdk.answer("建单提案待确认。")
    run = R1Run(root, "deepseek", transport=httpx.MockTransport(sdk.handle))
    holder["phone"] = run.run.context.owner_phone
    run.turn("查询并生成一人建单提案", expectations={"required_tools": [
        "railway_query_trips", "railway_quote_fare", "railway_create_order"]})
    pending = run.pending()
    assert pending and pending[0]["state"] == "PENDING"
    restored = restore_session(run.run.session.root, expected_sid=run.session_id)
    assert restored.read_only and restored.agent is None
    assert restored.read_only
    # The historical replay is intentionally read-only; no secret/pending
    # action is restored into an executable Conversation.
    import pytest
    with pytest.raises(ValueError):
        restored.confirm_railway_proposal(pending[0]['proposal_id'], True)
