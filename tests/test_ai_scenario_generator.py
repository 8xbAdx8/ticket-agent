import copy
import json
import uuid
from pathlib import Path
import pytest
from target.scenario_generator import Store, ROOT, review, evidence


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv('TICKET_DISABLE_LOCAL_SECRETS', '1')
    return Store(ROOT / 'artifacts/runtime' / ('ai-scenario-test-' + uuid.uuid4().hex))


def candidate(store):
    result = store.generate('验证查询工具参数', '工具调用', 'medium', 1, 'Mock')
    assert result['status'] == 'SUCCEEDED'
    return store.list()[0]


def test_review_execute_trace_and_isolation(store):
    files = [ROOT/'web/datasets/b_v32_20261020/case_catalog.json', ROOT/'data/rag1000/v1.1.1/cases.jsonl']
    before = [p.read_bytes() for p in files]
    row = candidate(store)
    assert row['status'] == 'PENDING'
    assert review(row['body'])['quality'] == 'PASS'
    with pytest.raises(ValueError):
        store.run(row['id'], row['revision'])
    store.decide([(row['id'], row['revision'])], 'APPROVED', 'reviewer')
    approved = store.list()[0]
    result = store.run(approved['id'], approved['revision'])
    assert result['status'] == 'passed'
    assert result['turn_results'][0]['run_id']
    assert result['turn_results'][0]['actual_tools'] == ['query_tickets']
    assert Path(result['turn_results'][0]['evidence_ref']).is_file()
    assert Store(store.root).runs()[0]['body'] == result
    assert [p.read_bytes() for p in files] == before
    for action in ('DELETED', 'REJECTED'):
        with pytest.raises(ValueError):
            store.decide([(approved['id'], approved['revision'])], action, 'reviewer')


@pytest.mark.parametrize('change', ['unknown_tool', 'bad_type', 'empty', 'state', 'order', 'uncertain'])
def test_failure_modes(store, change):
    row = candidate(store)
    case = copy.deepcopy(row['body'])
    if change == 'unknown_tool':
        case['expect'] = {'must_call': ['railway_lock_seat']}
    elif change == 'bad_type':
        case['expect'] = {'must_call': ['query_tickets'], 'args': {'query_tickets': {'from_city': 17}}}
    elif change == 'empty':
        case['expect'] = {'finish_reason': 'stop'}
    elif change == 'state':
        case['expected_state_changes'] = ['PAID']
    elif change == 'order':
        case['expected_call_order'] = ['query_tickets']
    else:
        case['needs_manual_review'] = True
    case['assertions'] = case['expect']
    case['expected_tool_calls'] = case['expect'].get('must_call', [])
    quality = review(case)
    assert quality['quality'] == ('NEEDS_REVIEW' if change in ('state', 'order', 'uncertain') else 'REJECTED')
    store.save(case, 'editor', row['revision'])
    updated = store.list()[0]
    with pytest.raises(ValueError):
        store.decide([(updated['id'], updated['revision'])], 'APPROVED', 'reviewer')


def test_revision_history_and_deletion(store):
    row = candidate(store)
    store.save(row['body'], 'editor', row['revision'])
    with pytest.raises(ValueError):
        store.save(row['body'], 'stale', row['revision'])
    row = store.list()[0]
    store.decide([(row['id'], row['revision'])], 'DELETED', 'reviewer')
    assert store.list() == []
    assert store.list(True)[0]['status'] == 'DELETED'
    with store.connect() as c:
        assert c.execute('SELECT count(*) FROM history').fetchone()[0] == 3


def test_duplicates_and_atomic_approval(store):
    a = candidate(store)
    b = candidate(store)
    assert review(a['body'], [b['body']])['duplicates'] == [b['id']]
    with pytest.raises(ValueError):
        store.decide([(a['id'], 1), (b['id'], 1)], 'APPROVED', 'reviewer')
    assert all(r['status'] == 'PENDING' for r in store.list())


@pytest.mark.parametrize('count', [0, 6, True])
def test_generation_limits(store, count):
    with pytest.raises(ValueError):
        store.generate('test', '工具调用', 'medium', count, 'Mock')


def test_prompt_has_current_registry_and_provenance():
    packet = evidence('业务状态一致性')
    names = [t['function']['name'] for t in packet['registered_railway_tools']]
    assert len(names) == 11
    assert 'railway_lock_seat' not in names
    assert packet['effective_prompt']
    assert packet['references']['target/v39/policy.py']


def test_provider_failure_record_and_budget(store, monkeypatch):
    from target import p2_generator
    def unavailable(*args, **kwargs):
        raise RuntimeError('synthetic outage')
    monkeypatch.setattr(p2_generator, 'call', unavailable)
    result = store.generate('参数边界', '工具调用', 'medium', 1, 'deepseek')
    assert result['status'] == 'FAILED'
    assert store.list() == []
    assert result['budget']['remaining_http_requests'] == 50
    assert result['cost'] == 'UNKNOWN'


def test_generation_provider_scope_and_shared_budget(store, monkeypatch):
    import config
    from target import p2_generator
    from target.acceptance_budget import active
    original = (config.PROVIDER, config.MODEL_NAME)
    calls = []

    def model(*args, **kwargs):
        calls.append(kwargs['run_id'])
        assert config.PROVIDER == 'deepseek'
        budget = active()
        body = {'max_tokens': 4096, 'messages': []}
        budget.reserve('synthetic-http', 'deepseek', body, b'{}')
        budget.settle('synthetic-http', {'prompt_tokens': 20, 'completion_tokens': 10}, 'response_received')
        item = {'title': '查询工具参数', 'turns': ['请查明天上海到杭州高铁'],
                'expected_behavior': 'answer', 'expect': {'must_call': ['query_tickets']},
                'difficulty': 'medium', 'forbidden_claims': ['真实出票']}
        return json.dumps({'scenarios': [item]}), {'prompt': 20, 'completion': 10}, ['synthetic-http'], []

    monkeypatch.setattr(p2_generator, 'call', model)
    result = store.generate('检查查询工具', '工具调用', 'medium', 1, 'deepseek')
    assert len(calls) == 1
    assert result['status'] == 'SUCCEEDED'
    assert result['budget']['http_requests'] == 1
    assert result['budget']['observed_tokens'] == 30
    assert store.list()[0]['status'] == 'PENDING'
    assert (config.PROVIDER, config.MODEL_NAME) == original


def test_content_hash_ignores_title_and_whitespace(store):
    row = candidate(store)
    body = copy.deepcopy(row['body'])
    body['title'] = '不同的标题'
    body['turns'] = ['请查询 明天 上海到杭州的高铁二等座']
    body['conversation'] = body['turns']
    store.save(body, 'editor', row['revision'])
    assert store.list()[0]['body']['normalized_hash'] == row['body']['normalized_hash']


def test_missing_generation_budget_cannot_reset(store, monkeypatch):
    from target import p2_generator
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise RuntimeError('offline injected failure')
    monkeypatch.setattr(p2_generator, 'call', unavailable)
    store.generate('test', '工具调用', 'medium', 1, 'deepseek')
    (store.root / 'generation-budget.sqlite').unlink()
    result = store.generate('test again', '工具调用', 'medium', 1, 'deepseek')
    assert result['status'] == 'FAILED'
    assert result['error'] == 'GENERATION_BUDGET_MISSING'
    assert len(calls) == 1
    assert not (store.root / 'generation-budget.sqlite').exists()
