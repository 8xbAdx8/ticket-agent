from copy import deepcopy
from dataclasses import replace
import pytest
from tests.v39.test_service import sim,create
from target.v39.business_claim_guard import check,claims


@pytest.fixture(autouse=True)
def isolate_trusted_contexts():
    from target.execution_config import scope as effective
    from target.v39.context import scope
    from target.v39.registry import service_scope
    with effective(None),scope(None),service_scope(None):yield


def event(tool,result,**kw):return dict(event='tool_end',tool=tool,executed=True,ok=True,result=result,call_id='test-call',args={},**kw)


@pytest.mark.parametrize('text',['尚未锁定。','还没有锁座。','如果确认，下一步将锁座。','是否需要锁座？','用户引用的「已锁定」。','历史订单之前已支付。'])
def test_not_current_success_claim(text):assert claims(text)==[]


@pytest.mark.parametrize('tool,result,text',[
    ('railway_check_inventory',dict(status='SIMULATED_AVAILABLE',available=8),'G7503已锁定。'),
    ('railway_quote_fare',dict(status='QUOTED',quote=dict(quote_id='Qfake')),'已创建订单。'),
    ('railway_create_order',dict(proposal_id='Pfake',status='PENDING'),'已锁座，已创建订单，已支付。')])
def test_observation_or_proposal_is_not_completed_transaction(sim,tool,result,text):
    service,ctx=sim
    assert check(text,[event(tool,result)],ctx,service.store.path,service.now())['status']=='blocked'


@pytest.mark.parametrize('alter',['executed_false','failed','wrong_user','wrong_session','wrong_seat','wrong_train','db_mismatch'])
def test_only_matching_executed_owned_persistent_state_supports_success(sim,alter):
    service,ctx,proposal,result=create(sim);order=service.order(ctx,result['order_id'])
    e=event('railway_get_order',order);text='已创建订单。'
    if alter=='executed_false':e['executed']=False
    elif alter=='failed':e['ok']=False
    elif alter=='wrong_user':ctx=replace(ctx,owner_phone='OTHER')
    elif alter=='wrong_session':ctx=replace(ctx,session_id='OTHER')
    elif alter=='wrong_seat':text='商务座已创建订单。'
    elif alter=='wrong_train':text='G9999已创建订单。'
    elif alter=='db_mismatch':e['result']=dict(order,order_status='PAID')
    assert check(text,[e],ctx,service.store.path,service.now())['status']=='blocked'


def test_actual_confirmed_create_hold_pay_refund_change_states(sim):
    service,ctx,p,result=create(sim);order=service.order(ctx,result['order_id'])
    e=event('railway_get_order',order)
    assert check('已创建订单。已锁座。',[e],ctx,service.store.path,service.now())['status']=='supported'
    assert check('已支付。',[e],ctx,service.store.path,service.now())['status']=='blocked'
    p=service.propose(ctx,'PAY',dict(order_id=order['order_id'],expected_total_fen=6000));service.confirm(ctx,p['proposal_id'])
    paid=service.order(ctx,order['order_id'])
    assert check('已支付。',[event('railway_get_order',paid)],ctx,service.store.path,service.now())['status']=='supported'


def test_real_quote_expiry_and_object_integrity(sim):
    from datetime import timedelta
    service,ctx=sim
    result=service.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)
    e=event('railway_quote_fare',result)
    assert check('已生成报价。',[e],ctx,service.store.path,service.now())['status']=='supported'
    assert check('已生成报价。',[e],ctx,service.store.path,service.now()+timedelta(hours=1))['status']=='blocked'
    changed=deepcopy(e);changed['result']['quote']['total_fen']=1
    assert check('已生成报价。',[changed],ctx,service.store.path,service.now())['status']=='blocked'


def test_request_train_identity_cannot_be_replaced_by_other_order(sim):
    service,ctx,p,result=create(sim);order=service.order(ctx,result['order_id'])
    assert check('已创建订单。',[event('railway_get_order',order)],ctx,service.store.path,service.now(),resolve_train=lambda t,d:'G2',user_message='我想买G1的票')['status']=='blocked'


def test_confirmed_change_full_refund_cancel_and_no_false_full_amount(sim):
    from tests.v39.test_lifecycle import target
    service,ctx,p,result=create(sim);oid=result['order_id']
    p=service.propose(ctx,'PAY',dict(order_id=oid,expected_total_fen=6000));service.confirm(ctx,p['proposal_id'])
    p=service.propose(ctx,'CHANGE',target(service,ctx,oid,trip_id='T2'));service.confirm(ctx,p['proposal_id'])
    order=service.order(ctx,oid)
    assert check('已改签。',[event('railway_get_order',order)],ctx,service.store.path,service.now())['status']=='supported'
    p=service.propose(ctx,'REFUND',dict(order_id=oid,scope='FULL'));service.confirm(ctx,p['proposal_id'])
    order=service.order(ctx,oid)
    assert check('已全部退款。已取消订单。',[event('railway_get_order',order)],ctx,service.store.path,service.now())['status']=='supported'
    assert check('已全额退款。',[event('railway_get_order',order)],ctx,service.store.path,service.now())['status']=='blocked'


def test_actual_runtime_guard_replaces_false_lock_with_verified_unknown(sim):
    from target.v39.context import scope
    from target.v39.registry import service_scope
    from target.v39.business_claim_guard import apply
    service,ctx=sim
    with scope(ctx),service_scope(service):reply,assessment=apply('G7503已锁定。',[],user_message='我想买G7503')
    assert assessment['status']=='blocked' and '锁座：尚无成功证据' in reply
    assert 'G7503已锁定' not in reply


class TruncatedProvider:
    name='scripted_mock'
    last_usage={'prompt':10,'completion':5}
    def chat(self,messages,tools):return dict(role='assistant',content='已支付成功',tool_calls=[],finish_reason='length')


@pytest.mark.parametrize('engine',['legacy','langchain'])
def test_truncated_result_is_not_success_and_keeps_public_contract(engine,monkeypatch):
    from target.agent import Agent
    from target.langchain_model import LangChainMockModel
    monkeypatch.setenv('RAILWAY_SIMULATION_ENABLED','0')
    provider=TruncatedProvider()
    agent=Agent(provider=provider,engine=engine,model=LangChainMockModel(decision_provider=provider) if engine=='langchain' else None)
    result=agent.chat('length-'+engine,'你好',save_trace=False)
    assert len(result)==10 and result['finish_reason']=='stop'
    assert '截断' in result['reply'] and '已支付成功' not in result['reply']
    audit=agent.last_audit_report
    assert audit['error']['category']=='model_output_truncated'
    if engine=='langchain':
        assert any(e.get('event')=='output_truncated' and e.get('original_model_reply')=='已支付成功' for e in agent.langchain_engine.last_events)
