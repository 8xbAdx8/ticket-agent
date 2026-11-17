"""Deterministic receipt classifications over real Service transactions."""
import copy
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import pytest
from tests.v39.test_service import sim
from target.execution_config import resolve_effective_config,scope
from target.v39.read_model import read
from web.business_actions import confirm

@pytest.fixture
def ui(sim,monkeypatch,tmp_path):
    from web.runtime import Conversation
    import web.v39_bridge
    s,ctx=sim
    ef=resolve_effective_config(ctx.session_id,'developer_custom',engine='legacy',provider='mock',full_tools=True)
    ctx=replace(ctx,session_id='web-112233445566',config_hash=ef.config_hash,config_revision=ef.override_revision)
    session=Conversation('user',sid=ctx.session_id,root=tmp_path/'conversation')
    session._v39_service=s;session._v39_context=ctx;session._v39_effective=ef
    monkeypatch.setattr(web.v39_bridge,'prepare',lambda *a:(s,ctx,ef))
    q=s.quote(ctx,trip_id='T1',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['合成甲'],contact=ctx.owner_phone))
    with scope(None):yield session,s,ctx,p

def count(s,table):
    with s.store.transaction() as c:return c.execute('SELECT count(*) FROM v39_'+table).fetchone()[0]

def test_commit_and_duplicate_confirmation(ui):
    session,s,ctx,p=ui
    result=confirm(session,p['proposal_id'],True)
    assert result['status']=='PENDING_PAYMENT'
    view=read(s.store.path,ctx,now=s.now());o=view['orders'][0]
    assert o['hold_status']=='ACTIVE' and o['hold']['remaining_quantity']==1
    assert o['proposal_id']==p['proposal_id'] and o['idempotency_key']==p['proposal_id']
    assert session.business_receipts[-1]['status']=='SUCCEEDED'
    assert confirm(session,p['proposal_id'],True)==result and count(s,'orders')==1

def test_readback_failure_is_unknown_and_never_repeats_write(ui,monkeypatch):
    session,s,ctx,p=ui
    import target.v39.read_model as model
    original=model.read;calls=[]
    def failing(*a,**k):
        calls.append(1)
        if len(calls)>1:raise OSError('read unavailable after commit')
        return original(*a,**k)
    monkeypatch.setattr(model,'read',failing)
    result=confirm(session,p['proposal_id'],True)
    assert result['verification_status']=='UNKNOWN' and count(s,'orders')==1
    assert session.business_receipts[-1]['status']=='UNKNOWN'
    monkeypatch.setattr(model,'read',original)
    monkeypatch.setattr(s,'confirm',lambda *a:pytest.fail('uncertain write repeated'))
    restored=confirm(session,p['proposal_id'],True)
    assert restored['status']=='PENDING_PAYMENT' and session.business_receipts[-1]['database_verified']
    assert count(s,'orders')==1

def test_secret_lost_is_not_a_database_read_error(ui):
    session,s,ctx,p=ui;s._secrets.clear()
    result=confirm(session,p['proposal_id'],True)
    assert result['error']=='CONFIRMATION_SECRET_LOST' and result['verification_status']=='FAILED'
    assert count(s,'orders')==count(s,'holds')==0

def test_expired_proposal_does_not_write(ui):
    session,s,ctx,p=ui;s.clock=lambda:__import__('datetime').datetime(2026,11,6,0,6,tzinfo=__import__('datetime').timezone.utc)
    # Advance relative to fixture time, without altering a production clock.
    from datetime import datetime
    s.clock=lambda:datetime.fromisoformat(p['expires_at'])+timedelta(seconds=1)
    result=confirm(session,p['proposal_id'],True)
    assert result['failure_reason']=='PROPOSAL_EXPIRED' and result['verification_status']=='FAILED' and count(s,'orders')==0

def test_decline_and_invalid_reconfirm(ui):
    session,s,ctx,p=ui
    assert confirm(session,p['proposal_id'],False)['status']=='CANCELLED'
    assert count(s,'orders')==0 and not read(s.store.path,ctx,now=s.now())['pending_proposals']

def test_hold_failure_rolls_back_all_rows(ui,monkeypatch):
    session,s,ctx,p=ui
    monkeypatch.setattr(s,'_delta',lambda *a:(_ for _ in ()).throw(RuntimeError('injected hold failure')))
    with pytest.raises(RuntimeError):confirm(session,p['proposal_id'],True)
    assert count(s,'orders')==count(s,'holds')==count(s,'idempotency')==0
    assert session.operations[-1]['status']=='FAILED'

def test_commit_then_auxiliary_exception_uses_native_receipt(ui,monkeypatch):
    session,s,ctx,p=ui;original=s.confirm
    def after_commit(*a):original(*a);raise OSError('after commit transport failure')
    monkeypatch.setattr(s,'confirm',after_commit)
    result=confirm(session,p['proposal_id'],True)
    assert result['status']=='PENDING_PAYMENT' and session.operations[-1]['status']=='SUCCEEDED'
    assert count(s,'orders')==1

def test_partial_order_hold_is_never_success(ui,monkeypatch):
    session,s,ctx,p=ui
    import target.v39.read_model as model
    original=model.read
    def inconsistent(*a,**k):
        view=original(*a,**k)
        if view['orders']:
            view=copy.deepcopy(view);view['orders'][0]['hold']=None
            op=view['operations'][0];op['database_verified']=False;op['status']='UNKNOWN'
        return view
    monkeypatch.setattr(model,'read',inconsistent)
    result=confirm(session,p['proposal_id'],True)
    assert result['error']=='BUSINESS_INCONSISTENT' and session.business_receipts[-1]['status']=='PARTIAL'
    assert count(s,'orders')==1

def test_pay_is_separate_and_unique(ui):
    session,s,ctx,p=ui;created=confirm(session,p['proposal_id'],True)
    assert count(s,'transactions')==0
    pay=s.propose(ctx,'PAY',dict(order_id=created['order_id'],expected_total_fen=created['total_fen']))
    result=confirm(session,pay['proposal_id'],True)
    assert result['status']=='PAID' and confirm(session,pay['proposal_id'],True)==result
    o=read(s.store.path,ctx,now=s.now())['orders'][0]
    assert o['payment_status']=='SUCCEEDED' and o['hold_status']=='CONSUMED' and o['ledger_verified']
    assert count(s,'transactions')==1

def test_pending_navigation_is_owned_and_does_not_repeat(monkeypatch):
    import web.proposal_navigation as nav
    state={};monkeypatch.setattr(nav.st,'session_state',state)
    a=SimpleNamespace(sid='A',business_view={'railway':{'pending_proposals':[{'proposal_id':'P1'}]}})
    nav.prepare(a);assert state['user_info_open'] and state['railway_proposal_focus_A']=='P1'
    state['user_info_open']=False;nav.prepare(a);assert not state['user_info_open']
    a.business_view['railway']['pending_proposals'].append({'proposal_id':'P2'});nav.prepare(a)
    assert state['user_info_open'] and state['railway_proposal_focus_A']=='P2'
    b=SimpleNamespace(sid='B',business_view={'railway':{'pending_proposals':[]}});nav.prepare(b)
    assert 'railway_proposal_focus_B' not in state

def test_restored_snapshot_is_read_only(ui):
    session,s,ctx,p=ui
    session.railway_state_reference={'path':str(s.store.path),'scenario_id':ctx.scenario_id}
    session.operations=[dict(request_id='pending',operation='create preview',status='BLOCKED',session_id=session.sid,tools=[])]
    session.root.mkdir(parents=True,exist_ok=True);session.save_replay()
    from web.session_store import restore_session
    restored=restore_session(session.root,expected_sid=session.sid)
    assert restored.read_only and restored.railway_state_reference==session.railway_state_reference
    assert restored.operations[0]['status']=='BLOCKED'
    assert count(s,'orders')==0


def test_unproven_success_stays_unknown(ui,monkeypatch):
    session,s,ctx,p=ui
    monkeypatch.setattr(s,'confirm',lambda *a:dict(status='PENDING_PAYMENT',order_id='unverified-order'))
    result=confirm(session,p['proposal_id'],True)
    assert result['verification_status']=='UNKNOWN' and count(s,'orders')==0
    assert session.operations[-1]['status']=='UNKNOWN'
    monkeypatch.setattr(s,'confirm',lambda *a:pytest.fail('uncertain write retried'))
    assert confirm(session,p['proposal_id'],True)['verification_status']=='UNKNOWN'


def test_unresolved_other_proposal_blocks_new_create(ui):
    session,s,ctx,p=ui
    session.business_receipts=[dict(proposal_id='old-uncertain',status='UNKNOWN',actual_result={},order_id=None)]
    with pytest.raises(ValueError,match='PREVIOUS_BUSINESS_RESULT_UNRESOLVED'):confirm(session,p['proposal_id'],True)
    assert count(s,'orders')==0


def test_initial_read_failure_never_calls_service(ui,monkeypatch):
    session,s,ctx,p=ui
    import target.v39.read_model as model
    monkeypatch.setattr(model,'read',lambda *a,**k:(_ for _ in ()).throw(OSError('initial read blocked')))
    monkeypatch.setattr(s,'confirm',lambda *a:pytest.fail('unreadable state confirmed'))
    with pytest.raises(OSError):confirm(session,p['proposal_id'],True)
    assert count(s,'orders')==0


@pytest.mark.parametrize('status',['UNKNOWN','PARTIAL'])
def test_uncertain_states_render_without_success_animation(status):
    from web.request_motion import state
    view=state(dict(status=status),[],active=False)
    assert not view['moving'] and view['state']!='SUCCEEDED'
    from streamlit.testing.v1 import AppTest
    code="""import streamlit as st
from types import SimpleNamespace
from unittest.mock import patch
from web.conversation import _run_summary_bar
session=SimpleNamespace(history=[])
with patch('web.run_view.run_summary',return_value={}):
    _run_summary_bar(session,None,[],'test',dict(status=STATUS,kind='page_business',run_id='test',error=None))
""".replace('STATUS',repr(status))
    app=AppTest.from_string(code).run(timeout=20)
    assert not app.exception
    assert any(('结果待核验' if status=='UNKNOWN' else '业务状态不一致') in m.value for m in app.markdown)


def test_actual_sqlite_hold_anomaly_is_partial(ui,monkeypatch):
    session,s,ctx,p=ui;original=s.confirm
    def damaged_hold(*a):
        result=original(*a)
        # Explicit fault injection into this test's NEW synthetic database only.
        with s.store.transaction() as c:c.execute("UPDATE v39_holds SET status='RELEASED' WHERE order_id=?",(result['order_id'],))
        return result
    monkeypatch.setattr(s,'confirm',damaged_hold)
    result=confirm(session,p['proposal_id'],True)
    assert result['verification_status']=='PARTIAL' and result['error']=='BUSINESS_INCONSISTENT'
    view=read(s.store.path,ctx,now=s.now())
    assert view['orders'][0]['order_status']=='PENDING_PAYMENT'
    assert view['orders'][0]['hold_status']=='RELEASED'
    assert not view['operations'][0]['database_verified']


def test_receipt_cannot_use_an_unrelated_quote_hold(ui):
    session,s,ctx,p=ui;confirm(session,p['proposal_id'],True)
    view=read(s.store.path,ctx,now=s.now())
    from target.v39.receipt_proof import creation_proof
    order=copy.deepcopy(view['orders'][0]);proposal=view['proposals'][0]
    assert creation_proof(order,proposal)
    order['hold']['quote_id']='unrelated-quote'
    assert not creation_proof(order,proposal)


def test_proposal_summary_is_bound_to_quote_and_known_static_record(ui):
    session,s,ctx,p=ui
    from web.proposal_navigation import summary
    view=read(s.store.path,ctx,now=s.now())
    session.railway_queries=[dict(tool='railway_trip_stops',ok=True,result=dict(data=dict(trip={'trip_id':'T1'},stops=[]))),dict(tool='railway_query_trips',ok=True,result=dict(data=[dict(trip_id='T1',trip_short_name='REAL_RETURNED_TRAIN')]))]
    shown=summary(session,view,view['proposals'][0]);q=view['quotes'][0]
    assert shown['train']=='REAL_RETURNED_TRAIN' and shown['trip_id']==q['trip_id']
    assert (shown['date'],shown['origin'],shown['destination'],shown['seat'],shown['total_fen'])==(q['service_date'],q['origin_stop_id'],q['destination_stop_id'],q['seat_class'],q['total_fen'])


def test_valid_order_hold_without_receipt_proof_is_unknown_not_partial(ui,monkeypatch):
    session,s,ctx,p=ui
    import target.v39.read_model as model
    original=model.read
    def incomplete_proof(*a,**k):
        view=original(*a,**k)
        if view['orders']:
            view=copy.deepcopy(view)
            view['operations'][0].update(database_verified=False,status='UNKNOWN')
        return view
    monkeypatch.setattr(model,'read',incomplete_proof)
    result=confirm(session,p['proposal_id'],True)
    assert result['verification_status']=='UNKNOWN' and session.business_receipts[-1]['status']=='UNKNOWN'
    assert count(s,'orders')==1 and count(s,'holds')==1
    monkeypatch.setattr(model,'read',original)
    monkeypatch.setattr(s,'confirm',lambda *a:pytest.fail('uncertain create retried'))
    assert confirm(session,p['proposal_id'],True)['status']=='PENDING_PAYMENT'
