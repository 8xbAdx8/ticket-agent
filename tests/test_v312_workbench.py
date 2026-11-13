import json
from uuid import uuid4

import pytest

from target.scenario_workbench import RUN_ROOT, Workbench, _run_case, load_run_results
from target.scenario_workbench_gaps import inspect_run, select_gaps
from target.v39.planner import RailwayDemoProvider
from target.v39.static import RailwayStatic
from tests.test_scenario_workbench import FixtureModel, candidate, source_session


FIRST = '查询2026-11-05 上海虹桥到杭州东的铁路车次；出发站编码AOH，到达站编码HGH。'
NEXT = '需要我继续翻页取剩余车次吗？如果还需要，请继续取剩余车次。'


def check(path, value, op='eq'):
    return dict(path=path, op=op, value=value)


def railway_candidate():
    route = 'result.queries.0.args.'
    turns = [FIRST, NEXT, '查看 G7331 的经停站', '比较 G7331 和 G1321']
    return dict(candidate(), title='四轮静态查询', dimension='多轮', turns=turns, integration_steps=[
        dict(kind='chat', message=turns[0], checks=[
            check(route+'service_date', '2026-11-05'), check('result.reply', '还有下一页', 'contains')]),
        dict(kind='chat', message=turns[1], checks=[
            check(route+'service_date', '2026-11-05'), check(route+'origin_stop_id', 'AOH'),
            check(route+'destination_stop_id', 'HGH'), check(route+'cursor', '20')]),
        dict(kind='chat', message=turns[2], checks=[
            check('result.public_result.tool_sequence', 'railway_trip_stops', 'contains'),
            check(route+'service_date', '2026-11-05')]),
        dict(kind='chat', message=turns[3], checks=[
            check(route+'train_no', 'G7331'), check('result.queries.1.args.train_no', 'G1321'),
            check('metrics.order_count', 0), check('metrics.transaction_count', 0)]),
    ])


@pytest.mark.parametrize('engine', ['legacy', 'langchain'])
def test_four_real_offline_turns_use_tool_evidence_and_preserve_database(engine):
    run_id = uuid4().hex
    plan = dict(railway_candidate(), case_id='case-001')
    case = dict(plan, run_id=run_id, mutation=None)
    execution, events = _run_case(case, plan, RUN_ROOT/run_id/'executions/case-001', engine)
    assert execution['agent_invoked'] and events
    assert execution['objective_status'] == 'passed', [step['checks'] for step in execution['steps']]
    assert execution['metrics']['memory'] is True
    assert len({step['trace_id'] for step in execution['steps']}) == 4
    route = dict(service_date='2026-11-05', origin_stop_id='AOH', destination_stop_id='HGH', limit=20)
    query = RailwayStatic()
    first = query.trips(**route)
    second = query.trips(**route, cursor=first['next_cursor'])
    first_reply = execution['steps'][0]['result']['reply']
    assert f"共 {first['total_count']} 班" in first_reply
    assert f"本页返回 {first['returned_count']} 班" in first_reply
    assert '还有下一页' in first_reply
    stops = [row for row in execution['tool_evidence']
             if row['tool'] == 'railway_trip_stops' and row.get('executed') is True]
    assert len(stops) == 1
    trip_id = next(row['trip_id'] for row in first['data'] if row['trip_short_name'] == 'G7331')
    assert execution['steps'][2]['result']['queries'][-1]['args'] == dict(
        trip_id=trip_id, service_date=route['service_date'])
    actual_stops = stops[0]['output']['data']['stops']
    expected_stops = query.trip(trip_id, route['service_date'])['data']['stops']
    fields = ('stop_id', 'arrival_at', 'departure_at', 'sequence_index')
    assert [tuple(row.get(key) for key in fields) for row in actual_stops] == [
        tuple(row.get(key) for key in fields) for row in expected_stops]
    actual_pages = [row['output'] for row in execution['tool_evidence']
                    if row['tool'] == 'railway_query_trips' and row.get('executed') is True]
    assert [page['data'] for page in actual_pages[:2]] == [first['data'], second['data']]
    assert not {r['trip_id'] for r in first['data']} & {r['trip_id'] for r in second['data']}
    for row in actual_pages[-2:]:
        trip = row['data'][0]
        assert f"{trip['departure_at']}→{trip['arrival_at']}" in execution['steps'][-1]['result']['reply']
    for step in execution['steps']:
        assert all(step['db_metrics'][key] for key in ('foreign_keys_ok','inventory_conserved','money_conserved'))
        assert step['db_metrics']['order_count'] == step['db_metrics']['transaction_count'] == 0


@pytest.mark.parametrize('history,prompt,wanted', [
    ('absent', '下一页', None),
    ('failed', '下一页', None),
    ('terminal', '下一页', None),
    ('valid', '日期改为 2026-11-06', {'service_date': '2026-11-06'}),
    ('valid', '日期改为 2026-11-06 或 2026-11-07，出发站编码 AOH', None),
    ('valid', '不要翻页', None),
    ('valid', '下一页', {'service_date': '2026-11-05', 'cursor': '20'}),
])
def test_pagination_only_uses_valid_evidence(history, prompt, wanted):
    params = dict(origin_stop_id='AOH', destination_stop_id='HGH', service_date='2026-11-05')
    messages = []
    if history != 'absent':
        output = dict(status='FOUND', query_parameters=params, limit=20,
                      has_more=history != 'terminal', next_cursor='20' if history != 'terminal' else None)
        messages.extend([
            dict(role='user', content=FIRST),
            dict(role='tool', name='railway_query_trips', content=json.dumps(output)),
        ])
    if history == 'failed':
        messages.append(dict(role='tool', name='railway_query_trips', content='{"error":"DB_UNAVAILABLE"}'))
    reply = RailwayDemoProvider().chat([*messages, dict(role='user', content=prompt)], [])
    if wanted:
        assert reply['tool_calls'][0]['arguments'] == (params | {'limit':20} | wanted)
    else:
        assert not reply['tool_calls']


def test_gap_generation_reuses_quality_gate_and_preserves_review_and_ownership(tmp_path):
    session = source_session(tmp_path/'source')
    original = Workbench(session.sid)
    original.execute(session, FixtureModel([candidate()]))
    old_seal = (original.directory/'sha256.txt').read_bytes()
    report = inspect_run(original.run_id, session.sid, root=original.directory.parent)
    assert report['coverage']['total'] == 42
    assert report['coverage']['covered'] == 1
    assert report['coverage']['uncovered'] == 41
    assert report['disagreements'] == 0
    assert any(gap['status'] == 'NOT_RUN' and gap['feature'] == '并发性能' for gap in report['gaps'])
    assert not any(gap['status'] == 'PASS' for gap in report['gaps'])
    with pytest.raises(ValueError, match='INVALID_GAP_SELECTION'):
        select_gaps(report, ['forged'])
    with pytest.raises(ValueError, match='NOT_OWNED'):
        inspect_run(original.run_id, 'different', root=original.directory.parent)
    gap = next(row for row in report['gaps'] if row['feature'] == '跨轮记忆')
    supplement = Workbench(session.sid)
    plan = railway_candidate()
    plan['turns'] = plan['turns'][:2]
    plan['integration_steps'] = plan['integration_steps'][:2]
    model = FixtureModel([dict(plan, gap_id=gap['gap_id']), dict(candidate(), gap_id='forged')])
    manifest = supplement.execute(session, model, source_run_id=original.run_id, gap_ids=[gap['gap_id']])
    assert manifest['status'] == 'AWAITING_REVIEW'
    assert model.calls == ['generate']
    assert not list((supplement.directory/'executions').iterdir())
    case, plan = supplement.review_candidates()[0]
    assert case['gap_reference'] == dict(run_id=original.run_id, gap_id=gap['gap_id'],
                                         evidence_refs=gap['evidence_refs'])
    assert not plan['expect']
    assert Workbench.reopen(supplement.run_id, session.sid).review_candidates() == [(case, plan)]
    assert 'GAP_REFERENCE_NOT_SELECTED' in (supplement.directory/'cases.jsonl').read_text(encoding='utf8')
    assert (original.directory/'sha256.txt').read_bytes() == old_seal
    with pytest.raises(ValueError, match='HUMAN_APPROVAL'):
        supplement.approve([case['case_id']], model, actor='automatic')
    final = supplement.approve_and_execute([case['case_id']], model, actor='human', runner=_run_case)
    assert final['status'] == 'COMPLETED'
    assert model.calls == ['generate', 'judge-case-001']
    assert load_run_results(supplement.run_id, session.sid)['gap_source']['run_id'] == original.run_id
