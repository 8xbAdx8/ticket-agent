"""Objective state/receipt checks against actual isolated SQLite, not response prose."""
import copy,json,uuid
from datetime import timedelta
from dataclasses import replace
import pytest
from tests.v39.test_service import sim,create
from tests.v39.test_lifecycle import assert_conserved,target,run
from target.v39.read_model import read
from target.execution_config import scope


@pytest.fixture(autouse=True)
def own_context():
    with scope(None):yield


def test_read_model_is_owned_single_snapshot_and_does_not_expire(sim):
    s,ctx,p,created=create(sim)
    before=s.store.path.read_bytes()
    snap=read(s.store.path,ctx,now=s.now()+timedelta(days=9))
    o=snap['orders'][0]
    assert o['order_status']=='PENDING_PAYMENT' and o['hold_expired_at_read']
    assert len(o['passenger_ids'])==3 and o['hold']['remaining_quantity']==3
    assert s.store.path.read_bytes()==before
    assert read(s.store.path,replace(ctx,session_id='other'),now=s.now())['orders']==[]
    with pytest.raises(ValueError,match='ORDER_FORBIDDEN'):read(s.store.path,replace(ctx,owner_phone='other'),order_id=created['order_id'])


def test_full_lifecycle_receipts_and_committed_snapshot_conserve(sim):
    s,ctx,p,created=create(sim);oid=created['order_id']
    paid=run(s,ctx,'PAY',order_id=oid,expected_total_fen=6000)
    snap=read(s.store.path,ctx,now=s.now());o=snap['orders'][0]
    assert o['order_status']=='PAID' and o['payment_status']=='SUCCEEDED' and o['ledger_verified']
    first=o['items'][0]['item_id']
    run(s,ctx,'REFUND',order_id=oid,scope='ITEMS',item_ids=[first])
    run(s,ctx,'CHANGE',**target(s,ctx,oid,trip_id='T2',seat_class='FIRST'))
    snap=read(s.store.path,ctx,now=s.now());o=snap['orders'][0]
    assert o['order_status']=='CHANGED' and len(o['passenger_ids'])==2
    assert o['ledger_verified'] and o['hold']['remaining_quantity']==2
    assert [r['action'] for r in snap['operations']]==['CREATE_ORDER','PAY','REFUND','CHANGE']
    assert all(r['database_verified'] and r['status']=='SUCCEEDED' for r in snap['operations'])
    assert len(o['transactions'])==3
    assert_conserved(s)


def test_failed_refund_is_distinct_from_paid_order_state(sim):
    s,ctx,p,created=create(sim);oid=created['order_id']
    run(s,ctx,'PAY',order_id=oid,expected_total_fen=6000)
    with s.store.transaction() as c:
        row=c.execute('SELECT config_json FROM v39_scenarios').fetchone();v=json.loads(row[0]);v['refund_failures_remaining']=1
        c.execute('UPDATE v39_scenarios SET config_json=?',(json.dumps(v),))
    failed=run(s,ctx,'REFUND',order_id=oid,scope='FULL')
    snap=read(s.store.path,ctx,now=s.now());o=snap['orders'][0]
    assert failed['status']=='REFUND_FAILED' and failed['error']=='SIMULATED_REFUND_FAILURE'
    assert o['order_status']=='PAID' and o['refunded_total_fen']==0 and o['hold']['remaining_quantity']==3
    attempt=next(r for r in snap['operations'] if r['action']=='REFUND')
    assert attempt['status']=='FAILED' and not attempt['database_verified']
    assert o['ledger_verified'];assert_conserved(s)


def test_ui_paid_receipt_can_support_state_without_a_new_model_payment(sim):
    from target.v39.business_claim_guard import check
    s,ctx,p,created=create(sim);oid=created['order_id']
    pay=s.propose(ctx,'PAY',dict(order_id=oid,expected_total_fen=6000));result=s.confirm(ctx,pay['proposal_id'])
    s.page_event(ctx,'UI_CONFIRMED_PROPOSAL',dict(proposal_id=pay['proposal_id']),result,True,0)
    assessment=check('订单'+oid+'已支付。',[],ctx,s.store.path,s.now())
    assert assessment['status']=='supported'
    assert assessment['checks'][0]['proof_source']=='committed_confirmation_receipt'
    assert assessment['checks'][0]['call_id'] is None
    failed=dict(event='tool_end',tool='railway_pay_order',executed=True,ok=False,result=dict(error='INVALID_STATE'),call_id='actual-failed-call')
    assessment=check('本次订单'+oid+'支付成功。',[failed],ctx,s.store.path,s.now())
    assert assessment['status']=='blocked'


def test_pending_proposal_never_counts_as_committed_payment(sim):
    from target.v39.business_claim_guard import check
    s,ctx,p,created=create(sim);oid=created['order_id']
    pay=s.propose(ctx,'PAY',dict(order_id=oid,expected_total_fen=6000))
    snap=read(s.store.path,ctx,now=s.now())
    assert next(r for r in snap['operations'] if r['action']=='PAY')['status']=='PENDING_CONFIRMATION'
    assert check('订单'+oid+'已支付。',[],ctx,s.store.path,s.now())['status']=='blocked'


def test_ui_confirmation_does_not_rewrite_original_agent_operation(sim,monkeypatch,tmp_path):
    from web.runtime import Conversation
    from web.business_actions import confirm
    import web.v39_bridge
    from target.execution_config import resolve_effective_config
    s,ctx,p,result=create(sim);oid=result['order_id']
    session=Conversation('user',sid=ctx.session_id,root=__import__('config').BASE_DIR/'artifacts/runtime/v394-business-test'/uuid.uuid4().hex)
    # Fixture supplies an isolated Service, real confirmation, and trusted context.
    effective=resolve_effective_config(ctx.session_id,'developer_custom',engine='legacy',provider='mock',full_tools=True)
    trusted=replace(ctx,config_hash=effective.config_hash,config_revision=effective.override_revision)
    monkeypatch.setattr(web.v39_bridge,'prepare',lambda *a:(s,trusted,effective))
    session.operations=[dict(request_id='original',run_id='actual-agent-run',session_id=session.sid,status='BLOCKED',error=dict(category='awaiting_confirmation'),operation='支付提案',started_at='2026-11-03',tools=[])]
    original=copy.deepcopy(session.operations[0])
    pay=s.propose(trusted,'PAY',dict(order_id=oid,expected_total_fen=6000))
    result=confirm(session,pay['proposal_id'],True)
    assert result['status']=='PAID' and session.operations[0]==original
    assert session.operations[-1]['kind']=='page_business' and session.operations[-1]['agent_started'] is False
    receipt=session.business_receipts[-1]
    assert receipt['before']['order_status']=='PENDING_PAYMENT' and receipt['after']['order_status']=='PAID'
    assert receipt['database_verified'] and receipt['order_id']==oid
    assert confirm(session,pay['proposal_id'],True)==result
    assert len(session.business_receipts)==1
    with s.store.transaction() as c:assert c.execute('SELECT count(*) FROM v39_transactions').fetchone()[0]==1


def test_card_display_id_cannot_invalidate_real_selected_trip():
    from web.business_state import query_identity,select_trip
    from types import SimpleNamespace
    result=dict(query_parameters=dict(service_date='2026-11-05',origin_stop_id='AOH',destination_stop_id='HGH'),data=[dict(trip_id='actual-trip')])
    row=dict(tool='railway_query_trips',ok=True,result=result)
    displayed=dict(row,id='display-only-id')
    assert query_identity(row)==query_identity(displayed)
    session=SimpleNamespace();select_trip(session,displayed,result['data'][0])
    assert session.selected_railway_trip['query_identity']==query_identity(row)
    assert session.selected_railway_trip['origin_stop_id']=='AOH'
    assert query_identity(dict(row,result=dict(result,query_parameters=dict(service_date='2026-11-06'))))!=query_identity(row)


def ui_case(sim,monkeypatch):
    from web.runtime import Conversation
    import web.v39_bridge
    from target.execution_config import resolve_effective_config
    s,ctx,p,created=create(sim)
    session=Conversation('user',sid=ctx.session_id,root=__import__('config').BASE_DIR/'artifacts/runtime/v394-business-test'/uuid.uuid4().hex)
    effective=resolve_effective_config(ctx.session_id,'developer_custom',engine='legacy',provider='mock',full_tools=True)
    trusted=replace(ctx,config_hash=effective.config_hash,config_revision=effective.override_revision)
    monkeypatch.setattr(web.v39_bridge,'prepare',lambda *a:(s,trusted,effective))
    return session,s,trusted,created['order_id'],effective


def test_auxiliary_audit_failure_cannot_turn_committed_payment_into_failure(sim,monkeypatch):
    from web.business_actions import confirm
    from web.interaction import history
    session,s,ctx,oid,_=ui_case(sim,monkeypatch)
    pay=s.propose(ctx,'PAY',dict(order_id=oid,expected_total_fen=6000))
    monkeypatch.setattr(s,'page_event',lambda *a:(_ for _ in ()).throw(OSError('controlled audit disk error')))
    result=confirm(session,pay['proposal_id'],True)
    assert result['status']=='PAID' and session.business_receipts[-1]['database_verified']
    assert session.operations[-1]['status']=='SUCCEEDED' and history(session)[-1]['status']=='SUCCEEDED'
    assert session.persistence_warning and s.order(ctx,oid)['payment_status']=='SUCCEEDED'
    assert confirm(session,pay['proposal_id'],True)==result
    assert len(s.order(ctx,oid)['transactions'])==1


def test_business_exception_does_not_leave_running_or_retry_payment(sim,monkeypatch):
    from web.business_actions import confirm
    session,s,ctx,oid,_=ui_case(sim,monkeypatch)
    pay=s.propose(ctx,'PAY',dict(order_id=oid,expected_total_fen=6000))
    count=[]
    def failed(*args):count.append(1);raise RuntimeError('controlled transaction failure')
    monkeypatch.setattr(s,'confirm',failed)
    with pytest.raises(RuntimeError):confirm(session,pay['proposal_id'],True)
    assert count==[1] and session.operations[-1]['status']=='FAILED'
    assert not s.order(ctx,oid)['transactions'] and s.order(ctx,oid)['order_status']=='PENDING_PAYMENT'


def test_cancelled_confirmation_does_not_mean_failed_cancel_order(sim,monkeypatch):
    from web.business_actions import confirm
    session,s,ctx,oid,_=ui_case(sim,monkeypatch)
    pay=s.propose(ctx,'PAY',dict(order_id=oid,expected_total_fen=6000))
    result=confirm(session,pay['proposal_id'],False)
    assert result['status']=='CANCELLED' and session.operations[-1]['status']=='CANCELLED'
    assert s.order(ctx,oid)['order_status']=='PENDING_PAYMENT' and not s.order(ctx,oid)['transactions']


def test_write_permission_revocation_blocks_confirmation(sim,monkeypatch):
    from web.business_actions import confirm
    from dataclasses import replace
    import web.v39_bridge
    session,s,ctx,oid,effective=ui_case(sim,monkeypatch)
    pay=s.propose(ctx,'PAY',dict(order_id=oid,expected_total_fen=6000))
    denied=replace(effective,tool_whitelist=tuple(t for t in effective.tool_whitelist if t!='pay_order'))
    monkeypatch.setattr(web.v39_bridge,'prepare',lambda *a:(s,ctx,denied))
    with pytest.raises(ValueError,match='WRITE_POLICY_DENIED'):confirm(session,pay['proposal_id'],True)
    assert not s.order(ctx,oid)['transactions']
    assert confirm(session,pay['proposal_id'],False)['status']=='CANCELLED'


def test_page_operations_are_not_fictional_user_or_model_chat_turns():
    from types import SimpleNamespace
    from web.interaction import chat_turns
    session=SimpleNamespace(sid='owned',history=[],audits=[],business_view=None,operations=[dict(session_id='owned',kind='page_business',run_id='real-page-operation',started_at='2026-11-04',ended_at='2026-11-04',status='BLOCKED',operation='生成确认卡')])
    assert chat_turns(session)==[]


def test_blocked_page_tool_does_not_claim_backend_execution(sim,monkeypatch):
    from web.business_actions import invoke
    from web.interaction import markup
    import web.v39_bridge
    session,s,ctx,oid,effective=ui_case(sim,monkeypatch)
    denied=replace(ctx,tool_whitelist=('railway_get_order',))
    monkeypatch.setattr(web.v39_bridge,'prepare',lambda *a:(s,denied,effective))
    result=invoke(session,'railway_pay_order',dict(order_id=oid,expected_total_fen=6000))
    assert result['error']=='V39_TOOL_NOT_ALLOWED'
    row=session.operations[-1]
    assert row['status']=='BLOCKED' and row['tools'][0]['executed'] is False
    assert session.business_receipts[-1]['order_id']==oid
    assert '已执行工具' not in markup(row)
    assert not s.order(ctx,oid)['transactions']


def test_order_list_and_single_order_tool_results_share_current_snapshot():
    from types import SimpleNamespace
    from web.business_state import order_for_record
    record=dict(user_msg='查看我的订单',reply='已读取本人订单')
    for result in ([dict(order_id='owned-order')],dict(order_id='owned-order')):
        audit=dict(framework_events=[dict(event='tool_end',tool='railway_get_order',result=result)])
        session=SimpleNamespace(sid='owned',business_view=dict(session_id='owned',railway=dict(orders=[dict(order_id='owned-order')])),_audit_for=lambda r:audit)
        assert order_for_record(session,record)==[dict(order_id='owned-order')]


def test_incomplete_model_reply_still_projects_committed_order_state():
    from types import SimpleNamespace
    from web.business_state import orders_for_operation
    from web.user_copy import error_message
    oid='V39-'+'a'*32
    failed=dict(run_id='failed-model',operation='查询本人订单'+oid)
    trace=dict(user_msg=failed['operation'],reply='模型输出已截断')
    audit=dict(trace_id='failed-model',public_trace=trace)
    session=SimpleNamespace(sid='owned',audits=[audit],_audit_for=lambda r:audit,business_view=dict(session_id='owned',railway=dict(orders=[dict(order_id=oid,order_status='CHANGED')])) )
    assert orders_for_operation(session,failed)[0]['order_status']=='CHANGED'
    assert '已提交' in error_message('model_output_truncated')
