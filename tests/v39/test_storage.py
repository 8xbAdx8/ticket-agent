from datetime import datetime,timedelta,timezone
from pathlib import Path
import sqlite3
import pytest
from target.v39.store import Store,integer
from tests.v39.fixtures import seed

@pytest.fixture
def data():
 c,a=seed()
 try:yield c,a
 finally:c.close()

@pytest.mark.parametrize('v',[True,False,0.5,1.0,float('nan'),'2',None,[],{}])
def test_integer_boundary(v):
 with pytest.raises(ValueError):integer(v,'quantity')

def test_migration_rolls_back(tmp_path):
 s=Store(tmp_path/'fault.sqlite')
 with pytest.raises(RuntimeError,match='INJECTED'):s.initialize(fail_after=8)
 with sqlite3.connect(s.path) as c:assert c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]==0

def test_store_identity_and_connection(tmp_path):
 s=Store(tmp_path/'sim.sqlite');s.initialize();s.initialize()
 with s.transaction() as c:
  assert c.execute('PRAGMA foreign_keys').fetchone()[0]==1
  assert c.execute('PRAGMA journal_mode').fetchone()[0]=='wal'

@pytest.mark.parametrize('path',['data/tickets.db','artifacts/runtime/railway-static-phase8-20261102-184912/static.sqlite'])
def test_refuse_protected_path(path):
 with pytest.raises(ValueError,match='PROTECTED_DATABASE'):Store(Path(path))

def test_global_worker_lease(tmp_path):
 s=Store(tmp_path/'lease.sqlite');s.initialize();t=datetime(2026,11,3,tzinfo=timezone.utc)
 a=s.acquire_worker('a',epoch='a1',now=t,ttl=10)
 with pytest.raises(ValueError,match='WORKER_BUSY'):s.acquire_worker('b',epoch='b1',now=t)
 s.renew_worker('a',a,now=t+timedelta(seconds=5),ttl=10)
 with pytest.raises(ValueError,match='WORKER_BUSY'):s.acquire_worker('b',epoch='b1',now=t+timedelta(seconds=11))
 s.acquire_worker('b',epoch='b1',now=t+timedelta(seconds=16))
 assert not s.release_worker('a','a1')
 assert s.release_worker('b','b1')

@pytest.mark.parametrize('sql',[
 "UPDATE v39_transactions SET amount_fen=1 WHERE transaction_id='PAY'",
 "UPDATE v39_transactions SET status='FAILED' WHERE transaction_id='PAY'",
 "DELETE FROM v39_transactions WHERE transaction_id='PAY'",
 "UPDATE v39_transaction_allocations SET amount_fen=1 WHERE allocation_id='AL0'",
 "DELETE FROM v39_transaction_allocations WHERE allocation_id='AL0'",
])
def test_completed_money_is_immutable(data,sql):
 c,_=data
 with pytest.raises(sqlite3.IntegrityError):c.execute(sql)
 assert c.execute("SELECT amount_fen FROM v39_transactions WHERE transaction_id='PAY'").fetchone()[0]==6000

@pytest.mark.parametrize('status',['FAILED','TIMEOUT','SUCCEEDED'])
def test_transactions_start_pending(data,status):
 _,a=data
 with pytest.raises(sqlite3.IntegrityError):a['ins']('v39_transactions',transaction_id='bad',order_id='OA',transaction_type='PAYMENT',direction='DEBIT',amount_fen=1,status=status,idempotency_key='bad')

def test_cross_scope_quote_rejected(data):
 _,a=data
 for kwargs in ({'rule':'RB'},{'version':'v2'}):
  with pytest.raises(sqlite3.IntegrityError):a['quote']('BAD',**kwargs)

def test_parent_hold_identity_rejected(data):
 _,a=data
 with pytest.raises(sqlite3.IntegrityError):a['ins']('v39_hold_segments',hold_id='HT',segment_index=0,inventory_role='NEW')

def test_original_cross_owner_reproduced_and_fixed(data):
 source=Path('artifacts/runtime/v39-architecture-v1.2.2-20261103-121613/schema.sql').read_text(encoding='utf-8')
 c,a=seed(source)
 try:
  c.execute("DELETE FROM v39_hold_segments WHERE hold_id='HA'")
  a['ins']('v39_hold_segments','B',hold_id='HA',segment_index=0,inventory_role='RETAINED',source_hold_id='HB',source_order_id='OB')
  assert c.execute("SELECT source_order_id FROM v39_hold_segments WHERE hold_id='HA'").fetchone()[0]=='OB'
 finally:c.close()
 c,a=data
 with pytest.raises(sqlite3.IntegrityError):a['ins']('v39_hold_segments','B',hold_id='HT',segment_index=0,inventory_role='RETAINED',source_hold_id='HB',source_order_id='OB')
