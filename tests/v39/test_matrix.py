"""Versioned V3.9.1 mapping. Original V1.2.2 matrix and failures retained."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,sqlite3
import pytest
from tests.v39.test_service import sim,create,SyntheticStatic
from tests.v39.test_lifecycle import paid,approved,run,target,assert_conserved
from target.v39.context import digest,scope
from target.v39.service import Service
from target.v39.pricing import price,select_rule

class DenseStatic(SyntheticStatic):
    def interval(self,trip_id,service_date,origin_stop_id,destination_stop_id):
        stops=[dict(stop_id=n,sequence_index=(i+1)*10,position=i,departure_at=service_date+'T08:00:00+00:00') for i,n in enumerate(('X','Y','Z','W'))]
        a=['X','Y','Z','W'].index(origin_stop_id);b=['X','Y','Z','W'].index(destination_stop_id)
        if a>=b:raise ValueError('INVALID_INTERVAL')
        return dict(dataset_version='SYNTHETIC_TEST_FIXTURE/v39',source_sha256='synthetic',trip={'trip_id':trip_id},stops=stops,origin=stops[a],destination=stops[b],segments=list(range(a,b)))

def book(s,ctx,count=1,origin='X',destination='Z'):
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id=origin,destination_stop_id=destination,seat_class='SECOND',passenger_count=count)['quote']
    p=s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['P']*count))
    r=s.confirm(ctx,p['proposal_id']);oid=r['order_id']
    run(s,ctx,'PAY',order_id=oid,expected_total_fen=r['total_fen'])
    return oid

def proposal(s,ctx):
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    return s.propose(ctx,'CREATE_ORDER',dict(quote_id=q['quote_id'],passengers=['P']))

def fault_config(s,**kw):
    with s.store.transaction() as c:
        cfg=json.loads(c.execute('SELECT config_json FROM v39_scenarios').fetchone()[0]);cfg.update(kw)
        c.execute('UPDATE v39_scenarios SET config_json=?',(json.dumps(cfg),))

@pytest.mark.parametrize('case',range(1,57),ids=lambda n:f'V39-T{n:03}')
def test_matrix(case,sim,monkeypatch,tmp_path):
    s,ctx=sim
    if case in (1,2,3,4):
        other=replace(ctx,session_id='B',owner_phone='B')
        if case==1:
            p=proposal(s,ctx)
            with s.store.transaction() as c:qid=c.execute('SELECT quote_id FROM v39_proposals').fetchone()[0]
            with pytest.raises(ValueError,match='QUOTE_FORBIDDEN'):s.propose(other,'CREATE_ORDER',dict(quote_id=qid,passengers=['B']))
        elif case==3:
            p=proposal(s,ctx)
            with pytest.raises(ValueError,match='PROPOSAL_NOT_FOUND'):s.confirm(other,p['proposal_id'])
        else:
            _,_,oid=paid(sim)
            if case==2:
                with pytest.raises(ValueError,match='ORDER_FORBIDDEN'):s.order(other,oid)
            else:assert s.order(other)==[] and len(s.order(ctx))==1
    elif case in (5,6,7):
        p=proposal(s,ctx);result=s.confirm(ctx,p['proposal_id'])
        if case==5:assert s.confirm(ctx,p['proposal_id'])==result
        if case==6:
            with s.store.transaction() as c:c.execute("UPDATE v39_proposals SET payload_json='{}' WHERE proposal_id=?",(p['proposal_id'],))
            with pytest.raises(ValueError,match='IDEMPOTENCY_CONFLICT'):s.confirm(ctx,p['proposal_id'])
        if case==7:
            # Caller-supplied alternate keys are not part of this server API.
            with pytest.raises(TypeError):s.confirm(ctx,p['proposal_id'],idempotency_key='new')
        with s.store.transaction() as c:assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==1
    elif case in (8,9,10,33):
        p=proposal(s,ctx)
        if case in (8,33):
            wrong=Service(s.store,s.static,clock=s.clock,worker='B')
            with pytest.raises(ValueError,match='WRONG_WORKER'):wrong.confirm(ctx,p['proposal_id'])
            with s.store.transaction() as c:assert c.execute('SELECT state FROM v39_proposals').fetchone()[0]=='PENDING'
        elif case==9:
            s.close();s.start();assert s.confirm(ctx,p['proposal_id'])['status']=='CONFIRMATION_SECRET_LOST'
        else:
            now=s.now();s.clock=lambda:now+timedelta(seconds=300)
            assert s.confirm(ctx,p['proposal_id'])['status']=='PROPOSAL_EXPIRED'
    elif case==11:
        from tests.v39.test_confirmation_rpc import test_same_proposal_two_process_clients_one_authority
        test_same_proposal_two_process_clients_one_authority(sim)
    elif case==12:
        s,ctx,_,r=create(sim);now=s.now();s.clock=lambda:now+timedelta(seconds=850)
        p=s.propose(ctx,'PAY',dict(order_id=r['order_id'],expected_total_fen=r['total_fen']))
        s.clock=lambda:now+timedelta(seconds=900)
        assert s.expire(ctx)==1
        assert s.confirm(ctx,p['proposal_id'])['status']=='EXPIRED'
        with s.store.transaction() as c:assert c.execute('SELECT count(*) FROM v39_transactions').fetchone()[0]==0
    elif case in (13,14):
        s,ctx,oid=paid(sim);approved(s)
        assert run(s,ctx,'CHANGE',**target(s,ctx,oid,trip_id='T2'))['status']=='CHANGED'
        if case==14:fault_config(s,refund_failures_remaining=1)
        result=run(s,ctx,'REFUND',order_id=oid,scope='FULL')
        assert result['status']==('REFUND_FAILED' if case==14 else 'CANCELLED')
        assert s.order(ctx,oid)['order_status']==('CHANGED' if case==14 else 'CANCELLED')
    elif case in (15,16,17,18):
        s,ctx,oid=paid(sim);approved(s)
        with s.store.transaction() as c:c.execute("UPDATE v39_price_rules SET base_fen_per_segment=? WHERE seat_class='SECOND'",(1200 if case<17 else 900,))
        if case in (16,18):fault_config(s,change_money_failures_remaining=1)
        result=run(s,ctx,'CHANGE',**target(s,ctx,oid,trip_id='T2'))
        assert result['status']==('CHANGE_FAILED' if case in (16,18) else 'CHANGED')
        o=s.order(ctx,oid)
        assert o['total_fen']==(6000 if case in (16,18) else 7200 if case==15 else 5400)
        assert o['paid_total_fen']==(7200 if case==15 else 6000)
        assert o['refunded_total_fen']==(600 if case==17 else 0)
    elif case==19:
        # Accounting unit scenario, not a valid equal-fare partial-refund order.
        # Concrete service lifecycle with nonzero P01 fee is covered by T042.
        from target.v39.accounting import balances
        result=balances([dict(direction='DEBIT',amount_fen=6000,status='SUCCEEDED'),dict(direction='DEBIT',amount_fen=1200,status='SUCCEEDED'),dict(direction='CREDIT',amount_fen=1000,status='SUCCEEDED'),dict(direction='CREDIT',amount_fen=9999,status='FAILED')])
        assert result==dict(paid_total_fen=7200,refunded_total_fen=1000,net_paid_fen=6200)
    elif case==20:
        from target.execution_config import resolve_effective_config,scope as frozen_scope
        from target.v39.registry import definitions,NAMES,service_scope
        from target.tools import TOOLS
        baseline=resolve_effective_config('formal','baseline')
        with frozen_scope(baseline),scope(replace(ctx,tool_whitelist=NAMES)),service_scope(s):
            assert len(definitions(TOOLS))==8
            with pytest.raises(ValueError):s.confirm(ctx,'anything')
    elif case==21:
        from tests.v39.test_concurrency import test_forty_process_requests_capacity_twenty
        test_forty_process_requests_capacity_twenty(sim)
    elif case==22:
        # Fixed 100 operations including expected invalid change attempts after
        # all paid orders are fully refunded. Attempts are not counted successes.
        approved(s);s.static=DenseStatic();orders=[];operations=0
        for i in range(20):
            q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
            r=run(s,ctx,'CREATE_ORDER',quote_id=q['quote_id'],passengers=['P']);orders.append(r['order_id']);operations+=1
        for oid in orders[:10]:run(s,ctx,'PAY',order_id=oid,expected_total_fen=2000);operations+=1
        for oid in orders[10:]:run(s,ctx,'CANCEL',order_id=oid);operations+=1
        for oid in orders[:10]:run(s,ctx,'REFUND',order_id=oid,scope='FULL');operations+=1
        for oid in orders:
            with pytest.raises(ValueError):s.propose(ctx,'CHANGE',dict(order_id=oid))
            operations+=1
        for i in range(30):assert len(s.order(ctx))==20;operations+=1
        assert operations==100
    elif case in (23,24,25,26,27,28):
        s.static=DenseStatic();approved(s);fault_config(s,capacity={'SECOND':1,'FIRST':1,'BUSINESS':1})
        oid=book(s,ctx,origin='X',destination='Y' if case==25 else 'Z')
        change={23:dict(origin_stop_id='Y'),24:dict(origin_stop_id='Y',destination_stop_id='W'),25:dict(origin_stop_id='Z',destination_stop_id='W'),26:dict(trip_id='T2'),27:dict(service_date='2026-11-07'),28:dict(seat_class='FIRST')}[case]
        args=target(s,ctx,oid,**change)
        if case==25:
            other=replace(ctx,owner_phone='other',session_id='other');book(s,other,origin='Z',destination='W')
        result=run(s,ctx,'CHANGE',**args)
        assert result['status']==('CHANGE_FAILED' if case==25 else 'CHANGED')
        with s.store.transaction() as c:
            roles=[r[0] for r in c.execute('SELECT role FROM v39_change_segments')]
            if case in (23,24):assert roles.count('RETAINED')==1
            elif case!=25:assert 'RETAINED' not in roles
        o=s.order(ctx,oid)
        assert o['change_count']==(0 if case==25 else 1)
    elif case==29:
        s,ctx,oid=paid(sim);approved(s);args=target(s,ctx,oid)
        with s.store.transaction() as c:
            q=dict(c.execute('SELECT * FROM v39_quotes WHERE quote_id=?',(args['target_quote_id'],)).fetchone())
            # The attempted cross-dataset quote cannot even be constructed now.
            with pytest.raises(sqlite3.IntegrityError,match='INVENTORY_IDENTITY_MISMATCH'):
                c.execute("INSERT INTO v39_price_rules SELECT 'other-version',version,scenario_id,'d2',trip_id,seat_class,base_fen_per_segment,seat_multiplier_bp,fixed_fee_fen,priority,valid_from,valid_until,'INACTIVE' FROM v39_price_rules WHERE seat_class='SECOND'")
        assert s.order(ctx,oid)['change_count']==0
    elif case in (30,53,55):
        with s.store.transaction() as c:c.execute("UPDATE v39_scenarios SET name='payment_fail'")
        q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=2)['quote']
        r=run(s,ctx,'CREATE_ORDER',quote_id=q['quote_id'],passengers=['A','B'])
        p=s.propose(ctx,'PAY',dict(order_id=r['order_id'],expected_total_fen=4000));result=s.confirm(ctx,p['proposal_id'])
        assert result['status']=='PAYMENT_FAILED' and s.confirm(ctx,p['proposal_id'])==result
        with s.store.transaction() as c:
            assert [tuple(r) for r in c.execute('SELECT held,sold FROM v39_inventory_segments')]==[(0,0),(0,0)]
            assert c.execute('SELECT status FROM v39_transactions').fetchone()[0]=='FAILED'
    elif case==31:
        from tests.v39.test_confirmation_rpc import clients
        s,ctx,oid=paid(sim);approved(s);item=s.order(ctx,oid)['items'][0]['item_id']
        ids=[s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=[item]))['proposal_id'] for _ in range(2)]
        results=clients(s,ctx,ids)
        assert sorted(r['status'] for r in results)==['PAID','REFUND_FAILED']
        with s.store.transaction() as c:
            assert c.execute("SELECT count(*) FROM v39_refund_items WHERE status='SUCCEEDED'").fetchone()[0]==1
            assert c.execute("SELECT count(*) FROM v39_refund_items WHERE status='FAILED'").fetchone()[0]==1
            assert c.execute("SELECT count(*) FROM v39_refund_requests WHERE status='FAILED'").fetchone()[0]==1
        with pytest.raises(ValueError,match='REFUND_ALREADY'):s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=[item]))
    elif case==32:
        s,ctx,oid=paid(sim);approved(s)
        ids=[r['item_id'] for r in s.order(ctx,oid)['items']]+['FOREIGN']
        with pytest.raises(ValueError,match='REFUND_'):s.propose(ctx,'REFUND',dict(order_id=oid,scope='ITEMS',item_ids=ids))
        with s.store.transaction() as c:assert c.execute('SELECT count(*) FROM v39_refund_requests').fetchone()[0]==0
    elif case==34:
        with s.store.transaction() as c:assert c.execute('PRAGMA foreign_keys').fetchone()[0]==1 and c.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
    elif case in (35,36,37):
        p=proposal(s,ctx)
        context={35:replace(ctx,write_policy=(('CREATE_ORDER','deny'),)),36:replace(ctx,enabled=False),37:replace(ctx,execution_mode='baseline')}[case]
        with pytest.raises(ValueError):s.confirm(context,p['proposal_id'])
        with s.store.transaction() as c:assert c.execute('SELECT used_at FROM v39_confirmation_tokens').fetchone()[0] is None
    elif case in (38,39,40,41):
        from tests.v39.test_lifecycle import test_technical_failure_rolls_back_token_and_all_domain_writes
        table={38:'v39_orders',39:'v39_inventory_events',40:'v39_transactions',41:'v39_audit_events'}[case]
        test_technical_failure_rolls_back_token_and_all_domain_writes(sim,table)
    elif case==42:
        from tests.v39.test_lifecycle import test_full_partial_change_failed_refund_retry_lifecycle
        test_full_partial_change_failed_refund_retry_lifecycle(sim)
    elif case in (43,44):
        with s.store.transaction() as c:c.execute("UPDATE v39_price_rules SET base_fen_per_segment=?,seat_multiplier_bp=15000,fixed_fee_fen=? WHERE seat_class='SECOND'",(1235,100 if case==43 else 0))
        s.static=DenseStatic()
        result=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Y',seat_class='SECOND',passenger_count=3)
        assert result['quote']['single_seat_fen']==1853
        assert result['quote']['total_fen']==(5659 if case==43 else 5559)
        if case==43:assert [i['fixed_fee_share_fen'] for i in result['items']]==[34,33,33]
    elif case==45:
        s.static=DenseStatic();oid=book(s,ctx)
        with s.store.transaction() as c:
            assert [r[0] for r in c.execute('SELECT segment_index FROM v39_inventory_segments ORDER BY segment_index')]==[0,1]
            assert [r[0] for r in c.execute('SELECT from_sequence FROM v39_inventory_segments ORDER BY segment_index')]==[10,20]
    elif case in (46,47):
        from target.v39.static import RailwayStatic
        real=RailwayStatic()
        if case==46:
            row=real.trips('2026-11-02',train_no='K5165')['data'][0]
            stops=real.trip(row['trip_id'],'2026-11-02')['data']['stops']
            revision=json.loads(Path('tests/v39/matrices/v391.json').read_text(encoding='utf8'))
            expected=next(r['expected_response'] for r in revision['tests'] if r['test_id']=='V39-T046')
            assert stops[-1]['arrival_at']==expected
        else:
            with real._open() as db:trip=db.db.execute('SELECT trip_id FROM trip_quarantine LIMIT 1').fetchone()[0]
            assert real.trip(trip,'2026-11-03')['status']=='TRIP_QUARANTINED'
    elif case==48:
        s,ctx,p,created=create(sim)
        q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
        with pytest.raises(sqlite3.IntegrityError,match='proposal_id'):
            with s.store.transaction() as c:s._create(c,ctx,dict(proposal_id=p['proposal_id']),dict(quote_id=q['quote_id'],passengers=['P']))
        with s.store.transaction() as c:assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==1
    elif case in (49,50,51):
        old=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
        with s.store.transaction() as c:
            rule=dict(c.execute("SELECT * FROM v39_price_rules WHERE seat_class='SECOND'").fetchone());rule.update(rule_id='specific' if case==49 else 'ambiguous' if case==50 else rule['rule_id'],version=2,trip_id='T' if case==49 else None,valid_from='2026-11-02T00:00:00+00:00')
            if case==51:
                with pytest.raises(sqlite3.IntegrityError,match='OVERLAP_REJECTED'):s._insert(c,'v39_price_rules',rule)
            else:s._insert(c,'v39_price_rules',rule)
        if case==50:
            with pytest.raises(ValueError,match='PRICE_RULE_AMBIGUOUS'):s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)
        elif case==49:assert s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']['rule_id']=='specific'
        with s.store.transaction() as c:assert dict(c.execute('SELECT * FROM v39_quotes WHERE quote_id=?',(old['quote_id'],)).fetchone())==old
    elif case==52:
        s,ctx,oid=paid(sim);approved(s)
        initial=s.now()
        for hours,fee in ((49,300),(36,600),(12,1200)):
            s.clock=lambda:datetime(2026,11,6,8,tzinfo=timezone.utc)-timedelta(hours=hours)
            with s.store.transaction() as c:
                o=dict(c.execute('SELECT * FROM v39_orders').fetchone());items,fees=s._refund_preview(c,o,dict(scope='FULL'))
                assert sum(f['fee_fen'] for f in fees)==fee
                assert sum(f['net_fen'] for f in fees)==6000-fee
        s.clock=lambda:initial
    elif case==54:
        # D7 seed/capacity/rule IDs are deterministic; capability IDs must remain
        # unique. Original matrix's generic 'IDs' does not imply token reuse.
        before=s.order(ctx);s.scenario('demo','SYNTHETIC_TEST_FIXTURE/v39');s.scenario('demo','SYNTHETIC_TEST_FIXTURE/v39')
        with s.store.transaction() as c:
            assert c.execute('SELECT count(*) FROM v39_scenarios').fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM v39_price_rules').fetchone()[0]==3
        assert s.order(ctx)==before
    elif case==56:
        s,ctx,oid=paid(sim);approved(s);args=target(s,ctx,oid,seat_class='FIRST');p=s.propose(ctx,'CHANGE',args)
        original=s.order(ctx,oid)
        with s.store.transaction() as c:c.execute("CREATE TRIGGER ledger_fault BEFORE INSERT ON v39_transactions BEGIN SELECT RAISE(ABORT,'LEDGER_SQL_FAILURE'); END")
        with pytest.raises(sqlite3.IntegrityError,match='LEDGER_SQL_FAILURE'):s.confirm(ctx,p['proposal_id'])
        after=s.order(ctx,oid)
        for key in ('hold_id','quote_id','total_fen','paid_total_fen','order_status','items'):assert original[key]==after[key]
        with s.store.transaction() as c:
            assert c.execute('SELECT count(*) FROM v39_change_requests').fetchone()[0]==0
            assert c.execute('SELECT used_at FROM v39_confirmation_tokens WHERE proposal_id=?',(p['proposal_id'],)).fetchone()[0] is None
    else:raise AssertionError('Unmapped matrix case')
    assert_conserved(s)
