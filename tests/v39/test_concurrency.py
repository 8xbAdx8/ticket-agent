"""Multiprocess SQLite writers, using private creation to isolate DB locking.

This does not claim multiple confirmation workers are deployed: production uses
one leased authority. Separate workers below exercise transactions, not a secret
distribution or another public confirmation path.
"""
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
from dataclasses import replace
import os
from target.v39.store import Store
from target.v39.service import Service
from target.v39.context import Context
from tests.v39.test_service import SyntheticStatic,sim

def contender(path,index):
    os.environ['RAILWAY_SIMULATION_ENABLED']='1'
    s=Service(Store(path),SyntheticStatic(),clock=lambda:datetime(2026,11,3,8,tzinfo=timezone.utc))
    ctx=Context('s'+str(index),'u'+str(index),'demo',enabled=True)
    q=s.quote(ctx,trip_id='T',service_date='2026-11-06',origin_stop_id='X',destination_stop_id='Z',seat_class='SECOND',passenger_count=1)['quote']
    # Give each DB-only contender its own correctly scoped proposal. No token
    # is fabricated or exported, and no public confirmation permission is bypassed.
    from target.v39.context import digest
    import json,uuid
    pid='DBTEST-'+uuid.uuid4().hex
    payload=dict(quote_id=q['quote_id'],passengers=['P'])
    from target.v39.service import insert
    with s.store.transaction() as c:
        p=dict(proposal_id=pid,session_id=ctx.session_id,owner_phone=ctx.owner_phone,action='CREATE_ORDER',aggregate_id=q['quote_id'],quote_id=q['quote_id'],scenario_id='demo',confirmation_owner_worker='TEST_ONLY',confirmation_boot_epoch='NO_SECRET',idempotency_key=pid,request_hash=digest(payload),payload_json=json.dumps(payload),state='PENDING',expires_at='2026-11-03T09:00:00+00:00',created_at=s.stamp(),**ctx.snapshot())
        insert(c,'v39_proposals',p)
    try:
        with s.store.transaction() as c:s._create(c,ctx,p,payload)
        return 'CREATED'
    except ValueError as exc:
        if str(exc)!='INVENTORY_INSUFFICIENT':raise
        return str(exc)

def lease_contender(path,index):
    s=Store(path)
    try:s.acquire_worker('w'+str(index),epoch='e'+str(index),now=datetime(2026,11,3,tzinfo=timezone.utc));return 'LEASED'
    except ValueError as exc:return str(exc)

def test_forty_process_requests_capacity_twenty(sim):
    s,ctx=sim
    with ProcessPoolExecutor(max_workers=8) as pool:results=list(pool.map(contender,[str(s.store.path)]*40,range(40)))
    assert results.count('CREATED')==20 and results.count('INVENTORY_INSUFFICIENT')==20
    with s.store.transaction() as c:
        assert c.execute('SELECT count(*) FROM v39_orders').fetchone()[0]==20
        assert [tuple(r) for r in c.execute('SELECT held,sold FROM v39_inventory_segments')]==[(20,0),(20,0)]
        assert c.execute('SELECT sum(delta_held) FROM v39_inventory_events').fetchone()[0]==40
        assert not c.execute('PRAGMA foreign_key_check').fetchall()

def test_global_lease_two_process_contenders(tmp_path):
    path=tmp_path/'lease-race.sqlite';Store(path).initialize()
    with ProcessPoolExecutor(max_workers=2) as pool:results=list(pool.map(lease_contender,[str(path)]*2,range(2)))
    assert sorted(results)==['CONFIRMATION_WORKER_BUSY','LEASED']
