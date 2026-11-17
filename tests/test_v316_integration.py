import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from test_ai_scenario_v311 import sdk_env

from scripts import build_send_zip, launch_app
from target.acceptance_budget import active
from target.scenario_workbench import SEMANTIC_WEIGHTS, Workbench
from target.scenario_workbench_fixture import MockWorkbenchModel
from target.scenario_workbench_review import evaluate_candidate


def test_packaging_is_dry_by_default_and_preserves_licenses_and_data(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    destination = tmp_path/'destination'
    files = {'.env': b'not shipped', '.env.example': b'template', 'LICENSE.txt': b'license',
             'static.sqlite': b'data', 'source.py': b'print(1)'}
    for name, data in files.items():
        (source/name).write_bytes(data)
    assert build_send_zip.build(source, destination)['excluded'] == ['.env']
    assert not destination.exists()
    result = build_send_zip.build(source, destination, apply=True)
    with ZipFile(result['archive']) as archive:
        assert archive.testzip() is None
        assert '.env' not in archive.namelist()
        assert archive.read('LICENSE.txt') == files['LICENSE.txt']
        assert archive.read('static.sqlite') == files['static.sqlite']
    assert (source/'.env').read_bytes() == files['.env']


def test_desktop_uses_one_storage_profile_without_startup_requests(tmp_path, monkeypatch):
    monkeypatch.setattr('target.api_config.bootstrap', lambda root: None)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'local-test-placeholder')
    monkeypatch.setenv('TICKET_LAUNCHER_PROVIDER', 'deepseek')
    offline = launch_app.graphical_environment('offline', tmp_path)
    live = launch_app.graphical_environment('live', tmp_path)
    assert offline['AGENT_PROVIDER'] == 'mock' and live['AGENT_PROVIDER'] == 'deepseek'
    assert 'DEEPSEEK_API_KEY' not in offline
    for field in ('AGENT_DB_PATH', 'RAILWAY_SIM_DB_PATH', 'TICKET_UI_SESSION_ROOT', 'TICKET_WORKBENCH_RUN_ROOT'):
        assert offline[field] == live[field]
        assert not Path(live[field]).exists()


def test_workbench_reservation_and_reload_are_source_scoped(tmp_path):
    owner = Workbench.start('one', root=tmp_path)
    assert Workbench.latest('one', root=tmp_path) == owner.run_id
    assert Workbench.latest('two', root=tmp_path) is None
    with pytest.raises(ValueError, match='ALREADY_ACTIVE'):
        Workbench.start('one', root=tmp_path)
    with pytest.raises(ValueError, match='NOT_OWNED'):
        Workbench.reopen(owner.run_id, 'two', root=tmp_path)


def test_refresh_during_generation_cannot_reserve_a_second_run(tmp_path):
    from threading import Event
    from target.scenario_workbench import read_manifest
    from test_scenario_workbench import FixtureModel, candidate, source_session

    entered, release = Event(), Event()
    class SlowModel(FixtureModel):
        def __call__(self, *args, **kwargs):
            entered.set()
            assert release.wait(10)
            return super().__call__(*args, **kwargs)
    source = source_session(tmp_path/'source')
    model = SlowModel([candidate()])
    run = Workbench.start(source.sid, root=tmp_path)
    future = run.submit(run.execute, source, model, review_required=True)
    try:
        assert entered.wait(10)
        assert read_manifest(run.run_id, source.sid, root=tmp_path)['status'] == 'RUNNING'
        with pytest.raises(ValueError, match='ALREADY_ACTIVE'):
            Workbench.start(source.sid, root=tmp_path)
    finally:
        release.set()
    future.result(timeout=10)
    assert Workbench.reopen(run.run_id, source.sid, root=tmp_path).manifest['status'] == 'AWAITING_REVIEW'
    assert model.calls == ['generate']


def test_stage_budget_is_enforced_at_request_admission(tmp_path, monkeypatch):
    monkeypatch.setenv('TICKET_ACCEPTANCE_BATCH', str(tmp_path/'batch.sqlite'))
    monkeypatch.setenv('TICKET_ACCEPTANCE_HTTP_LIMIT', '1')
    batch = active()
    batch.initialize()
    batch.reserve('first', 'deepseek', {'max_tokens': 1}, b'first')
    with pytest.raises(Exception, match='acceptance_http_budget_exhausted'):
        active().reserve('second', 'bailian', {'max_tokens': 1}, b'second')


def test_candidate_review_rejects_unbound_evidence_and_low_safety():
    packet = {'scores': dict.fromkeys(SEMANTIC_WEIGHTS, 90), 'reason': 'Source turn',
              'uncertainty': '', 'evidence_refs': ['other-turn'], 'recommendation': 'accept'}
    workbench = SimpleNamespace(_model=lambda *args: (json.dumps(packet), {}))
    turn = {'turn_id': 'turn-001', 'user': 'question', 'reply': 'answer', 'execution_events': []}
    case = {'case_id': 'case-001', 'source_turn_ids': ['turn-001']}
    with pytest.raises(ValueError, match='INVALID_SEMANTIC_REVIEW'):
        evaluate_candidate(workbench, {'turns': [turn]}, case, {'integration_steps': []}, None, SEMANTIC_WEIGHTS)
    packet['evidence_refs'] = ['turn-001']
    packet['scores']['safety'] = 60
    result = evaluate_candidate(workbench, {'turns': [turn]}, case, {'integration_steps': []}, None, SEMANTIC_WEIGHTS)
    assert result['total'] == 88.5 and result['recommendation'] == 'revise'


def test_mock_fixture_uses_source_parameters_and_explicitly_labels_policy():
    args = dict(origin_stop_id='AOH', destination_stop_id='HGH', service_date='2026-11-06')
    train = dict(turn_id='turn-001', user='查车', public_tool_calls=[dict(tool='railway_query_trips', args=args)])
    policy = dict(turn_id='turn-002', user='退票超过48小时扣多少', public_tool_calls=[dict(tool='search_policy', args={})])
    cases = MockWorkbenchModel._candidates([train, policy])
    assert [(case['dimension'], case['source_turn_ids']) for case in cases] == [('RAG', ['turn-002']), ('工具调用', ['turn-001'])]
    assert any(check['value'] == '2026-11-06' for check in cases[1]['integration_steps'][0]['checks'])
    assert MockWorkbenchModel.source == 'deterministic_model_fixture'


@pytest.mark.parametrize('topic', ['railway', 'policy'])
def test_live_shaped_workflow_keeps_generation_review_and_judge_separate(tmp_path, monkeypatch, topic):
    from target.scenario_workbench import LiveWorkbenchModel, ModelReply, RUN_ROOT, _run_case, load_run_results
    from test_scenario_workbench import candidate, source_session

    session = source_session(tmp_path/'source')
    item = candidate()
    if topic == 'policy':
        message = '查询发车超过 48 小时退票手续费，并引用 P01。'
        session.history[0]['user_msg'] = message
        events = session.trace_dir/'run_events.jsonl'
        events.write_text(json.dumps(dict(session_id=session.sid, run_id='source', event_id='policy-event',
            event_type='tool_result', tool='search_policy', executed=True, output={'hits': [{'doc_id': 'P01'}]})), encoding='utf8')
        item = dict(item, title='核对退票政策引用', objective='验证政策检索与引用',
                    dimension='RAG', turns=[message], covered_nodes=['工具选择'],
                    integration_steps=[dict(kind='chat', message=message, checks=[
                        dict(path='result.public_result.tool_sequence', op='contains', value='search_policy'),
                        dict(path='result.reply', op='contains', value='P01')])])
    calls = []
    def model_reply(self, system, user, *, directory, run_id, step):
        packet = json.loads(user)
        calls.append((self.provider, step))
        if step == 'generate':
            selected = packet['conversation']['turns'][0]
            assert ('退票手续费' in selected['user']) == (topic == 'policy')
            result = {'scenarios': [item]}
        elif step.startswith('semantic-'):
            assert packet['executor_contract']['adapter'] == 'v310'
            paths = packet['executor_contract']['chat_check_paths']
            assert {'result.queries', 'metrics.order_count'} <= paths.keys()
            assert '以 executor_contract 为准' in system
            result = dict(scores=dict.fromkeys(SEMANTIC_WEIGHTS, 90), reason='检查源对话与车次参数断言',
                          evidence_refs=list(packet['evidence'])[:1], uncertainty='', recommendation='accept')
        else:
            assert packet['tool_events'] and packet['evidence'][0]['trace_id']
            result = dict(status='passed', reason='工具参数与零订单断言均可核验', evidence_refs=packet['refs'][-1:])
        return ModelReply(json.dumps(result, ensure_ascii=False), self.provider+'-stub', step, {'prompt': 1, 'completion': 1}, 1)

    monkeypatch.setattr(LiveWorkbenchModel, '__call__', model_reply)
    run = Workbench(session.sid, root=RUN_ROOT)
    generator = LiveWorkbenchModel('deepseek', authorized=True)
    judge = LiveWorkbenchModel('bailian', authorized=True)
    manifest = run.execute(session, generator, reviewer=judge, review_required=True, source_workspace='user')
    assert manifest['status'] == 'AWAITING_REVIEW'
    assert calls == [('deepseek', 'generate'), ('bailian', 'semantic-case-001')]
    assert not (run.directory/'execution-started').exists()
    run.approve(['case-001'], generator, actor='human')
    with pytest.raises(ValueError, match='VALID_APPROVAL'):
        run.execute_approved(generator, runner=_run_case)
    result = run.execute_approved(judge, runner=_run_case)
    assert result['status'] == 'COMPLETED'
    assert calls[-1] == ('bailian', 'judge-case-001')
    assert load_run_results(run.run_id, session.sid, root=RUN_ROOT)['executed'] == 1


@pytest.mark.parametrize('provider', ['deepseek', 'bailian'])
def test_live_http_failure_has_its_own_ledger_without_mock_fallback(provider, tmp_path, monkeypatch, sdk_env):
    import importlib
    import httpx
    from target.scenario_workbench import LiveWorkbenchModel, WorkbenchModelError
    from target.acceptance_budget import Batch

    module = importlib.import_module('target.'+provider+'_runtime')
    original = module.make_model
    requests = []
    def respond(request):
        requests.append(request.url.host)
        return httpx.Response(429, json={'error': {'message': 'fixture throttled'}})
    monkeypatch.setattr(module, 'make_model', lambda settings: original(settings, transport=httpx.MockTransport(respond)))
    model = LiveWorkbenchModel(provider, authorized=True, request_limit=1)
    with pytest.raises(WorkbenchModelError) as failure:
        model('return JSON', '{}', directory=tmp_path, run_id='test-fixture', step='generate')
    assert failure.value.details['http_status'] == 429
    assert len(requests) == 1
    assert Batch(tmp_path/'model-budget.sqlite', max_http=1).snapshot()['http_requests'] == 1
    assert (tmp_path/'generation-http.json').is_file()


def test_m1_experiment_runs_from_boundary_board_and_keeps_trace(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    import config
    from web import runtime
    from web.evidence import read_audit_records
    monkeypatch.delenv('TICKET_UI_SESSION_ROOT', raising=False)
    monkeypatch.setenv('RAILWAY_SIMULATION_ENABLED', '0')
    monkeypatch.setenv('TICKET_WEB_OFFLINE_ONLY', '1')
    monkeypatch.setattr(config, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(runtime, 'ROOT', tmp_path)
    overview = AppTest.from_string('from web.consistency_audit_view import competition_page\ncompetition_page([])').run()
    assert not any(box.key == 'lab_mutation_date_offset' for box in overview.checkbox)
    app = AppTest.from_string('from web.consistency_audit_view import lab_page\nlab_page()').run()
    app.checkbox(key='lab_mutation_date_offset').check().run()
    next(button for button in app.button if button.label == '执行测试').click().run()
    assert not app.exception
    session = app.session_state['lab_session']
    rows, errors = read_audit_records(session.trace_dir/'audit_runs.jsonl')
    assert not any(errors.values()) and len(rows) == 1
    assert rows[0]['fault_report']['mutations'] == {'date_offset': 1}
    assert any(event['mutation_id'] == 'M1' and event['status'] == 'applied' for event in rows[0]['mutation_events'])
