import json

import httpx
import pytest

from target import deepseek_runtime
from target.acceptance_budget import Batch
from target.scenario_workbench import (RUN_ROOT, LiveWorkbenchModel, Workbench, WorkbenchModelError,
                                       _run_case, load_run_results)
from test_scenario_workbench import candidate, source_session


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.delenv('TICKET_WEB_OFFLINE_ONLY', raising=False)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'offline-mock-credential')
    monkeypatch.setenv('DEEPSEEK_MODEL', 'deepseek-flash')
    monkeypatch.setenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    make = deepseek_runtime.make_model

    def install(handler):
        monkeypatch.setattr(deepseek_runtime, 'make_model',
                            lambda settings: make(settings, transport=httpx.MockTransport(handler)))
    return install


def reply(content):
    return httpx.Response(200, json={'id':'fake-response','object':'chat.completion','created':0,
        'model':'deepseek-flash','choices':[{'index':0,'finish_reason':'stop',
        'message':{'role':'assistant','content':content}}],
        'usage':{'prompt_tokens':20,'completion_tokens':5,'total_tokens':25}})


@pytest.mark.parametrize('outcome,category,status',[
    ('ok',None,None), ('connection','network_connection',None), ('timeout','timeout',None),
    (401,'authentication_failed',401), (403,'permission_denied',403), (429,'rate_limited',429),
    (500,'server_error',500), (503,'service_unavailable',503), ('empty','empty_response',200),
    ('bad-http-json','invalid_response',200),
])
def test_workbench_deepseek_http_failure_diagnostics(tmp_path, wire, outcome, category, status):
    sent = []
    def dispatch(request):
        sent.append(request.url.path)
        if outcome=='connection':
            raise httpx.ConnectError('private connection info',request=request)
        if outcome=='timeout':
            raise httpx.ReadTimeout('private timeout info',request=request)
        if isinstance(outcome,int):
            return httpx.Response(outcome, json={'error':{'message':'private API detail'}})
        if outcome=='bad-http-json':
            return httpx.Response(200, content=b'not JSON', headers={'Content-Type':'application/json'})
        return reply('' if outcome=='empty' else '{"status":"passed"}')
    wire(dispatch)
    model=LiveWorkbenchModel('deepseek',authorized=True)
    if category:
        with pytest.raises(WorkbenchModelError) as caught:
            model('system','user',directory=tmp_path,run_id='a'*32,step='generate')
        details=caught.value.details
        assert details['category']==category and details['http_status']==status
        assert details['dispatched'] and not details['automatic_retry']
        assert details['request_id'] and details['elapsed_ms']>=0
        assert 'private' not in json.dumps(details)
    else:
        result=model('system','user',directory=tmp_path,run_id='a'*32,step='generate')
        assert result.token_usage=={'prompt':20,'completion':5}
    assert len(sent)==1
    assert Batch(tmp_path/'model-budget.sqlite').snapshot()['http_requests']==1


def test_oversize_payload_is_local_rejection_before_dispatch(tmp_path, wire):
    def dispatch(request):
        pytest.fail('oversized packet reached Mock HTTP transport')
    wire(dispatch)
    model=LiveWorkbenchModel('deepseek',authorized=True)
    Batch(tmp_path/'model-budget.sqlite').initialize()
    (tmp_path/'prompts').mkdir()
    with pytest.raises(WorkbenchModelError) as caught:
        model('judge','x'*131235,directory=tmp_path,run_id='a'*32,step='judge-case-001')
    assert caught.value.details['category']=='request_payload_limit'
    assert caught.value.details['http_status'] is None and not caught.value.details['dispatched']
    assert Batch(tmp_path/'model-budget.sqlite').snapshot()['http_requests']==0


@pytest.mark.parametrize('bad,category',[('not-json','invalid_json'), ('{}','invalid_judge_structure')])
def test_only_judge_is_recovered_with_original_execution_and_approval(tmp_path,wire,bad,category):
    session=source_session(tmp_path/'source')
    workbench=Workbench(session.sid,root=tmp_path)
    model=LiveWorkbenchModel('deepseek',authorized=True)
    calls=[]
    def dispatch(request):
        messages=json.loads(request.content)['messages']
        system,user=(x['content'] for x in messages)
        if len(calls)==0:
            calls.append('generate')
            return reply(json.dumps({'scenarios':[candidate()]}))
        calls.append('judge')
        assert len(request.content)<=64000
        payload=json.loads(user)
        assert 'evidence_limits' in payload and payload['evidence'][0]['checks']
        assert payload['evidence'][0]['tool_result']['detail_omitted']
        return reply(bad if len(calls)==2 else json.dumps(dict(status='passed', reason='verified',
                                                             evidence_refs=payload['refs'])))
    wire(dispatch)
    run_calls=[]
    def runner(case, plan, directory, engine):
        run_calls.append(case['case_id'])
        cid=case['case_id']
        row=dict(run_id=workbench.run_id,case_id=cid,executed=True,agent_invoked=True,
                 ref=f'executions/{cid}.json',agent_trace_refs=['run_events.jsonl#event-1'],
                 steps=[dict(kind='tool',trace_id='local-trace',result={'reply':'result','data':['x'*90000]},
                             checks=[{'passed':True}],state={},db_metrics={})],
                 retrieval_evidence=[],tool_evidence=[],objective_status='passed')
        return row,[dict(event_id='event-1',event_type='tool_result')]
    workbench.execute(session,model,review_required=True)
    workbench.approve(['case-001'],model,actor='human')
    first=workbench.execute_approved(model,runner=runner)
    assert [s['status'] for s in first['stages']]==['COMPLETED']*3+['FAILED','WAITING']
    assert first['stages'][3]['error_details']['category']==category
    protected={p:p.read_bytes() for p in workbench.directory.glob('*.json*') if p.name!='manifest.json'}
    assert workbench.judge_recovery_available()
    reopened=Workbench.reopen(workbench.run_id,session.sid,root=tmp_path)
    target=workbench.directory/'executions/case-001.json'
    original=target.read_bytes()
    target.write_bytes(original+b'\n')
    with pytest.raises(ValueError,match='EVIDENCE_INTEGRITY_ERROR'):
        reopened.recover_judge(model)
    target.write_bytes(original)
    assert calls==['generate','judge']
    result=reopened.recover_judge(model)
    assert result['status']=='COMPLETED', result
    assert all(s['status']=='COMPLETED' for s in result['stages'])
    assert calls==['generate','judge','judge'] and run_calls==['case-001']
    assert all(p.read_bytes()==data for p,data in protected.items())
    assert load_run_results(workbench.run_id,session.sid,root=tmp_path)['executed']==1
    with pytest.raises(ValueError,match='RECOVERY_UNAVAILABLE'):
        reopened.recover_judge(model)


@pytest.mark.parametrize('references', [{}, {'evidence_refs': []}, {'evidence_refs': ['another-run.json']}])
def test_unsubstantiated_judge_cannot_hide_completed_objective_results(tmp_path, wire, references):
    session = source_session(tmp_path/'source')
    workbench = Workbench(session.sid, root=RUN_ROOT)
    model = LiveWorkbenchModel('deepseek', authorized=True)
    calls = []

    def dispatch(request):
        payload = json.loads(request.content)
        assert payload['response_format'] == {'type': 'json_object'}
        calls.append(payload)
        if len(calls) == 1:
            return reply(json.dumps({'scenarios': [candidate()]}))
        system, user = (row['content'] for row in payload['messages'])
        case_ref = json.loads(user)['refs'][0]
        example = system.split('输出结构示例（状态和理由按实际证据填写）：', 1)[1].splitlines()[0]
        assert json.loads(example)['evidence_refs'] == [case_ref]
        assert '三个字段均必填' in system
        return reply(json.dumps(dict(status='passed', reason='未经引用支持的结论', **references)))

    wire(dispatch)
    workbench.execute(session, model, review_required=True)
    workbench.approve(['case-001'], model, actor='human')
    result = workbench.execute_approved(model, runner=_run_case)
    assert result['status'] == 'COMPLETED', result['stages']
    raw = json.loads((workbench.directory/'judgements.jsonl').read_text(encoding='utf8'))
    assert raw['status'] == 'indeterminate'
    assert raw['request_id'] and raw['response_sha256']
    summary = load_run_results(workbench.run_id, session.sid, root=RUN_ROOT)
    assert summary['executed'] == summary['normal_quality']['objective']['passed'] == 1
    assert summary['normal_quality']['judge_rate']['denominator'] == 0
    if not references.get('evidence_refs'):
        assert raw['evidence_refs'] == []
        assert summary['evidence_rate']['numerator'] == 0
        assert summary['judge_missing_evidence_refs'] == 1
    else:
        assert 'another-run.json' not in raw['evidence_refs']
        assert summary['judge_missing_evidence_refs'] == 0
    assert len(calls) == Batch(workbench.directory/'model-budget.sqlite').snapshot()['http_requests'] == 2
