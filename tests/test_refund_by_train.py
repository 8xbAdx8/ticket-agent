"""write-code-eval: objective rule -> fixed input -> SQL outcome/failure."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
import sqlite3
from unittest.mock import patch
import pytest
import config
from target import mock_core
from target.order_refund import quote

NOW=datetime(2026,12,8,12)


@pytest.fixture
def db(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'now',lambda:NOW)
    path=tmp_path/'tickets.db'
    with sqlite3.connect(path) as c:
        c.executescript('''CREATE TABLE inventory(kind,train_no,from_city,to_city,date,depart,arrive,seat_type,price,seats_left);
        CREATE TABLE orders(order_id TEXT PRIMARY KEY,phone,train_no,date,seat_type,passengers,amount,status,created_at,lock_id);
        CREATE TABLE locks(lock_id,train_no,date,seat_type,passengers,created_at,expire_at,used);''')
        for train,day,seat,price in [('G101','2026-12-10','二等座',100),('G101','2026-12-10','一等座',150),
            ('G102','2026-12-11','二等座',120),('G103','2026-12-10','二等座',80),('G104','2026-12-10','二等座',100),('MU1','2026-12-10','经济舱',200)]:
            c.execute('INSERT INTO inventory VALUES (?,?,?,?,?,?,?,?,?,?)',('机票' if train=='MU1' else '高铁',train,'上海','杭州',day,'12:00','14:00',seat,price,5))
        for oid,phone,seat,name in [('OD1',config.CURRENT_USER_PHONE,'二等座','张三'),('OD2',config.CURRENT_USER_PHONE,'二等座','李四'),('OD3',config.CURRENT_USER_PHONE,'一等座','张三'),('FOREIGN',config.OTHER_USER_PHONE,'二等座','外人')]:
            names=json.dumps([name],ensure_ascii=False)
            c.execute('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)',(oid,phone,'G101','2026-12-10',seat,names,100,'paid','2026-12-01','L'+oid))
            c.execute('INSERT INTO locks VALUES (?,?,?,?,?,?,?,?)',('L'+oid,'G101','2026-12-10',seat,names,'2026-12-01','2030-01-01',1))
    return path


def rows(db,sql,args=()):
    with sqlite3.connect(db) as c:return c.execute(sql,args).fetchall()


def dump(db):
    return {t:rows(db,'SELECT * FROM '+t+' ORDER BY 1') for t in ('orders','inventory','locks')}


def count(db,table):
    return rows(db,'SELECT COUNT(*) FROM '+table)[0][0] if rows(db,"SELECT 1 FROM sqlite_master WHERE name=?",(table,)) else 0


def get_quote(db,oid='OD1'):
    with sqlite3.connect(db) as c:
        c.row_factory=sqlite3.Row
        return quote(c,c.execute('SELECT * FROM orders WHERE order_id=?',(oid,)).fetchone())


@pytest.mark.parametrize('seat,passenger,expected',[(None,None,['OD1','OD2','OD3']),('二等座',None,['OD1','OD2']),
 ('二等座','张三',['OD1']),('一等座','李四',[]),(None,'外人',[])])
def test_owned_filters_and_no_implicit_cancellation(db,seat,passenger,expected):
    before=dump(db)
    with mock_core.database_scope(db):result=mock_core.cancel_order_by_train('G101','2026-12-10',seat,passenger)
    assert [r['order_id'] for r in result['orders']]==expected
    assert 'FOREIGN' not in json.dumps(result) and config.OTHER_USER_PHONE not in json.dumps(result)
    assert dump(db)==before and count(db,'refunds')==0


@pytest.mark.parametrize('train,day',[('G103','2026-12-10'),('G101','2026-12-11'),('missing','2026-12-10')])
def test_inventory_is_not_an_order_and_exact_date_required(db,train,day):
    with mock_core.database_scope(db):r=mock_core.cancel_order_by_train(train,day)
    assert r['orders']==[] and r['message']=='你没有该车次的可退订单。'


def test_missing_date_does_not_guess(db):
    with mock_core.database_scope(db):r=mock_core.cancel_order_by_train('G101',None)
    assert r['requires_date'] and not r['orders']


@pytest.mark.parametrize('hours,rate',[(49,.05),(48,.10),(47,.10),(24,.10),(23,.20)])
def test_fixed_time_fee_boundaries_and_persisted_money(db,hours,rate):
    depart=datetime(2026,12,10,12)
    with patch('config.now',return_value=depart-timedelta(hours=hours)),mock_core.database_scope(db):
        p=get_quote(db);assert p['fee_rate']==rate
        result=mock_core.cancel_order('OD1',expected=p)
    assert result['status']=='refunded' and result['fee']==100*rate and result['refund']==100-100*rate
    recorded=json.loads(rows(db,'SELECT detail FROM refunds WHERE order_id=?',('OD1',))[0][0])
    assert recorded==result and recorded['refunded_at'] and recorded['order_id']=='OD1'
    assert rows(db,'SELECT status FROM orders WHERE order_id=?',('OD1',))==[('refunded',)]


def test_decimal_rounding(db):
    with sqlite3.connect(db) as c:c.execute("UPDATE orders SET amount=33.33 WHERE order_id='OD1'")
    with mock_core.database_scope(db):r=mock_core.cancel_order('OD1')
    assert r['fee']==3.33 and r['refund']==30.0


def test_pending_zero_fee_and_single_inventory_release(db):
    with sqlite3.connect(db) as c:c.execute("UPDATE orders SET status='pending' WHERE order_id='OD1'")
    with mock_core.database_scope(db):
        r=mock_core.cancel_order('OD1');assert r['policy_ref']=='P12' and r['fee']==0 and r['refund']==0
        assert 'error' in mock_core.cancel_order('OD1')
    assert count(db,'refunds')==1 and rows(db,"SELECT seats_left FROM inventory WHERE train_no='G101' AND seat_type='二等座'")==[(6,)]


@pytest.mark.parametrize('status',['refunded','cancelled','expired'])
def test_terminal_state_rejects_without_side_effect(db,status):
    with sqlite3.connect(db) as c:c.execute("UPDATE orders SET status=? WHERE order_id='OD1'",(status,))
    before=dump(db)
    with mock_core.database_scope(db):assert 'error' in mock_core.cancel_order('OD1')
    assert dump(db)==before and count(db,'refunds')==0


@pytest.mark.parametrize('offset',[0,1])
def test_departed_paid_order_rejected(db,offset):
    before=dump(db)
    with patch('config.now',return_value=datetime(2026,12,10,12)+timedelta(seconds=offset)),mock_core.database_scope(db):
        assert '发车后' in mock_core.cancel_order('OD1')['error']
    assert dump(db)==before


@pytest.mark.parametrize('oid',['FOREIGN','NO_ORDER'])
def test_unauthorized_and_nonexistent_orders_rejected(db,oid):
    before=dump(db)
    with mock_core.database_scope(db):assert mock_core.cancel_order(oid)=={'error':'订单不存在'}
    assert dump(db)==before and count(db,'refunds')==0


def test_printed_voucher_rejected_by_business_and_quote(db):
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE reimbursement_vouchers(order_id TEXT PRIMARY KEY,printed_at TEXT)')
        c.execute("INSERT INTO reimbursement_vouchers VALUES ('OD1','2026-12-01')")
    before=dump(db);assert get_quote(db)['policy_ref']=='P01/P07'
    with mock_core.database_scope(db):assert '凭证' in mock_core.cancel_order('OD1')['error']
    assert dump(db)==before and count(db,'refunds')==0


def test_stale_quote_refuses_changed_amount(db):
    q=get_quote(db)
    with sqlite3.connect(db) as c:c.execute("UPDATE orders SET amount=101 WHERE order_id='OD1'")
    with mock_core.database_scope(db):assert '变化' in mock_core.cancel_order('OD1',expected=q)['error']
    assert count(db,'refunds')==0


def test_refund_rolls_back_after_inventory_failure(db):
    with sqlite3.connect(db) as c:c.executescript("CREATE TRIGGER fail_stock BEFORE UPDATE ON inventory BEGIN SELECT RAISE(ABORT,'injected'); END;")
    before=dump(db)
    with mock_core.database_scope(db),pytest.raises(sqlite3.IntegrityError):mock_core.cancel_order('OD1')
    assert dump(db)==before and count(db,'refunds')==0


def test_concurrent_refunds_only_one_record_and_one_release(db):
    def perform(_):
        with mock_core.database_scope(db):return mock_core.cancel_order('OD1')
    with ThreadPoolExecutor(max_workers=2) as p:results=list(p.map(perform,range(2)))
    assert sum('error' not in r for r in results)==1 and count(db,'refunds')==1
    assert rows(db,"SELECT seats_left FROM inventory WHERE train_no='G101' AND seat_type='二等座'")==[(6,)]
