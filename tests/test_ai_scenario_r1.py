"""V3.11-R1 test-side batch, lifecycle checkpoint and Oracle claim regression."""
from pathlib import Path
import json
import uuid

import httpx

from target.scenario_r1_budget import R1Batch
from target.scenario_r1_lifecycle import R1Run
from tests.test_ai_scenario_v311 import ScriptedSDK, ROUTE, selection


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
