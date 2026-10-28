"""Isolated simulated rail rescheduling, policy P01/P02/P03."""
import json, sqlite3, uuid
from datetime import datetime, timedelta
from decimal import Decimal
from contextlib import closing
import config
from target.mock_core import _release


def _calculate(db, order_id, train_no, date, seat_type):
    order=db.execute('SELECT * FROM orders WHERE order_id=? AND phone=?',(order_id,config.CURRENT_USER_PHONE)).fetchone()
    if not order: raise ValueError('未找到当前模拟用户的订单')
    if order['status'] != 'paid': raise ValueError('目前只支持已支付的模拟订单改签')
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reschedules'").fetchone()
    if exists and db.execute('SELECT 1 FROM reschedules WHERE order_id=?',(order_id,)).fetchone(): raise ValueError('该订单已改签过一次')
    old=db.execute('SELECT * FROM inventory WHERE train_no=? AND date=? AND seat_type=?',(order['train_no'],order['date'],order['seat_type'])).fetchone()
    new=db.execute('SELECT * FROM inventory WHERE train_no=? AND date=? AND seat_type=?',(train_no,date,seat_type)).fetchone()
    if not old or not new: raise ValueError('原车次或目标车次不存在')
    if old['kind']!='高铁' or new['kind']!='高铁': raise ValueError('当前改签仅实现高铁模拟政策')
    if (order['train_no'],order['date'],order['seat_type'])==(train_no,date,seat_type): raise ValueError('请选择不同的目标车次或席别')
    now=config.now(); old_time=datetime.fromisoformat(order['date']+' '+old['depart']); new_time=datetime.fromisoformat(date+' '+new['depart'])
    if new_time<=now: raise ValueError('目标车次已发车')
    delta=old_time-now
    if delta < timedelta(0):
        if train_no == order['train_no']:
            raise ValueError('发车后只能改签到其他车次')
        if -delta > timedelta(hours=2) or new_time.date()!=old_time.date(): raise ValueError('发车后仅支持两小时内改签到原出发日的其他车次')
    elif delta < timedelta(hours=48) and new_time.date()>old_time.date():
        raise ValueError('距发车不足48小时，目标须在原出发日结束前')
    passengers=json.loads(order['passengers']); count=len(passengers)
    if new['seats_left']<count: raise ValueError('目标车次余票不足')
    old_price=Decimal(str(order['amount'])); new_price=Decimal(str(new['price']))*count
    return {'order_id':order_id,'old_train':order['train_no'],'old_date':order['date'],'old_seat':order['seat_type'],
            'new_train':train_no,'new_date':date,'new_seat':seat_type,'passengers':passengers,
            'original_amount':str(old_price),'new_amount':str(new_price),'difference':str(new_price-old_price),
            'policy':['P01','P02','P03'],'note':'差额仅记录模拟应补或应退，不进行支付或退款'}


def preview(path, order_id, train_no, date, seat_type):
    if not path.is_file(): raise ValueError('当前会话尚无模拟订单')
    with closing(sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        return _calculate(db,order_id,train_no,date,seat_type)


def confirm(path, proposal):
    with closing(sqlite3.connect(path)) as db, db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE')
        actual=_calculate(db,proposal['order_id'],proposal['new_train'],proposal['new_date'],proposal['new_seat'])
        if actual!=proposal: raise ValueError('订单或目标价格已变化，请重新预览')
        db.execute('CREATE TABLE IF NOT EXISTS reschedules (order_id TEXT PRIMARY KEY, record_id TEXT NOT NULL, detail TEXT NOT NULL)')
        count=len(actual['passengers'])
        changed=db.execute('UPDATE inventory SET seats_left=seats_left-? WHERE train_no=? AND date=? AND seat_type=? AND seats_left>=?',(count,actual['new_train'],actual['new_date'],actual['new_seat'],count)).rowcount
        if changed!=1: raise ValueError('目标余票不足，请重新预览')
        _release(db,actual['old_train'],actual['old_date'],actual['old_seat'],json.dumps(actual['passengers'],ensure_ascii=False))
        db.execute('UPDATE orders SET train_no=?,date=?,seat_type=? WHERE order_id=?',(actual['new_train'],actual['new_date'],actual['new_seat'],actual['order_id']))
        record_id='RS'+uuid.uuid4().hex[:10]
        db.execute('INSERT INTO reschedules VALUES (?,?,?)',(actual['order_id'],record_id,json.dumps(actual,ensure_ascii=False)))
        return {'record_id':record_id,**actual}
