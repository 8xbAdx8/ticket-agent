from datetime import timedelta
import json,sqlite3
import pytest
from tests.v39.test_storage import data
from tests.v39.test_service import sim,create
from tests.v39.test_lifecycle import run,assert_conserved
from tests.v39.test_matrix import fault_config

@pytest.mark.parametrize('kwargs',[
 dict(source_hold_id='missing'),dict(source_order_id='OB'),dict(quantity=4),
 dict(trip_id='T2'),dict(service_date='2026-11-05'),dict(dataset_version='v2'),dict(seat_class='FIRST')])
def test_retained_full_identity_and_source_quantity(data,kwargs):
    c,a=data
    # The destination belongs to order A and targets the same A quote. Cross
    # owner/date/seat/trip/dataset references must fail even with equal indices.
    a['ins']('v39_holds',hold_id='DEST',quote_id='QA',order_id='OA',status='ACTIVE')
    values=dict(hold_id='DEST',segment_index=0,inventory_role='RETAINED',source_hold_id='HA',source_order_id='OA');values.update(kwargs)
    with pytest.raises(sqlite3.IntegrityError):a['ins']('v39_hold_segments',**values)
    assert c.execute("SELECT count(*) FROM v39_hold_segments WHERE hold_id='DEST'").fetchone()[0]==0

def test_allocation_change_scope_and_required_transaction_refs(data):
    c,a=data
    for cid in ('CA','CB'):
        a['ins']('v39_change_requests',change_id=cid,order_id='OA',old_hold_id='HA',old_quote_id='QA',target_quote_id='QT',target_seat_class='SECOND',difference_fen=100,status='PENDING',idempotency_key=cid)
    a['ins']('v39_transactions',transaction_id='CHANGE',order_id='OA',change_id='CA',transaction_type='CHANGE_SUPPLEMENT',direction='DEBIT',amount_fen=100,status='PENDING',idempotency_key='change')
    with pytest.raises(sqlite3.IntegrityError):a['ins']('v39_transaction_allocations',allocation_id='BAD',transaction_id='CHANGE',order_id='OA',order_item_id='A0',change_id='CB',amount_fen=100)
    for kind,direction,ref,ch in [('REFUND','CREDIT',None,None),('CHANGE_REFUND','CREDIT',None,None),('CHANGE_SUPPLEMENT','DEBIT',None,None),('PAYMENT','DEBIT',None,'CA'),('CHANGE_SUPPLEMENT','CREDIT',None,'CA')]:
        with pytest.raises(sqlite3.IntegrityError):a['ins']('v39_transactions',transaction_id='bad'+kind+direction,order_id='OA',change_id=ch,refund_id=ref,transaction_type=kind,direction=direction,amount_fen=100,status='PENDING',idempotency_key=kind)

def test_timeout_keeps_failed_receipt_no_charge_and_no_held(sim):
    s,ctx,_,r=create(sim);fault_config(s,payment_timeouts_remaining=1)
    p=s.propose(ctx,'PAY',dict(order_id=r['order_id'],expected_total_fen=6000))
    result=s.confirm(ctx,p['proposal_id']);assert result['error']=='PAYMENT_TIMEOUT'
    assert result==s.confirm(ctx,p['proposal_id'])
    o=s.order(ctx,r['order_id']);assert (o['net_paid_fen'],o['payment_status'])==(0,'TIMEOUT')
    with s.store.transaction() as c:
        assert all(tuple(r)==(0,0) for r in c.execute('SELECT held,sold FROM v39_inventory_segments'))
        assert c.execute('SELECT status FROM v39_transactions').fetchone()[0]=='TIMEOUT'
    assert_conserved(s)

def test_past_departure_cannot_lock_and_token_rolls_back(sim):
    s,ctx=sim
    from tests.v39.test_matrix import proposal
    p=proposal(s,ctx)
    s._departure=lambda o:(s.now()-timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError,match='DEPARTURE_ALREADY_PASSED'):s.confirm(ctx,p['proposal_id'])
    with s.store.transaction() as c:
        assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==0
        assert c.execute('SELECT used_at FROM v39_confirmation_tokens').fetchone()[0] is None

def test_create_contact_cannot_override_authenticated_identity(sim):
    s,ctx=sim
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    with pytest.raises(ValueError,match='ORDER_FORBIDDEN'):
        s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['P'],contact='another-user'))
    with s.store.transaction() as c:assert c.execute('SELECT count(*) FROM v39_proposals').fetchone()[0]==0

def test_corrupt_database_ui_fails_closed_without_stack_trace(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import web.railway_simulation as ui
    monkeypatch.setenv('RAILWAY_SIMULATION_ENABLED','1')
    def corrupt(path):raise sqlite3.DatabaseError('TEST_CORRUPT_DATABASE')
    monkeypatch.setattr(ui,'resource',corrupt)
    app=AppTest.from_string('from web.railway_simulation import page\npage()').run(timeout=20)
    assert not app.exception
    assert any('未能通过初始化或身份核验' in e.value for e in app.error)
