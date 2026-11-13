import json

import pytest

from target.scenario_workbench import ModelReply, Workbench, _generator_prompt
from test_scenario_workbench import FixtureModel, candidate, source_session
from test_v3111_judge import wire


def test_generator_prompt_exposes_exact_read_only_contract(tmp_path):
    source=source_session(tmp_path/'source')
    from target.scenario_workbench_evidence import snapshot_conversation
    system,user=_generator_prompt(snapshot_conversation(source))
    packet=json.loads(user)
    assert '只允许字面空对象 {}' in system
    assert '严禁用 result.queries 检查 search_policy' in system
    assert 'confirm' not in packet['packet']['v310_contract']['step_kinds']
    assert 'railway_create_order' not in packet['packet']['v310_contract']['tool_schemas']
    assert packet['conversation']['turns'][0]['user']==source.history[0]['user_msg']


@pytest.mark.parametrize('value,error',[
    ('','empty_response'), ('not JSON','invalid_json'), ('{}','invalid_envelope'),
    (json.dumps({'scenarios':[]}), 'invalid_envelope'),
])
def test_invalid_response_is_preserved_with_separate_diagnostics(tmp_path,value,error):
    class Bad(FixtureModel):
        def __call__(self,*args,**kwargs):
            return ModelReply(value,'test-only','fixture-request',{},0)
    workbench=Workbench('web-c-source',root=tmp_path)
    manifest=workbench.execute(source_session(tmp_path/'source'),Bad([]),review_required=True)
    assert manifest['status']=='FAILED' and manifest['stages'][2]['status']=='WAITING'
    receipt=json.loads((workbench.directory/'generation-response.json').read_text(encoding='utf8'))
    assert receipt['text']==value
    diagnostics=json.loads((workbench.directory/'generation-diagnostics.json').read_text(encoding='utf8'))
    assert diagnostics['error']==error and diagnostics['counts']['retained']==0


def test_every_rejected_candidate_has_its_own_reason_and_original_payload(tmp_path):
    missing=candidate()
    del missing['title']
    old=candidate() | {'expect':{'reply_contains':'irrelevant'}}
    unknown=candidate() | {'integration_steps':[{'kind':'tool','tool':'fictional_tool','args':{},
        'checks':[{'path':'result.status','op':'eq','value':'FOUND'}]}]}
    workbench=Workbench('web-c-source',root=tmp_path)
    run=workbench.execute(source_session(tmp_path/'source'),FixtureModel([missing,old,unknown]),review_required=True)
    assert run['stages'][1]['error']=='C_WORKBENCH_NO_EXECUTABLE_CASES'
    report=json.loads((workbench.directory/'generation-diagnostics.json').read_text(encoding='utf8'))
    assert report['counts']==dict(raw_candidates=3,parsed_candidates=3,schema_valid=0,executor_compatible=0,retained=0)
    for row,code in zip(report['rejected'],('TITLE_REQUIRED','V310_EXPECT_MUST_BE_EMPTY_OBJECT','TOOL_STEP_INVALID:0'),strict=True):
        assert code in row['errors']
    assert json.loads((workbench.directory/'raw-candidates.json').read_text(encoding='utf8'))==[missing,old,unknown]
    assert not (workbench.directory/'review.json').exists()


def test_old_failed_run_and_new_reviewable_generation_are_separate(tmp_path):
    session=source_session(tmp_path/'source')
    old=Workbench(session.sid,root=tmp_path)
    old.execute(session,FixtureModel([candidate() | {'expect':{'legacy':True}}]),review_required=True)
    preserved=(old.directory/'manifest.json').read_bytes()
    new=Workbench(session.sid,root=tmp_path)
    new.execute(session,FixtureModel([candidate()]),review_required=True)
    loaded=Workbench.reopen(new.run_id,session.sid,root=tmp_path)
    assert loaded.manifest['status']=='AWAITING_REVIEW'
    assert loaded.review_candidates()[0][0]['case_id']=='case-001'
    assert (old.directory/'manifest.json').read_bytes()==preserved
    assert not (new.directory/'execution-started').exists()


def test_two_dialogues_produce_distinct_grounded_test_contracts_with_fixture(tmp_path):
    from target.diagnostics import digest
    cases=[]
    for topic,tool,criterion in (('查上海到杭州的车次','railway_query_trips','上海'),
                               ('查询 P01 退票费率','search_policy','P01')):
        source=source_session(tmp_path/f'source-{tool}')
        source.history[0]['user_msg']=topic
        source.audits[0]['public_trace_sha256']=digest(source.history[0])
        class ContextFixture(FixtureModel):
            def __call__(self, system, user, **kwargs):
                message=json.loads(user)['conversation']['turns'][0]['user']
                assert message==topic
                item=candidate() | dict(objective=topic,turns=[message],
                    integration_steps=[dict(kind='chat',message=message,checks=[
                        dict(path='result.public_result.tool_sequence',op='contains',value=tool),
                        dict(path='result.reply',op='contains',value=criterion)])])
                return ModelReply(json.dumps({'scenarios':[item]}),'deterministic-fixture','mock-id',{},0)
        run=Workbench(source.sid,root=tmp_path)
        run.execute(source,ContextFixture([]),review_required=True)
        cases.append(run.review_candidates()[0])
    left,right=cases
    assert left[0]['objective']!=right[0]['objective']
    assert left[1]['integration_steps'][0]['message']!=right[1]['integration_steps'][0]['message']
    assert left[1]['integration_steps'][0]['checks']!=right[1]['integration_steps'][0]['checks']


@pytest.mark.parametrize('failure,category',[('timeout','timeout'),('limit','request_payload_limit'),(429,'rate_limited')])
def test_live_provider_failures_keep_generation_stage_and_audit(tmp_path, wire, failure, category, monkeypatch):
    import httpx
    from target import scenario_workbench as workbench_module
    called=[]
    def handler(request):
        called.append(request)
        if failure=='timeout':
            raise httpx.ReadTimeout('private details',request=request)
        return httpx.Response(429,json={'error':{'message':'private details'}})
    wire(handler)
    if failure=='limit':
        monkeypatch.setattr(workbench_module,'WORKBENCH_PAYLOAD_BYTES',4000)
    source=source_session(tmp_path/'source')
    run=Workbench(source.sid,root=tmp_path)
    manifest=run.execute(source,workbench_module.LiveWorkbenchModel('deepseek',authorized=True),review_required=True)
    assert manifest['status']=='FAILED'
    details=manifest['stages'][1]['error_details']
    assert details['category']==category and details['automatic_retry'] is False
    assert len(called)==(0 if failure=='limit' else 1)
    assert 'private' not in json.dumps(details)
    assert manifest['stages'][2]['status']=='WAITING'
    assert (run.directory/'generation-http.json').is_file()
