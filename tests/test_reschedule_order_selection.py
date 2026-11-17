from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import pytest
from target import reschedule,mock_core
from tests.test_refund_by_train import db,rows,dump,count


@pytest.mark.parametrize('target,day,seat,diff',[('G102','2026-12-11','二等座','20'),('G103','2026-12-10','二等座','-20'),('G104','2026-12-10','二等座','0')])
def test_preview_readonly_and_difference(db,target,day,seat,diff):
    before=dump(db);p=reschedule.preview(db,'OD1',target,day,seat)
    assert p['difference']==diff and dump(db)==before and count(db,'reschedules')==0


@pytest.mark.parametrize('target,day,seat',[('NO','2026-12-10','二等座'),('G102','bad','二等座'),('G102','2026-12-11','invalid')])
def test_invalid_target_no_mutation(db,target,day,seat):
    before=dump(db)
    with pytest.raises(ValueError):reschedule.preview(db,'OD1',target,day,seat)
    assert dump(db)==before


@pytest.mark.parametrize('mutation',["UPDATE inventory SET seats_left=4 WHERE train_no='G102'", "UPDATE inventory SET seats_left=0 WHERE train_no='G102'", "UPDATE inventory SET price=121 WHERE train_no='G102'", "UPDATE orders SET amount=101 WHERE order_id='OD1'", "UPDATE orders SET lock_id='OTHER' WHERE order_id='OD1'"])
def test_stale_confirmation_revalidated(db,mutation):
    p=reschedule.preview(db,'OD1','G102','2026-12-11','二等座')
    with sqlite3.connect(db) as c:c.execute(mutation)
    before=dump(db)
    with pytest.raises(ValueError):reschedule.confirm(db,p)
    assert dump(db)==before and count(db,'reschedules')==0


def test_success_updates_stock_order_once_and_blocks_refund(db):
    p=reschedule.preview(db,'OD1','G102','2026-12-11','二等座');reschedule.confirm(db,p)
    assert rows(db,"SELECT train_no,date,seat_type,status,amount FROM orders WHERE order_id='OD1'")==[('G102','2026-12-11','二等座','paid',100)]
    assert rows(db,"SELECT seats_left FROM inventory WHERE train_no IN ('G101','G102') AND seat_type='二等座' ORDER BY train_no")==[(6,),(4,)]
    detail=json.loads(rows(db,'SELECT detail FROM reschedules')[0][0]);assert detail['difference']=='20' and detail['rescheduled_at']
    assert count(db,'demo_payments')==0 and count(db,'refunds')==0
    with pytest.raises(ValueError):reschedule.confirm(db,p)
    with mock_core.database_scope(db):assert mock_core.cancel_order('OD1')['policy_ref']=='P02'


def test_reschedule_transaction_failure_rolls_back_all(db):
    p=reschedule.preview(db,'OD1','G102','2026-12-11','二等座')
    with sqlite3.connect(db) as c:c.executescript("CREATE TRIGGER fail_order BEFORE UPDATE ON orders BEGIN SELECT RAISE(ABORT,'injected'); END;")
    before=dump(db)
    with pytest.raises(sqlite3.IntegrityError):reschedule.confirm(db,p)
    assert dump(db)==before and count(db,'reschedules')==0


def test_concurrent_confirmation_one_success(db):
    proposal=reschedule.preview(db,'OD1','G102','2026-12-11','二等座')
    def run(_):
        try:reschedule.confirm(db,proposal);return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as p:assert sorted(p.map(run,range(2)))==[False,True]
    assert count(db,'reschedules')==1 and rows(db,"SELECT seats_left FROM inventory WHERE train_no='G102'")==[(4,)]


@pytest.mark.parametrize('sql',["UPDATE orders SET status='pending' WHERE order_id='OD1'", "UPDATE orders SET phone='other' WHERE order_id='OD1'", "UPDATE inventory SET kind='机票' WHERE train_no='G101'"])
def test_status_owner_and_rail_constraints(db,sql):
    with sqlite3.connect(db) as c:c.execute(sql)
    before=dump(db)
    with pytest.raises(ValueError):reschedule.preview(db,'OD1','G102','2026-12-11','二等座')
    assert dump(db)==before
