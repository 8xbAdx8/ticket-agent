"""Actual SQLite assertions; injected policies below are TEST ONLY, not approval."""
from dataclasses import replace
from datetime import timedelta
import json,sqlite3
import pytest
from tests.v39.test_service import sim,create
from target.v39.policy import Policy


def approved(s,profile='CHANGED_REFUND_P01'):
    s.policy=Policy(version='TEST_ONLY/'+profile,profile=profile,approved=True,partial_change=True,further_refund=True)

def paid(sim):
    s,ctx,_,created=create(sim);oid=created['order_id']
    p=s.propose(ctx,'PAY',dict(order_id=oid,expected_total_fen=6000))
    assert s.confirm(ctx,p['proposal_id'])['status']=='PAID'
    return s,ctx,oid

def run(s,ctx,action,**payload):
    p=s.propose(ctx,action,payload)
    return s.confirm(ctx,p['proposal_id'])

def target(s,ctx,oid,**changes):
    o=s.order(ctx,oid)
    args={k:o[k] for k in ('trip_id','service_date','origin_stop_id','destination_stop_id','seat_class')};args.update(changes)
    q=s.quote(ctx,passenger_count=o['active_item_count'],**args)['quote']
    return dict(order_id=oid,target_quote_id=q['quote_id'],**{'target_'+k:v for k,v in args.items()})

def assert_conserved(s):
    with s.store.transaction() as c:
        for row in c.execute('SELECT * FROM v39_inventory_segments'):
            key=tuple(row[k] for k in ('scenario_id','dataset_version','trip_id','service_date','seat_class','segment_index'))
            actual=c.execute('SELECT COALESCE(SUM(delta_held),0),COALESCE(SUM(delta_sold),0) FROM v39_inventory_events WHERE scenario_id=? AND dataset_version=? AND trip_id=? AND service_date=? AND seat_class=? AND segment_index=?',key).fetchone()
            assert tuple(actual)==(row['held'],row['sold'])
            assert 0<=row['held']+row['sold']<=row['capacity']
        for o in c.execute("SELECT * FROM v39_orders WHERE payment_status='SUCCEEDED'"):
            ledger=c.execute("SELECT COALESCE(SUM(CASE direction WHEN 'DEBIT' THEN amount_fen ELSE -amount_fen END),0) FROM v39_transactions WHERE order_id=? AND status='SUCCEEDED'",(o['order_id'],)).fetchone()[0]
            assert ledger==o['net_paid_fen']==o['total_fen']+o['fee_total_fen']
            assert o['initial_passenger_count']==o['active_item_count']+o['refunded_item_count']
        assert not c.execute('PRAGMA foreign_key_check').fetchall()

def test_pending_d9_does_not_choose_product_policy(sim):
    sim[0].policy=Policy(version='D9_PENDING',profile=None,approved=False,partial_change=False,further_refund=False)
    s,ctx,oid=paid(sim)
    assert s.order(ctx,oid)['policy_profile']=='D9_PENDING'
    for action in ('REFUND','CHANGE','CANCEL'):
        with pytest.raises(ValueError,match='POLICY_PENDING'):s.propose(ctx,action,dict(order_id=oid,scope='FULL'))
    assert s.order(ctx,oid)['paid_total_fen']==6000

def test_full_partial_change_failed_refund_retry_lifecycle(sim):
    s,ctx,oid=paid(sim);approved(s)
    first=s.order(ctx,oid)['items'][0]['item_id']
    r=run(s,ctx,'REFUND',order_id=oid,scope='ITEMS',item_ids=[first])
    assert (r['refund_fen'],r['fee_fen'],r['remaining_passengers'])==(1900,100,2)
    o=s.order(ctx,oid);assert (o['total_fen'],o['paid_total_fen'],o['refunded_total_fen'],o['net_paid_fen'])==(4000,6000,1900,4100)
    r=run(s,ctx,'CHANGE',**target(s,ctx,oid,trip_id='T2',seat_class='FIRST'))
    assert r['difference_fen']==2000
    o=s.order(ctx,oid);assert (o['order_status'],o['change_count'],o['paid_total_fen'],o['total_fen'])==('CHANGED',1,8000,6000)
    with s.store.transaction() as c:
        config=json.loads(c.execute('SELECT config_json FROM v39_scenarios').fetchone()[0]);config['refund_failures_remaining']=1
        c.execute('UPDATE v39_scenarios SET config_json=?',(json.dumps(config),))
    r=run(s,ctx,'REFUND',order_id=oid,scope='FULL')
    assert r['status']=='REFUND_FAILED'
    o=s.order(ctx,oid);assert (o['order_status'],o['total_fen'],o['refunded_total_fen'],o['fee_total_fen'])==('CHANGED',6000,1900,100)
    r=run(s,ctx,'REFUND',order_id=oid,scope='FULL')
    assert r['status']=='CANCELLED'
    o=s.order(ctx,oid);assert (o['total_fen'],o['active_item_count'],o['refunded_total_fen'],o['fee_total_fen'],o['net_paid_fen'])==(0,0,7600,400,400)
    assert len(o['refunds'])==3 and [r['status'] for r in o['refunds']].count('FAILED')==1
    assert_conserved(s)

@pytest.mark.parametrize('seat,delta',[('FIRST',3000),('SECOND',0)])
def test_change_money_and_retained(sim,seat,delta):
    s,ctx,oid=paid(sim);approved(s)
    r=run(s,ctx,'CHANGE',**target(s,ctx,oid,seat_class=seat))
    assert r['status']=='CHANGED' and r['difference_fen']==delta
    with s.store.transaction() as c:
        roles=[r[0] for r in c.execute('SELECT role FROM v39_change_segments')]
        assert roles==(['RETAINED','RETAINED'] if delta==0 else ['NEW','NEW','RELEASED','RELEASED'])
    assert_conserved(s)

@pytest.mark.parametrize('fault',['INVENTORY','MONEY'])
def test_failed_change_preserves_old_state_and_stock(sim,fault):
    s,ctx,oid=paid(sim);approved(s)
    args=target(s,ctx,oid,trip_id='T2',seat_class='FIRST')
    if fault=='INVENTORY':
        with s.store.transaction() as c:
            config=json.loads(c.execute('SELECT config_json FROM v39_scenarios').fetchone()[0]);config['capacity']['FIRST']=0
            c.execute('UPDATE v39_scenarios SET config_json=?',(json.dumps(config),))
    else:
        with s.store.transaction() as c:
            config=json.loads(c.execute('SELECT config_json FROM v39_scenarios').fetchone()[0]);config['change_money_failures_remaining']=1
            c.execute('UPDATE v39_scenarios SET config_json=?',(json.dumps(config),))
    before=s.order(ctx,oid)
    r=run(s,ctx,'CHANGE',**args)
    assert r['status']=='CHANGE_FAILED'
    after=s.order(ctx,oid)
    assert [after[k] for k in ('hold_id','quote_id','paid_total_fen','total_fen','change_count')]==[before[k] for k in ('hold_id','quote_id','paid_total_fen','total_fen','change_count')]
    assert_conserved(s)

def test_change_refund_difference_and_strict_policy(sim):
    s,ctx,oid=paid(sim);approved(s,'P02_STRICT')
    # Lower rule affects only new quote, never the frozen old price.
    with s.store.transaction() as c:c.execute("UPDATE v39_price_rules SET base_fen_per_segment=900 WHERE seat_class='SECOND'")
    r=run(s,ctx,'CHANGE',**target(s,ctx,oid,trip_id='T2'))
    assert r['difference_fen']==-600
    o=s.order(ctx,oid);assert (o['total_fen'],o['refunded_total_fen'])==(5400,600)
    with pytest.raises(ValueError,match='REFUND_NOT_ALLOWED'):s.propose(ctx,'REFUND',dict(order_id=oid,scope='FULL'))
    with pytest.raises(ValueError,match='CHANGE_LIMIT'):s.propose(ctx,'CHANGE',target(s,ctx,oid,trip_id='T3'))
    assert_conserved(s)

def test_refund_cross_item_and_repeated_items_rejected(sim):
    s,ctx,oid=paid(sim);approved(s)
    item=s.order(ctx,oid)['items'][0]['item_id']
    for ids in ([item,item],['FOREIGN']):
        with pytest.raises(ValueError,match='REFUND_'):s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=ids))
    run(s,ctx,'REFUND',order_id=oid,scope='ITEMS',item_ids=[item])
    with pytest.raises(ValueError,match='REFUND_ALREADY'):s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=[item]))
    assert_conserved(s)

@pytest.mark.parametrize('table',['v39_orders','v39_inventory_events','v39_transactions','v39_audit_events'])
def test_technical_failure_rolls_back_token_and_all_domain_writes(sim,table):
    s,ctx=sim
    if table in ('v39_orders','v39_inventory_events'):
        q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
        p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['A']))
    else:
        s,ctx,_,created=create(sim)
        p=s.propose(ctx,'PAY',dict(order_id=created['order_id'],expected_total_fen=6000))
    with s.store.transaction() as c:
        before=[tuple(r) for r in c.execute('SELECT held,sold FROM v39_inventory_segments')]
        count=c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]
        c.execute(f"CREATE TRIGGER test_fault BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'INJECTED_SQL_FAULT'); END")
    with pytest.raises(sqlite3.IntegrityError,match='INJECTED'):s.confirm(ctx,p['proposal_id'])
    with s.store.transaction() as c:
        assert [tuple(r) for r in c.execute('SELECT held,sold FROM v39_inventory_segments')]==before
        assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==count
        assert c.execute('SELECT used_at FROM v39_confirmation_tokens WHERE proposal_id=?',(p['proposal_id'],)).fetchone()[0] is None
        assert c.execute('SELECT count(*) FROM v39_idempotency WHERE key LIKE ?',('%'+p['proposal_id']+'%',)).fetchone()[0]==0

def test_expiry_exact_boundary_and_owner_restart(sim):
    s,ctx=sim
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['A']))
    base=s.now();s.clock=lambda:base+timedelta(seconds=300)
    assert s.confirm(ctx,p['proposal_id'])['status']=='PROPOSAL_EXPIRED'
    p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['A']))
    s.close();s.start()
    assert s.confirm(ctx,p['proposal_id'])['status']=='CONFIRMATION_SECRET_LOST'
    with s.store.transaction() as c:
        assert c.execute('SELECT invalid_reason FROM v39_confirmation_tokens WHERE proposal_id=?',(p['proposal_id'],)).fetchone()[0]=='SECRET_LOST'
        assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==0

def test_create_without_inventory_query_and_expire_once(sim):
    s,ctx=sim
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    created=run(s,ctx,'CREATE_ORDER',quote_id=q['quote_id'],passengers=['A'])
    base=s.now();s.clock=lambda:base+timedelta(seconds=900)
    assert s.expire(ctx)==1 and s.expire(ctx)==0
    assert s.order(ctx,created['order_id'])['order_status']=='EXPIRED'
    assert_conserved(s)
