import hashlib
import io
import json
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from streamlit.testing.v1 import AppTest

from target.diagnostics import digest
from target.scenario_plans import plans
from target.scenario_workbench import ModelReply, Workbench, export_bundle, load_run_results
from target.scenario_workbench_evidence import snapshot_conversation
from target.scenario_workbench_summary import DIMENSIONS, NODES, summarize


def source_session(path, *, sid='web-c-source'):
    path.mkdir(exist_ok=True)
    conversation = next(row for row in plans() if row['title'] == 'conversation')
    public = dict(session_id=sid, user_msg=conversation['integration_steps'][0]['message'],
                  reply='查询时刻', steps=[])
    (path / 'run_events.jsonl').write_text('\n'.join(json.dumps(row) for row in (
        dict(session_id=sid, run_id='source', event_id='a', event_type='railway_tool_result', tool='railway_query_trips'),
        dict(session_id='foreign', run_id='source', event_id='b', event_type='railway_tool_result', output='foreign'))),
        encoding='utf8')
    return SimpleNamespace(sid=sid, mode='user', live=False, engine='legacy', trace_dir=path,
                           history=[public, dict(public, session_id='foreign', reply='foreign')],
                           audits=[dict(public_trace=public, public_trace_sha256=digest(public), trace_id='source')])


def candidate():
    plan = next(row for row in plans() if row['title'] == 'conversation')
    steps = plan['integration_steps'][:1]
    return dict(title='核对日期与车站参数', objective='验证查询参数', risk_level='low', difficulty='medium',
                turns=[steps[0]['message']], expected_behavior='answer', expect={}, execution_adapter='v310',
                integration_steps=steps, expected_tool_calls=[], expected_state_changes=[], dimension='工具调用',
                source_turn_ids=['turn-001'], covered_nodes=['工具选择', '参数构造'])


class FixtureModel:
    source = 'deterministic_model_fixture'

    def __init__(self, items, *, bad_ref=False):
        self.items = items
        self.bad_ref = bad_ref
        self.calls = []

    def __call__(self, system, user, *, directory, run_id, step):
        body = json.loads(user)
        self.calls.append(step)
        if step == 'generate':
            assert body['conversation']['turns'][0]['run_id'] == 'source'
            result = dict(scenarios=self.items)
        else:
            assert body['evidence'][0]['trace_id'] and body['evidence'][0]['reply']
            result = dict(status='passed', reason='测试替身的结构化判定',
                          evidence_refs=['another-run.json'] if self.bad_ref else body['refs'][-1:])
        return ModelReply(json.dumps(result, ensure_ascii=False), 'fixed-test-fixture',
                          'fixture-' + step, dict(prompt=None, completion=None), 1)


def test_snapshot_binds_only_current_conversation_and_redacts(tmp_path):
    session = source_session(tmp_path / 'source')
    session.history[0]['user_msg'] += '，名字叫合成甲。'
    session.audits[0]['public_trace_sha256'] = digest(session.history[0])
    snapshot = snapshot_conversation(session)
    assert len(snapshot['turns']) == 1
    assert [row['event_id'] for row in snapshot['turns'][0]['execution_events']] == ['a']
    assert '合成甲' not in snapshot['turns'][0]['user']
    assert 'foreign' not in json.dumps(snapshot)
    with pytest.raises(ValueError, match='USER_SESSION_REQUIRED'):
        snapshot_conversation(SimpleNamespace(**(vars(session) | {'mode': 'lab'})))


def test_invalid_cases_gate_and_preserve_failed_evidence(tmp_path):
    session = source_session(tmp_path / 'source')
    model = FixtureModel([dict(candidate(), source_turn_ids=['other']), dict(candidate(), execution_adapter='p2')])
    workbench = Workbench(session.sid, root=tmp_path)
    result = workbench.execute(session, model)
    assert result['status'] == 'FAILED'
    assert result['stages'][1]['error'] == 'C_WORKBENCH_NO_EXECUTABLE_CASES'
    assert model.calls == ['generate']
    assert (workbench.directory / 'cases.jsonl').is_file()
    assert not (workbench.directory / 'summary.json').exists()
    with pytest.raises(ValueError, match='INCOMPLETE'):
        load_run_results(workbench.run_id, session.sid, root=tmp_path)


@pytest.mark.parametrize('engine,bad_ref', [('legacy', False), ('langchain', True)])
def test_real_offline_agent_single_run_dual_tracks_and_export(tmp_path, engine, bad_ref):
    session = source_session(tmp_path / 'source')
    session.engine = engine
    model = FixtureModel([candidate(), candidate()], bad_ref=bad_ref)
    workbench = Workbench(session.sid)
    manifest = workbench.execute(session, model)
    assert manifest['status'] == 'COMPLETED', manifest
    summary = load_run_results(workbench.run_id, session.sid)
    assert summary['run_id'] == workbench.run_id
    assert (summary['generated'], summary['validated'], summary['executed']) == (2, 1, 1)
    assert (summary['normal_quality']['objective'], summary['normal_quality']['judge']) == (
        {'passed': 1}, {'indeterminate': 1} if bad_ref else {'passed': 1})
    assert summary['coverage_rate']['denominator'] == len(DIMENSIONS) * len(NODES) == 42
    assert summary['coverage_rate']['numerator'] >= 1
    assert model.calls == ['generate', 'judge-case-001']
    result = json.loads((workbench.directory / 'executions/case-001.json').read_text(encoding='utf8'))
    assert result['engine'] == engine and result['agent_trace_refs']
    assert all(row['db_metrics']['order_count'] == 0 for row in result['steps'])
    assert result['steps'][0]['result']['queries'][0]['tool'] == 'railway_query_trips'
    usage = json.loads((workbench.directory / 'prompts/generate.json').read_text(encoding='utf8'))
    assert usage['token_usage'] == {'prompt': None, 'completion': None}
    assert usage['prompt_sha256'] == hashlib.sha256(usage['prompt'].encode()).hexdigest()
    archive = export_bundle(workbench.run_id, session.sid)
    with ZipFile(io.BytesIO(archive)) as bundle:
        assert len(bundle.namelist()) == 5
        for line in bundle.read('sha256.txt').decode().splitlines():
            sha, name = line.split('  ')
            assert hashlib.sha256(bundle.read(name)).hexdigest() == sha
    with pytest.raises(ValueError, match='NOT_OWNED'):
        load_run_results(workbench.run_id, 'another-session')
    app = AppTest.from_string('''import streamlit as st
from web.consistency_audit_view import competition_page, quality_page, rag_page, lab_page, trace_page
pages = [competition_page, quality_page, rag_page, lab_page, trace_page]
args = [(st.session_state.user_sessions,), (st.session_state.user_sessions,), (st.session_state.user_sessions,), (), ([],)]
pages[st.session_state.board](*args[st.session_state.board])''')
    app.session_state['user_sessions'] = [session]
    app.session_state['c_workbench_pointer'] = {'session_id': session.sid, 'run_id': workbench.run_id}
    for board in range(5):
        app.session_state['board'] = board
        app.run(timeout=20)
        assert not app.exception
        assert any(workbench.run_id in caption.value for caption in app.caption)
        if board:
            assert not app.button
    app.session_state['user_sessions'] = [source_session(tmp_path / 'other', sid='web-another')]
    app.run(timeout=20)
    assert any('请先在' in info.value for info in app.info)


def test_summary_never_turns_an_injected_defect_into_a_business_pass():
    from target.diagnostics import IDS
    cases = [dict(case_id=code, title=kind, validated=True, dimension='边界', mutation=kind,
                  boundary='输入不完整', covered_nodes=['工具选择']) for kind, code in IDS.items()]
    executions = [dict(case_id='M1', executed=True, agent_invoked=True, objective_status='passed',
                       verified_nodes=['工具选择'], mutation_status='missed', ref='probe.json')]
    result = summarize('run', cases, executions, [], [])
    assert len(result['mutations']) == 8 and result['mutations'][0]['missed'] == 1
    assert result['mutations'][1]['rate']['value'] is None
    assert result['normal_quality']['objective_rate']['value'] is None
    assert result['injected_quality']['executed'] == 1
    assert sum(cell['passed'] for cell in result['coverage_matrix']) == 0
    assert result['coverage_rate']['numerator'] == 1


def test_completed_manifest_with_modified_summary_is_rejected(tmp_path):
    session = source_session(tmp_path / 'source')
    workbench = Workbench(session.sid, root=tmp_path)
    workbench.manifest['status'] = 'COMPLETED'
    workbench._manifest()
    (workbench.directory / 'summary.json').write_text('{}', encoding='utf8')
    (workbench.directory / 'sha256.txt').write_text('0' * 64 + '  summary.json\n', encoding='utf8')
    with pytest.raises(ValueError, match='INTEGRITY'):
        load_run_results(workbench.run_id, session.sid, root=tmp_path)


def test_m8_uses_real_isolated_probe_and_keeps_normal_rate_empty(tmp_path):
    session = source_session(tmp_path / 'source')
    item = dict(candidate(), dimension='边界', mutation='concurrent_duplicate_order', boundary='并发与重复')
    workbench = Workbench(session.sid)
    result = workbench.execute(session, FixtureModel([item]))
    assert result['status'] == 'COMPLETED', result
    summary = load_run_results(workbench.run_id, session.sid)
    assert summary['mutations'][-1]['detected'] == 1
    assert summary['performance']['concurrency'][0]['workers'] == 2
    assert summary['normal_quality']['objective_rate']['value'] is None
    assert summary['boundaries'][3]['injected'] == 1


def test_offline_and_unauthorized_model_requests_stop_before_dispatch(monkeypatch, tmp_path):
    from target.scenario_workbench import LiveWorkbenchModel
    with pytest.raises(ValueError, match='AUTHORIZATION_REQUIRED'):
        LiveWorkbenchModel('deepseek', authorized=False)
    model = LiveWorkbenchModel('deepseek', authorized=True)
    monkeypatch.setenv('TICKET_WEB_OFFLINE_ONLY', '1')
    with pytest.raises(ValueError, match='OFFLINE_ONLY'):
        model('prompt', 'user', directory=tmp_path, run_id='fake', step='generate')
    assert not (tmp_path / 'model-budget.sqlite').exists()
