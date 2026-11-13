import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest

from target.scenario_generator import QUALITY_RULE_VERSION, Store, normalize, review, v310_contract
from target.scenario_plans import candidate, check, plans
from target.scenario_static_review import prompt_sample
from target.scenario_v310 import FLAG_SCHEMA, resolve, validate
from target.v39.static import RailwayStatic


@pytest.fixture
def case():
    result = candidate(plans()[0])
    result['objective'] = '验证 2026-11-05 上海虹桥到杭州东 G7331 及完整经停'
    _, trips, stops = result['integration_steps']
    trips['args']['train_no'] = 'G7331'
    trips['checks'] = [check('result.data.0.trip_short_name', 'G7331')]
    stops['checks'] = [check('result.data.stops', 9, 'len'),
                       check('result.data.stops.0.stop_id', 'AOH'),
                       check('result.data.stops.2.stop_name', '杭州东')]
    return result


def test_reference_sample_matches_frozen_adapter_and_real_dsl(case):
    sample = prompt_sample()
    assert v310_contract()['flag_schema'] == FLAG_SCHEMA
    static = RailwayStatic()
    trips = static.trips(**case['integration_steps'][1]['args'])
    trip_args = resolve(case['integration_steps'][2]['args'], {'trips': trips})
    actual = static.trip(**trip_args)
    assert actual['database_sha256'] == sample['dataset_sha256']
    assert actual['data']['trip']['trip_short_name'] == 'G7331'
    assert actual['data']['trip']['trip_id'] == sample['railway_trip_stops']['args']['trip_id']
    assert len(actual['data']['stops']) == sample['railway_trip_stops']['actual_full_stop_count'] == 9
    verdict = review(case)
    assert verdict['quality'] == 'PASS'
    assert any(x['path'] == 'result.data.stops' and x['actual'] == 9 and x['ok']
               for x in verdict['evidence'])


@pytest.mark.parametrize('path,op,value,code', [
    ('result.data.0.stop_id', 'eq', 'AOH', 'OUTPUT_PATH_INVALID'),
    ('result.data.0.stop_name', 'eq', '上海虹桥', 'OUTPUT_PATH_INVALID'),
    ('result.data.stops.0.unknown', 'eq', 1, 'OUTPUT_PATH_INVALID'),
    ('result.data.trip.0.trip_id', 'eq', 'x', 'OUTPUT_PATH_INVALID'),
    ('result.data', 'len', 2, 'OUTPUT_TYPE_MISMATCH'),
    ('result.data.stops', 'len', 2, 'STOP_COUNT_MISMATCH'),
    ('result.data.stops.999.stop_id', 'eq', 'AOH', 'OUTPUT_PATH_INVALID'),
    ('result.data.stops[0].stop_id', 'eq', 'AOH', 'ASSERTION_PATH_INVALID'),
    ('result.data.stops.*.stop_id', 'eq', 'AOH', 'ASSERTION_PATH_INVALID'),
    ('result.data.stops.-1.stop_id', 'eq', 'AOH', 'ASSERTION_PATH_INVALID'),
    ('result.data.stops.0.stop_id', 'eq', '$other.data.0.stop_id', 'UNBOUND_REFERENCE'),
])
def test_rejects_invalid_output_assertion(case, path, op, value, code):
    case['integration_steps'][2]['checks'] = [check(path, value, op)]
    verdict = review(case)
    assert verdict['quality'] == 'REJECTED'
    assert any(d['step'] == 2 and d['code'] == code for d in verdict['diagnostics'])


@pytest.mark.parametrize('changes,code', [
    ({'train_no': 'G7541'}, 'TRAIN_FILTER_REQUIRED'),
    ({'limit': True}, 'TOOL_ARGUMENTS_INVALID'),
    ({'extra': 'value'}, 'TOOL_ARGUMENTS_INVALID'),
    ({'origin_stop_id': '$future.data.0.stop_id'}, 'UNBOUND_REFERENCE'),
    ({'origin_stop_id': '$stations.data.0.invalid'}, 'MISSING_REFERENCE'),
    ({'origin_stop_id': '$stations.returned_count'}, 'RESOLVED_TOOL_ARGUMENTS_INVALID'),
])
def test_rejects_invalid_arguments_even_with_prior_output(case, changes, code):
    case['integration_steps'][1]['args'].update(changes)
    result = review(case)
    assert result['quality'] == 'REJECTED'
    assert any(d['step'] == 1 and d['code'] == code for d in result['diagnostics'])


def test_unfiltered_route_first_train_is_not_requested_train(case):
    args = case['integration_steps'][1]['args']
    args.pop('train_no')
    assert RailwayStatic().trips(**args)['data'][0]['trip_short_name'] == 'G7541'
    result = review(case)
    assert result['quality'] == 'REJECTED'
    assert {'TRAIN_FILTER_REQUIRED', 'STATIC_ASSERTION_MISMATCH', 'TRIP_REFERENCE_UNVERIFIED'} <= {
        d['code'] for d in result['diagnostics']}


def test_train_identity_assertion_and_link_are_both_required(case):
    steps = case['integration_steps']
    steps[1]['checks'][0]['op'] = 'contains'
    result = review(case)
    assert result['quality'] == 'REJECTED'
    assert {'TRAIN_SELECTION_UNVERIFIED', 'TRIP_REFERENCE_UNVERIFIED'} <= {d['code'] for d in result['diagnostics']}
    steps[1]['checks'][0]['op'] = 'eq'
    steps[2]['args']['trip_id'] = prompt_sample()['railway_trip_stops']['args']['trip_id']
    assert any(d['code'] == 'TRIP_REFERENCE_UNVERIFIED' for d in review(case)['diagnostics'])


@pytest.mark.parametrize('value', [True, False, 'false', 1, None])
def test_flag_requires_an_explicit_boolean_even_when_false(case, value):
    flag = dict(kind='flag', checks=[check('result.enabled', value)])
    if value is not None:
        flag['enabled'] = value
    case['integration_steps'].append(flag)
    result = review(case)
    if type(value) is bool:
        assert not validate(case)
        assert result['quality'] == 'PASS'
        assert result['evidence'][-1]['actual'] is value
    else:
        assert result['quality'] == 'REJECTED'
        assert any(d['code'] == 'FLAG_ENABLED_REQUIRED' and d['step'] == 3 for d in result['diagnostics'])


def test_creation_records_same_gate_and_never_approves(case):
    root = Path(__file__).resolve().parents[1] / 'artifacts/runtime' / ('v310-qa09-test-' + uuid4().hex)
    store = Store(root)
    requirements = dict(objective=case['objective'], constraints='')
    case['generation_requirements'] = requirements
    store.save(case, 'reviewer')
    with store.connect() as connection:
        original = connection.execute('SELECT body FROM history').fetchone()[0]
        created = connection.execute('SELECT stage,body FROM quality_reviews').fetchone()
    assert created['stage'] == 'CREATE'
    initial = json.loads(created['body'])
    assert initial['rule_version'] == QUALITY_RULE_VERSION
    assert initial == store.review_candidate(case)
    row = store.list()[0]
    assert row['status'] == 'PENDING'
    assert not store.runs()
    edited = copy.deepcopy(case)
    edited.pop('generation_requirements')
    edited['integration_steps'][1]['args']['train_no'] = 'G7541'
    store.save(edited, 'reviewer', row['revision'])
    revised = store.list()[0]
    assert revised['body']['generation_requirements'] == requirements
    assert revised['status'] == 'PENDING'
    with pytest.raises(ValueError, match='quality gate'):
        store.decide([(revised['id'], revised['revision'])], 'APPROVED', 'reviewer')
    with store.connect() as connection:
        assert connection.execute('SELECT body FROM history ORDER BY id LIMIT 1').fetchone()[0] == original
        attempt = connection.execute('SELECT stage,body FROM quality_reviews ORDER BY id DESC LIMIT 1').fetchone()
        assert attempt['stage'] == 'APPROVAL'
        assert json.loads(attempt['body'])['quality'] == 'REJECTED'
        assert connection.execute('SELECT count(*) FROM quality_reviews').fetchone()[0] == 3
    assert not store.runs()


def test_duplicate_uses_existing_policy(case):
    other = dict(case, case_id='duplicate')
    result = review(case, [other])
    assert result['quality'] == 'NEEDS_REVIEW'
    assert result['duplicates'] == ['duplicate']



@pytest.mark.parametrize('omit,code', [
    ('queries', 'REQUESTED_TRAIN_NOT_VERIFIED'),
    ('stops', 'REQUESTED_STOPS_NOT_VERIFIED'),
    ('count', 'REQUESTED_STOP_COUNT_NOT_VERIFIED'),
    ('enabled', 'REQUESTED_FLAG_NOT_VERIFIED'),
])
def test_positive_generation_request_cannot_be_replaced_with_incomplete_plan(case, omit, code):
    case['generation_requirements'] = dict(
        objective='查询 G7331 并验证全程经停和站数',
        constraints='先验证 flag.enabled=true', adapter='v310')
    flag = dict(kind='flag', enabled=True, checks=[check('result.enabled', True)])
    steps = case['integration_steps']
    steps.insert(0, flag)
    assert review(case)['quality'] == 'PASS'
    if omit == 'queries':
        steps[:] = steps[:1]
    elif omit == 'stops':
        steps.pop()
    elif omit == 'count':
        steps[-1]['checks'].pop(0)
    else:
        steps.pop(0)
    verdict = review(case)
    assert verdict['quality'] == 'REJECTED'
    assert any(d['code'] == code for d in verdict['diagnostics'])


def test_read_only_history_does_not_execute_static_query(case):
    case['integration_steps'].insert(0, dict(kind='history', enabled=True, checks=[check('result.read_only', True)]))
    result = review(case)
    assert result['quality'] == 'REJECTED'
    assert any(d['step'] == 1 and d['code'] == 'EXPECTED_ERROR_MISMATCH' for d in result['diagnostics'])
    assert not any(e['tool'] == 'railway_query_trips' for e in result['evidence'])


@pytest.mark.parametrize('where,path,code', [
    ('inventory', 'result.available.impossible', 'OUTPUT_PATH_INVALID'),
    ('quote', '$quote.quote.no_such_field', 'MISSING_REFERENCE'),
    ('db', 'db.nonexistent.0.order_id', 'OUTPUT_PATH_INVALID'),
])
def test_runtime_only_outputs_require_real_paths(where, path, code):
    result = candidate(plans()[1])
    if where == 'inventory':
        result['integration_steps'][1]['checks'].append(check(path, 0))
    elif where == 'quote':
        result['integration_steps'][3]['args']['quote_id'] = path
    else:
        result['integration_steps'][0]['checks'].append(check(path, 0))
    verdict = review(result)
    assert verdict['quality'] == 'REJECTED'
    assert any(d['code'] == code and d['path'] == path for d in verdict['diagnostics'])


def test_generated_legacy_payload_cannot_downgrade_selected_v310(monkeypatch):
    from target import p2_generator
    root = Path(__file__).resolve().parents[1] / 'artifacts/runtime' / ('v310-qa09-test-' + uuid4().hex)
    store = Store(root)
    item = dict(title='Legacy clarify', turns=['请帮我查询'], expected_behavior='clarify',
                expect={'reply_contains': ['请提供']}, forbidden_claims=['真实出票'], difficulty='medium')
    baseline = normalize([item], '功能正确性', 'test', 'hash', ['source'])[0]
    assert review(baseline)['quality'] == 'PASS'
    monkeypatch.setattr(p2_generator, 'call', lambda *args, **kwargs:
                        (json.dumps(dict(scenarios=[item])), {'prompt': 3, 'completion': 3}, [], []))
    receipt = store.generate('查询 G7331 全程经停', '功能正确性', 'medium', 1, 'deepseek', adapter='v310')
    assert receipt['status'] == 'SUCCEEDED'
    row = store.list()[0]
    assert row['status'] == 'PENDING'
    assert receipt['quality_reviews'][row['id']]['diagnostics'][0]['code'] == 'GENERATION_ADAPTER_MISMATCH'
    with pytest.raises(ValueError, match='quality gate'):
        store.decide([(row['id'],row['revision'])], 'APPROVED', 'reviewer')
    assert not store.runs()


def test_pending_edit_cannot_clear_required_adapter(case):
    case['generation_requirements'] = dict(objective=case['objective'], constraints='', adapter='v310')
    root = Path(__file__).resolve().parents[1] / 'artifacts/runtime' / ('v310-qa09-test-' + uuid4().hex)
    store = Store(root)
    store.save(case, 'reviewer')
    row = store.list()[0]
    edited = row['body']
    edited.pop('execution_adapter')
    edited.pop('generation_requirements')
    store.save(edited, 'reviewer', row['revision'])
    result = store.review_candidate(store.list()[0]['body'])
    assert result['quality'] == 'REJECTED'
    assert result['diagnostics'][0]['code'] == 'GENERATION_ADAPTER_MISMATCH'


@pytest.mark.parametrize('bad_step,code', [
    (dict(kind='foreign_order'), 'FOREIGN_REFERENCE_REQUIRED'),
    (dict(kind='foreign_confirm'), 'FOREIGN_REFERENCE_REQUIRED'),
    (dict(kind='chat', message='显示 {{missing.order_id}}'), 'UNBOUND_REFERENCE'),
    (dict(kind='chat', message='显示 {{state.orders.0.order_id}}'), 'UNBOUND_REFERENCE'),
])
def test_step_references_are_available_before_execution(case, bad_step, code):
    bad_step['checks'] = [check('metrics.money_conserved', True)]
    case['integration_steps'].insert(0, bad_step)
    verdict = review(case)
    assert verdict['quality'] == 'REJECTED'
    assert any(d['code'] == code and d['step'] == 0 for d in verdict['diagnostics'])


@pytest.mark.parametrize('change,code', [
    ('remove_route', 'REQUESTED_ROUTE_MISMATCH'),
    ('change_date', 'REQUESTED_DATE_MISMATCH'),
    ('business_action', 'READ_ONLY_SCOPE_VIOLATION'),
])
def test_named_static_request_keeps_exact_route_date_and_scope(case, change, code):
    case['generation_requirements'] = dict(
        objective='验证 2026-11-05 上海虹桥 AOH 到杭州东 HGH 的 G7331 及全程经停。只读。',
        constraints='', adapter='v310')
    assert review(case)['quality'] == 'PASS'
    steps = case['integration_steps']
    if change == 'remove_route':
        steps[1]['args'].pop('origin_stop_id')
        steps[1]['args'].pop('destination_stop_id')
    elif change == 'change_date':
        for step in steps[1:]:
            step['args']['service_date'] = '2026-11-06'
    else:
        steps.append(dict(kind='advance', seconds=30, checks=[check('result.advanced', 30)]))
    verdict = review(case)
    assert verdict['quality'] == 'REJECTED'
    assert any(d['code'] == code for d in verdict['diagnostics'])


@pytest.mark.parametrize('change,code', [
    ('first_stop', 'REQUESTED_FIRST_STOP_NOT_VERIFIED'),
    ('order_count', 'REQUESTED_ORDER_COUNT_NOT_CHECKED'),
    ('false_order_count', 'READ_ONLY_ORDER_COUNT_MISMATCH'),
    ('conflicting_order_count', 'READ_ONLY_ORDER_COUNT_MISMATCH'),
    ('late_flag', 'FLAG_ORDER_MISMATCH'),
])
def test_read_only_request_requires_its_own_assertions(case, change, code):
    case['generation_requirements'] = dict(
        objective='查询 G7331 全程经停，验证站数及首站。只读，不创建订单。',
        constraints='先验证 flag.enabled=true，包含 metrics.order_count=0', adapter='v310')
    steps = case['integration_steps']
    steps.insert(0, dict(kind='flag', enabled=True, checks=[check('result.enabled', True)]))
    checks = steps[-1]['checks']
    checks.append(check('metrics.order_count', 0))
    assert review(case)['quality'] == 'PASS'
    if change == 'first_stop':
        checks.pop(1)
    elif change == 'order_count':
        checks.pop()
    elif change == 'false_order_count':
        checks[-1]['value'] = 42
    elif change == 'conflicting_order_count':
        checks.append(check('metrics.order_count', 42, 'ge'))
    else:
        steps.append(steps.pop(0))
    verdict = review(case)
    assert verdict['quality'] == 'REJECTED'
    assert any(d['code'] == code for d in verdict['diagnostics'])


def test_invented_runtime_error_cannot_get_pass(case):
    from target.scenario_plans import tool
    case['integration_steps'].append(tool('railway_get_order', {}, 'orders',
                                          [check('result.error', 'FORGED_ERROR')], expected_error='FORGED_ERROR'))
    case['expected_tool_calls'].append('railway_get_order')
    verdict = review(case)
    assert verdict['quality'] == 'NEEDS_REVIEW'
    assert any('FORGED_ERROR' in message for message in verdict['warnings'])


@pytest.mark.parametrize('kind', ['check', 'reference'])
def test_overlong_numeric_paths_are_reported_as_invalid(case, kind):
    if kind == 'check':
        case['integration_steps'][1]['checks'] = [check(f'result.data.{"9"*5000}.trip_short_name', 'G7331')]
        expected = 'ASSERTION_PATH_INVALID'
    else:
        case['integration_steps'][2]['args']['trip_id'] = f'$trips.data.{"9"*5000}.trip_id'
        expected = 'UNBOUND_REFERENCE'
    verdict = review(case)
    assert verdict['quality'] == 'REJECTED'
    assert any(d['code'] == expected for d in verdict['diagnostics'])


def test_runtime_contract_paths_match_actual_reference_plan_outputs():
    from target.scenario_output_contract import result_shape, snapshot_shape, traverse
    from target.scenario_v310 import V310Adapter, lookup
    plan = plans()[1]
    result = V310Adapter().run(plan)
    assert result['status'] == 'passed'
    seen = set()
    for step, actual in zip(plan['integration_steps'], result['steps'], strict=True):
        if step['kind'] == 'tool' and step['tool'] in ('railway_check_inventory', 'railway_quote_fare', 'railway_get_order'):
            seen.add(step['tool'])
            for path in [c['path'].removeprefix('result.') for c in step['checks'] if c['path'].startswith('result.')]:
                traverse(result_shape(step), path.split('.'))
                assert lookup(actual['output'], path) is not None
        if actual['snapshot']['state']['orders']:
            assert lookup(actual['snapshot'], 'state.orders.0.order_status')
            traverse(snapshot_shape(), ['state', 'orders', '0', 'order_status'])
    assert seen == {'railway_check_inventory', 'railway_quote_fare', 'railway_get_order'}
