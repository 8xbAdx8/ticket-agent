import copy
import hashlib
import json
from pathlib import Path
import uuid
import pytest

from target.scenario_v310 import V310Adapter, validate
from target.scenario_plans import plans, candidate
from target.scenario_quality import coverage, quality
from target.scenario_generator import Store, ROOT, review, evidence, encode


@pytest.mark.parametrize('plan', plans(), ids=lambda p:p['title'])
def test_v310_business_plans(plan, monkeypatch):
    monkeypatch.setenv('TICKET_DISABLE_LOCAL_SECRETS', '1')
    result = V310Adapter().run(plan)
    assert result['status'] == 'passed', result['evidence_root']
    assert result['model_requests'] == 0
    assert all(s['verified'] for s in result['steps'])
    assert (Path(result['evidence_root'])/'run_events.jsonl').is_file()
    assert all(s['trace_id'] for s in result['steps'])


@pytest.mark.parametrize('fault,plan', [('wrong_arguments','lifecycle'),('missing_confirmation','lifecycle'),('missing_expiry','hold_expiry'),('ui_drift','railway_queries')])
def test_fault_detection(fault, plan):
    selected = next(p for p in plans() if p['title']==plan)
    result = V310Adapter().run(selected, fault=fault)
    assert result['status'] == 'failed', result['evidence_root']
    assert any(not c['ok'] for s in result['steps'] for c in s['checks'])


def test_plan_repository_approval_and_trace():
    store = Store(ROOT/'artifacts/runtime'/('ai-scenario-v2-test-'+uuid.uuid4().hex))
    case = candidate(plans()[0])
    assert review(case)['quality'] == 'PASS'
    store.save(case, 'deterministic test fixture')
    with pytest.raises(ValueError):
        store.run(case['case_id'], 1)
    store.decide([(case['case_id'],1)], 'APPROVED','synthetic-review-test')
    result=store.run(case['case_id'],2)
    assert result['status']=='passed'
    assert Store(store.root).runs()[0]['body']==result


@pytest.mark.parametrize('damage', ['token','tool','empty','actor','sql','clock'])
def test_unsupported_or_unsafe_plan_is_not_executable(damage):
    plan=copy.deepcopy(plans()[0])
    if damage=='token':plan['integration_steps'][0]['confirmation_token']='invented'
    elif damage=='tool':plan['integration_steps'][0]['tool']='railway_lock_seat'
    elif damage=='empty':plan['integration_steps'][0]['checks']=[]
    elif damage=='actor':plan['integration_steps']=[dict(kind='confirm',actor='model',approved=True,proposal='invented',checks=[dict(path='metrics.order_count',op='eq',value=0)])]
    elif damage=='sql':plan['integration_steps'][0]['kind']='sql'
    else:plan['integration_steps']=[dict(kind='advance',seconds=-1,checks=[dict(path='metrics.order_count',op='eq',value=0)])]
    result=V310Adapter().run(plan)
    assert result['status']=='NOT_EXECUTABLE'


def test_unexecuted_tools_and_candidates_do_not_increase_coverage():
    report=coverage([])
    assert report['tools']['numerator']==0
    assert report['tools']['denominator']==11
    assert report['models']['value']==0
    assert report['rag']['value'] is None
    assert report['defects']['display']=='N/A'
    assert quality([],[])['execution']['display']=='N/A'


def test_prompt_fits_existing_request_guard():
    from target.p2_generator import SYSTEM
    packet=evidence('业务状态一致性')
    assert len((SYSTEM+encode(packet)).encode('utf8'))<28000
    assert len(packet['registered_railway_tools'])==11
    assert packet['references']['target/v39/lifecycle.py']


def test_new_case_has_new_scene_and_database():
    a=V310Adapter().run(plans()[0]);b=V310Adapter().run(plans()[0])
    assert a['evidence_root']!=b['evidence_root']
    sa=a['steps'][-1]['snapshot']['state'];sb=b['steps'][-1]['snapshot']['state']
    assert sa['session_id']!=sb['session_id']
    assert sa['orders']==sb['orders']==[]


@pytest.mark.parametrize('field,value', [
    ('expected_tool_calls',['railway_lock_seat']),
    ('expected_tool_calls',['railway_pay_order']),
    ('preconditions',['paid order already exists']),
    ('expected_call_order',['railway_trip_stops','railway_search_stations']),
    ('assertions',{'must_call':['railway_pay_order']}),
    ('expect',{'must_call':['railway_pay_order']}),
])
def test_v310_review_rejects_unbound_declarations(field,value):
    case=candidate(plans()[0]);case[field]=value
    assert review(case)['quality']!='PASS'


def test_pay_false_receipt_cannot_pass_conserved_unchanged_database():
    result=V310Adapter().run(next(p for p in plans() if p['title']=='lifecycle'),fault='fake_payment_success')
    assert result['status']=='failed'
    last=result['steps'][-1]
    assert last['output']['status']=='PAID'
    assert last['snapshot']['db']['v39_orders'][0]['order_status']=='PENDING_PAYMENT'
    assert last['snapshot']['db']['v39_transactions']==[]
    assert last['snapshot']['metrics']['money_conserved']
    assert any(c['path']=='committed_confirmation_receipt' and not c['ok'] for c in last['checks'])


def test_inherited_live_environment_is_fixed_and_network_hard_blocked(monkeypatch):
    import os,socket
    from unittest.mock import patch
    monkeypatch.setenv('TICKET_TEST_MODE','0');monkeypatch.setenv('TICKET_DATA_MODE','live');monkeypatch.setenv('TICKET_RAILWAY_QUERY_ENABLED','1')
    attempted=[]
    def malicious(*args):
        attempted.append(dict(test=os.environ['TICKET_TEST_MODE'],source=os.environ['TICKET_DATA_MODE'],enabled=os.environ['TICKET_RAILWAY_QUERY_ENABLED']))
        socket.create_connection(('example.invalid',443))
    with patch('web.business_actions.invoke',malicious):
        result=V310Adapter().run(plans()[0])
    assert result['status']=='failed'
    assert attempted==[dict(test='1',source='fixture',enabled='0')]
    assert result['steps'][0]['error']=='RuntimeError'
    assert os.environ['TICKET_DATA_MODE']=='live'


def test_model_quality_uses_create_snapshot_not_current_revision():
    from target.scenario_quality import model_comparison
    store=Store(ROOT/'artifacts/runtime'/('ai-v2-quality-test-'+uuid.uuid4().hex))
    case=candidate(plans()[0]);store.save(case,'synthetic')
    edited=copy.deepcopy(case);edited['expected_tool_calls']=['railway_lock_seat']
    store.save(edited,'synthetic',1)
    generations=[dict(body=dict(provider='deepseek',cases=[case['case_id']]))]
    original=model_comparison(store.original_candidates(),generations)['deepseek']
    current=model_comparison(store.list(),generations)['deepseek']
    assert original['quality']['tools']['value']==1
    assert current['quality']['tools']['value']==0


def test_trace_coverage_requires_matching_execution_events(tmp_path):
    (tmp_path/'run_events.jsonl').write_text(json.dumps(dict(run_id='other',execution_id='other',event_type='scenario_step_finished')))
    result=dict(mode='deterministic_v310_integration',status='failed',execution_id='expected',evidence_root=str(tmp_path),steps=[dict(trace_id='expected',verified=False)])
    assert coverage([result])['trace']['numerator']==0


@pytest.mark.parametrize('damage',['expect','tools','alias'])
def test_malformed_saved_candidate_cannot_crash_review_or_quality(damage):
    case=candidate(plans()[0])
    if damage=='expect':case['expect']=[]
    elif damage=='tools':case['expected_tool_calls']=[{}]
    else:case['integration_steps'][0]['as']=['bad']
    assert review(case)['quality']=='REJECTED'
    assert quality([dict(body=case,status='PENDING')],[])['executable']['numerator']==0


def test_confirmation_proof_binds_exact_proposal_objects():
    from target.scenario_v310 import confirmation_proof,replay_proof
    result=V310Adapter().run(next(p for p in plans() if p['title']=='lifecycle'))
    assert result['status']=='passed'
    checked=set()
    for step in result['steps']:
        if step['kind']!='confirm':continue
        view=copy.deepcopy(step['snapshot'])
        proposal=next(p for p in view['db']['v39_proposals'] if p['state']=='CONFIRMED' and p['action'] not in checked)
        action=proposal['action'];checked.add(action)
        payload=json.loads(proposal['payload_json'])
        if action=='CREATE_ORDER':payload['passengers']=['wrong passenger']
        elif action=='PAY':payload['expected_total_fen']=1
        elif action=='REFUND':payload['_refund_preview']['items'][0]['item_id']='other passenger'
        elif action=='CHANGE':payload['target_quote_id']='other quote'
        else:continue
        proposal['payload_json']=json.dumps(payload)
        assert not confirmation_proof(proposal['proposal_id'],step['output'],view)
        if action=='REFUND':
            original=step['snapshot'];tampered=copy.deepcopy(step['output']);tampered['refund_fen']+=1
            assert replay_proof(proposal['proposal_id'],step['output'],original,original)
            assert not replay_proof(proposal['proposal_id'],tampered,original,original)
        if len(checked)==4:break
    assert checked=={'CREATE_ORDER','PAY','REFUND','CHANGE'}


@pytest.mark.parametrize('original,later,alias,receipt_status,current_status',[
    ('payment_replay',None,'create','PENDING_PAYMENT','PAID'),
    ('full_refund',None,'pay','PAID','CANCELLED'),
])
def test_old_receipt_replay_after_order_progression(original,later,alias,receipt_status,current_status):
    from target.scenario_plans import confirm,check
    plan=copy.deepcopy(next(p for p in plans() if p['title']==original))
    step=confirm(alias,'replayed_after_progress',receipt_status)
    step['checks'] += [check('state.orders.0.order_status',current_status)]
    plan['integration_steps'].append(step)
    result=V310Adapter().run(plan)
    assert result['status']=='passed',result['evidence_root']
    assert any(c.get('replay') for c in result['steps'][-1]['checks'])
