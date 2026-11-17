from datetime import datetime,timezone
import pytest
from target.v39.store import Store
from target.v39.context import Context
from target.v39.service import Service


class SyntheticStatic:
    def interval(self,trip_id,service_date,origin_stop_id,destination_stop_id):
        # Explicit synthetic source, never persisted as a real snapshot.
        stops=[dict(stop_id=n,sequence_index=i+1,position=i,departure_at='2026-11-06T08:00:00+00:00') for i,n in enumerate(('X','Y','Z'))]
        return dict(dataset_version='SYNTHETIC_TEST_FIXTURE/v39',source_sha256='synthetic',trip={'trip_id':trip_id},stops=stops,origin=stops[0],destination=stops[2],segments=[0,1])

@pytest.fixture
def sim(tmp_path,monkeypatch):
    monkeypatch.setenv('RAILWAY_SIMULATION_ENABLED','1')
    s=Service(Store(tmp_path/'service.sqlite'),SyntheticStatic(),clock=lambda:datetime(2026,11,3,8,tzinfo=timezone.utc))
    s.start();s.scenario('demo','SYNTHETIC_TEST_FIXTURE/v39')
    ctx=Context('session-A','user-A','demo',enabled=True,config_hash='frozen')
    return s,ctx

def create(sim):
    s,ctx=sim
    args=dict(trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND')
    assert s.inventory(ctx,quantity=3,**args)['available']==20
    q=s.quote(ctx,passenger_count=3,**args)['quote']
    p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['一','二','三'],contact=ctx.owner_phone))
    return s,ctx,p,s.confirm(ctx,p['proposal_id'])

def test_actual_create_pay_receipt_and_balances(sim):
    s,ctx,p,result=create(sim)
    assert result['status']=='PENDING_PAYMENT'
    assert s.confirm(ctx,p['proposal_id'])==result
    order=s.order(ctx,result['order_id'])
    assert order['total_fen']==6000
    p=s.propose(ctx,'PAY',dict(order_id=result['order_id'],expected_total_fen=6000))
    paid=s.confirm(ctx,p['proposal_id'])
    assert s.confirm(ctx,p['proposal_id'])==paid
    assert s.order(ctx,result['order_id'])['net_paid_fen']==6000
    with s.store.transaction() as c:
        assert [tuple(r) for r in c.execute('SELECT held,sold FROM v39_inventory_segments ORDER BY segment_index')]==[(0,3),(0,3)]
        assert c.execute("SELECT count(*) FROM v39_transactions WHERE status='SUCCEEDED'").fetchone()[0]==1

def test_cancel_releases_once(sim):
    s,ctx,_,created=create(sim)
    p=s.propose(ctx,'CANCEL',dict(order_id=created['order_id']))
    result=s.confirm(ctx,p['proposal_id'])
    assert result['status']=='CANCELLED'
    assert s.confirm(ctx,p['proposal_id'])==result
    with s.store.transaction() as c:assert all(tuple(r)==(0,0) for r in c.execute('SELECT held,sold FROM v39_inventory_segments'))

def test_cross_user_quote_and_config_change(sim):
    from dataclasses import replace
    s,ctx=sim
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    with pytest.raises(ValueError,match='QUOTE_FORBIDDEN'):
        s.propose(replace(ctx,session_id='other',owner_phone='other'),'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['X']))
    p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['X']))
    with pytest.raises(ValueError,match='CONFIG_STALE'):s.confirm(replace(ctx,config_hash='changed'),p['proposal_id'])
    with s.store.transaction() as c:
        assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==0
        assert c.execute('SELECT used_at FROM v39_confirmation_tokens WHERE proposal_id=?',(p['proposal_id'],)).fetchone()[0] is None
