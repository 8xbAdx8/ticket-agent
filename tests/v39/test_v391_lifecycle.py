"""T057–T076: approved product policy, actual SQLite and immutable snapshots."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,os,sqlite3
import pytest
from tests.v39.test_service import sim
from tests.v39.test_lifecycle import paid,run,target,assert_conserved
from tests.v39.test_matrix import fault_config
from tests.v39.test_confirmation_rpc import clients
from target.v39.policy import Policy,VERSION


def probe(s,case,steps,label):
    assert_conserved(s)
    tables=('v39_orders','v39_order_items','v39_holds','v39_hold_segments','v39_refund_requests','v39_refund_items','v39_transactions','v39_transaction_allocations','v39_inventory_segments','v39_inventory_events','v39_item_price_snapshots')
    with s.store.transaction() as c:
        data={n:[dict(r) for r in c.execute('SELECT * FROM '+n)] for n in tables}
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        for o in data['v39_orders']:
            if o['payment_status']!='SUCCEEDED':continue
            active=[i for i in data['v39_order_items'] if i['order_id']==o['order_id'] and i['item_status']=='ACTIVE']
            refunded=[i for i in data['v39_order_items'] if i['order_id']==o['order_id'] and i['item_status']=='REFUNDED']
            assert len(active)==o['active_item_count'] and len(refunded)==o['refunded_item_count']
            hold=next(h for h in data['v39_holds'] if h['hold_id']==o['hold_id'])
            assert hold['remaining_quantity']==len(active)
            for item in active+refunded:
                snap=next(v for v in data['v39_item_price_snapshots'] if v['item_id']==item['item_id'] and v['quote_id']==item['price_quote_id'])
                assert all(item[k]==snap[k] for k in ('base_fen','seat_fen','fixed_fee_share_fen','fare_fen'))
        steps.append(dict(label=label,tables=data))
    out=Path(os.environ['RAILWAY_SIM_DB_PATH']).parent/'db-probes';out.mkdir(exist_ok=True)
    (out/f'V39-T{case:03}.json').write_text(json.dumps(dict(test_id=f'V39-T{case:03}',steps=steps),ensure_ascii=False,indent=2),encoding='utf8')

def refund(s,ctx,oid,ids=None):
    return run(s,ctx,'REFUND',order_id=oid,scope='ITEMS' if ids else 'FULL',**(dict(item_ids=ids) if ids else {}))

@pytest.mark.parametrize('case',range(57,77),ids=lambda n:f'V39-T{n:03}')
def test_approved_lifecycle(case,sim):
    s,ctx=sim;steps=[]
    if case==57:
        assert Policy().version==VERSION and Policy().approved and Policy().profile=='CHANGED_REFUND_P01'
        assert Policy().partial_change and Policy().further_refund and Policy().max_changes==1
        _,_,oid=paid(sim)
        assert s.order(ctx,oid)['policy_profile']=='CHANGED_REFUND_P01'
    elif case in (58,59,60,61,64,74,75):
        s,ctx,oid=paid(sim);o=s.order(ctx,oid);ids=[i['item_id'] for i in o['items']]
        r=refund(s,ctx,oid,[ids[0]])
        assert (r['fee_fen'],r['refund_fen'],r['remaining_passengers'])==(100,1900,2)
        o=s.order(ctx,oid)
        assert (o['initial_passenger_count'],o['active_item_count'],o['refunded_item_count'],o['order_status'])==(3,2,1,'PAID')
        first=dict(o['items'][0]);probe(s,case,steps,'refund-first')
        if case==64:
            args={k:o[k] for k in ('trip_id','service_date','origin_stop_id','destination_stop_id','seat_class')}
            q=s.quote(ctx,passenger_count=3,**args)['quote']
            args=dict(order_id=oid,target_quote_id=q['quote_id'],**{'target_'+k:v for k,v in args.items()})
            with pytest.raises(ValueError,match='PASSENGER_MISMATCH'):s.propose(ctx,'CHANGE',args)
        elif case in (59,60,61,75):
            r=run(s,ctx,'CHANGE',**target(s,ctx,oid,trip_id='T2',seat_class='FIRST'))
            assert r['status']=='CHANGED' and r['difference_fen']==2000
            o=s.order(ctx,oid)
            assert o['change_count']==1 and o['active_item_count']==2 and o['items'][0]==first
            assert all(i['price_quote_id']==o['quote_id'] for i in o['items'] if i['item_status']=='ACTIVE')
            probe(s,case,steps,'change-remaining-two')
            if case in (60,61,75):
                r=refund(s,ctx,oid,[ids[1]])
                assert (r['status'],r['fee_fen'],r['refund_fen'])==('CHANGED',150,2850)
                probe(s,case,steps,'changed-refund-one')
            if case in (61,75):
                r=refund(s,ctx,oid,[ids[2]])
                assert r['status']=='CANCELLED'
                o=s.order(ctx,oid)
                assert (o['active_item_count'],o['refunded_item_count'],o['total_fen'])==(0,3,0)
                assert (o['paid_total_fen'],o['refunded_total_fen'],o['fee_total_fen'],o['net_paid_fen'])==(8000,7600,400,400)
                with s.store.transaction() as c:assert all(tuple(v)==(0,0) for v in c.execute('SELECT held,sold FROM v39_inventory_segments'))
        if case==74:
            assert (o['paid_total_fen'],o['refunded_total_fen'],o['fee_total_fen'],o['net_paid_fen'],o['total_fen'])==(6000,1900,100,4100,4000)
    elif case in (62,63):
        s,ctx,oid=paid(sim);ids=[i['item_id'] for i in s.order(ctx,oid)['items']]
        for k,item in enumerate(ids):
            refund(s,ctx,oid,[item]);probe(s,case,steps,'partial-'+str(k+1))
            if case==63:
                with pytest.raises(ValueError,match='REFUND_ALREADY_DONE'):s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=[item]))
                break
        if case==62:assert s.order(ctx,oid)['order_status']=='CANCELLED'
    elif case==65:
        s,ctx,oid=paid(sim)
        run(s,ctx,'CHANGE',**target(s,ctx,oid,trip_id='T2'))
        with pytest.raises(ValueError,match='CHANGE_LIMIT'):s.propose(ctx,'CHANGE',target(s,ctx,oid,trip_id='T3'))
        assert s.order(ctx,oid)['change_count']==1
    elif case in (66,67):
        base=s.now();hours=24 if case==66 else 48
        for offset in (-1,0,1):
            s.clock=lambda:base
            _,_,oid=paid(sim)
            seconds=hours*3600+offset
            now=datetime(2026,11,6,8,tzinfo=timezone.utc)-timedelta(seconds=seconds)
            s.clock=lambda:now
            r=refund(s,ctx,oid)
            rate=500 if seconds>172800 else 1000 if seconds>=86400 else 2000
            assert r['fee_fen']==6000*rate//10000 and r['refund_fen']==6000-r['fee_fen']
            probe(s,case,steps,'boundary-offset-'+str(offset))
    elif case==68:
        # Fixture rule adjustment only; all transactions still use the service.
        with s.store.transaction() as c:c.execute('UPDATE v39_price_rules SET base_fen_per_segment=5')
        q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=3)['quote']
        r=run(s,ctx,'CREATE_ORDER',quote_id=q['quote_id'],passengers=['A','B','C']);oid=r['order_id']
        run(s,ctx,'PAY',order_id=oid,expected_total_fen=30)
        r=refund(s,ctx,oid);assert (r['fee_fen'],r['refund_fen'])==(3,27)
        with s.store.transaction() as c:assert [v[0] for v in c.execute('SELECT fee_fen FROM v39_refund_items')]==[1,1,1]
    elif case in (69,70):
        s,ctx,oid=paid(sim);item=s.order(ctx,oid)['items'][0]['item_id'];fault_config(s,refund_failures_remaining=1)
        p=s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=[item]))
        failed=s.confirm(ctx,p['proposal_id']);assert failed['status']=='REFUND_FAILED'
        o=s.order(ctx,oid);assert (o['total_fen'],o['refunded_total_fen'],o['fee_total_fen'])==(6000,0,0)
        with s.store.transaction() as c:
            old=dict(c.execute('SELECT * FROM v39_refund_requests').fetchone())
            assert c.execute('SELECT status FROM v39_refund_items').fetchone()[0]=='FAILED'
            assert all(v[0]==3 for v in c.execute('SELECT sold FROM v39_inventory_segments'))
        assert s.confirm(ctx,p['proposal_id'])==failed
        probe(s,case,steps,'failed-replay')
        if case==69:
            p2=s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=[item]));assert p2['proposal_id']!=p['proposal_id']
            assert s.confirm(ctx,p2['proposal_id'])['status']=='PAID'
            with s.store.transaction() as c:
                assert dict(c.execute('SELECT * FROM v39_refund_requests WHERE refund_id=?',(old['refund_id'],)).fetchone())==old
                assert c.execute('SELECT count(*) FROM v39_refund_requests').fetchone()[0]==2
        else:
            with s.store.transaction() as c:assert c.execute("SELECT count(*) FROM v39_transactions WHERE transaction_type='REFUND'").fetchone()[0]==1
    elif case==71:
        s,ctx,oid=paid(sim);item=s.order(ctx,oid)['items'][0]['item_id']
        p=s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=[item]))
        with s.store.transaction() as c:c.execute("UPDATE v39_proposals SET payload_json='{}' WHERE proposal_id=?",(p['proposal_id'],))
        with pytest.raises(ValueError,match='IDEMPOTENCY_CONFLICT'):s.confirm(ctx,p['proposal_id'])
        with s.store.transaction() as c:assert c.execute('SELECT count(*) FROM v39_refund_requests').fetchone()[0]==0
    elif case==72:
        s,ctx,oid=paid(sim);item=s.order(ctx,oid)['items'][0]['item_id']
        ids=[s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=[item]))['proposal_id'] for _ in range(2)]
        assert len(set(ids))==2
        result=clients(s,ctx,ids)
        assert sorted(r['status'] for r in result)==['PAID','REFUND_FAILED']
        with s.store.transaction() as c:
            assert [v[0] for v in c.execute('SELECT status FROM v39_refund_requests ORDER BY status')]==['FAILED','SUCCEEDED']
            assert [v[0] for v in c.execute('SELECT status FROM v39_refund_items ORDER BY status')]==['FAILED','SUCCEEDED']
            assert c.execute("SELECT count(*) FROM v39_transactions WHERE transaction_type='REFUND' AND status='SUCCEEDED'").fetchone()[0]==1
            assert c.execute("SELECT count(*) FROM v39_transactions WHERE transaction_type='REFUND' AND status='FAILED'").fetchone()[0]==1
        for pid,r in zip(ids,result):assert s.confirm(ctx,pid)==r
    elif case==73:
        s,ctx,oid=paid(sim)
        with s.store.transaction() as c:c.execute("UPDATE v39_price_rules SET base_fen_per_segment=900 WHERE seat_class='SECOND'")
        run(s,ctx,'CHANGE',**target(s,ctx,oid,trip_id='T2'))
        o=s.order(ctx,oid);assert all(i['item_status']=='ACTIVE' for i in o['items'])
        assert o['refunded_item_count']==0 and o['refunded_total_fen']==600
        with s.store.transaction() as c:assert c.execute('SELECT count(*) FROM v39_refund_items').fetchone()[0]==0
        probe(s,case,steps,'change-credit-only')
        refund(s,ctx,oid);assert s.order(ctx,oid)['order_status']=='CANCELLED'
    elif case==76:
        s,ctx,oid=paid(sim);item=s.order(ctx,oid)['items'][0]['item_id']
        p=s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=[item]))
        with pytest.raises(ValueError,match='CONFIG_STALE'):s.confirm(replace(ctx,config_hash='new-config'),p['proposal_id'])
        with s.store.transaction() as c:
            assert c.execute('SELECT count(*) FROM v39_refund_requests').fetchone()[0]==0
            assert c.execute('SELECT used_at FROM v39_confirmation_tokens WHERE proposal_id=?',(p['proposal_id'],)).fetchone()[0] is None
    probe(s,case,steps,'final')

def test_refund_technical_failure_rolls_back_everything(sim):
    s,ctx,oid=paid(sim);item=s.order(ctx,oid)['items'][0]['item_id']
    p=s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=[item]))
    before=s.order(ctx,oid)
    with s.store.transaction() as c:c.execute("CREATE TRIGGER refund_technical_fault BEFORE INSERT ON v39_transactions BEGIN SELECT RAISE(ABORT,'REFUND_TECHNICAL_FAULT'); END")
    with pytest.raises(sqlite3.IntegrityError,match='REFUND_TECHNICAL_FAULT'):s.confirm(ctx,p['proposal_id'])
    assert s.order(ctx,oid)==before
    with s.store.transaction() as c:
        assert c.execute('SELECT count(*) FROM v39_refund_requests').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM v39_refund_items').fetchone()[0]==0
        assert c.execute('SELECT used_at FROM v39_confirmation_tokens WHERE proposal_id=?',(p['proposal_id'],)).fetchone()[0] is None
    assert_conserved(s)

def test_p01_boundary_between_preview_confirmation_requires_new_card(sim):
    s,ctx,oid=paid(sim)
    t=datetime(2026,11,6,8,tzinfo=timezone.utc)-timedelta(hours=48,seconds=1)
    s.clock=lambda:t
    p=s.propose(ctx,'REFUND',dict(order_id=oid,scope='FULL'));assert p['preview']['fee_fen']==300
    s.clock=lambda:t+timedelta(seconds=1)
    with pytest.raises(ValueError,match='PROPOSAL_PRICE_STALE'):s.confirm(ctx,p['proposal_id'])
    with s.store.transaction() as c:
        assert c.execute('SELECT count(*) FROM v39_refund_requests').fetchone()[0]==0
        assert c.execute('SELECT used_at FROM v39_confirmation_tokens WHERE proposal_id=?',(p['proposal_id'],)).fetchone()[0] is None
