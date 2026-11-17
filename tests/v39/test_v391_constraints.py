from pathlib import Path
import hashlib,sqlite3
import pytest
from target.v39.store import Store,statements
from tests.v39.test_service import sim
from tests.v39.test_lifecycle import paid,run,target

def test_migration_002_failure_rolls_back_both_versions(tmp_path):
    base=Path('target/v39')
    n=0
    for sql in statements('\n'.join((base/name).read_text(encoding='utf8') for name in ('schema.sql','hardening.sql'))):
        body='\n'.join(s for s in sql.splitlines() if not s.lstrip().startswith('--')).strip()
        if body and not body.upper().startswith('PRAGMA'):n+=1
    store=Store(tmp_path/'migration002-fault.sqlite')
    with pytest.raises(RuntimeError,match='INJECTED'):store.initialize(fail_after=n+2)
    with sqlite3.connect(store.path) as c:assert c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]==0

def test_v1_database_is_preserved_without_implicit_upgrade(tmp_path):
    path=tmp_path/'version1.sqlite'
    with sqlite3.connect(path) as c:
        c.executescript('\n'.join(Path('target/v39',name).read_text(encoding='utf8') for name in ('schema.sql','hardening.sql')))
        c.execute("INSERT INTO v39_schema_version VALUES (1,'original',?)",(Store.checksum(),))
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='MIGRATION_REQUIRED'):Store(path).initialize()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before

def test_refunded_item_snapshot_and_success_history_are_immutable(sim):
    s,ctx,oid=paid(sim);item=s.order(ctx,oid)['items'][0]['item_id']
    run(s,ctx,'REFUND',order_id=oid,scope='ITEMS',item_ids=[item])
    with s.store.transaction() as c:
        for sql in ["UPDATE v39_order_items SET item_status='ACTIVE' WHERE item_id=?","UPDATE v39_order_items SET fare_fen=1 WHERE item_id=?","UPDATE v39_item_price_snapshots SET fare_fen=1 WHERE item_id=?","DELETE FROM v39_item_price_snapshots WHERE item_id=?"]:
            with pytest.raises(sqlite3.IntegrityError):c.execute(sql,(item,))
        with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE v39_refund_items SET price_quote_id='unrelated' WHERE order_item_id=?",(item,))

def test_failed_refund_needs_complete_failed_financial_records(sim):
    s,ctx,oid=paid(sim)
    with s.store.transaction() as c:
        s._insert(c,'v39_refund_requests',dict(refund_id='incomplete',order_id=oid,scope='FULL',requested_fen=6000,refundable_fen=6000,fee_fen=300,net_fen=5700,status='PENDING',prior_order_status='PAID',prior_total_fen=6000,idempotency_key='incomplete',created_at=s.stamp()))
        with pytest.raises(sqlite3.IntegrityError,match='INCOMPLETE'):c.execute("UPDATE v39_refund_requests SET status='FAILED' WHERE refund_id='incomplete'")
