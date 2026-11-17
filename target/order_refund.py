"""Owned-order selection and a single refund quote shared by preview/execution."""
import hashlib
import json
from datetime import date as Date, datetime
from decimal import Decimal, ROUND_HALF_EVEN

import config


def exists(c, table):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None


def rescheduled(c, order_id):
    return exists(c,'reschedules') and c.execute('SELECT 1 FROM reschedules WHERE order_id=?',(order_id,)).fetchone() is not None


def voucher_printed(c, order_id):
    # This release has no voucher-print/return endpoint. A recorded printed
    # voucher is conservatively ineligible for online refund (P01/P07).
    return exists(c,'reimbursement_vouchers') and c.execute('SELECT 1 FROM reimbursement_vouchers WHERE order_id=?',(order_id,)).fetchone() is not None


def calculate(amount, departure, *, now=None, status='paid', kind='高铁', changed=False):
    if changed:return {'error':'P02：已改签订单不可退票'}
    try:
        value=Decimal(str(amount))
        if not value.is_finite() or value<=0:raise ValueError('票价必须为正有限数字')
    except Exception as e:raise ValueError('请提供有效票价，不按里程估价') from e
    now=now or config.now()
    seconds=Decimal(str((departure-now).total_seconds()))
    if status=='paid' and seconds<=0:return {'error':'发车后不能退票'}
    rate=(Decimal('.10') if seconds>86400 else Decimal('.30')) if kind=='机票' else (
        Decimal('.05') if seconds>172800 else Decimal('.10') if seconds>=86400 else Decimal('.20'))
    policy='P09' if kind=='机票' else 'P01'
    if status=='pending':rate=Decimal(0);policy='P12'
    amount=Decimal(str(amount))
    fee=(amount*rate).quantize(Decimal('.01'),rounding=ROUND_HALF_EVEN)
    return {'amount':float(amount),'fee_rate':float(rate),'fee':float(fee),'refund':float(amount-fee) if status=='paid' else 0,'policy_ref':policy,'seconds_before_departure':float(seconds)}


def quote(c, order):
    if order['status'] not in ('paid','pending'):
        return {'error':'当前订单状态不可取消或退票','status':order['status']}
    if rescheduled(c,order['order_id']):
        return {'error':'该订单已改签，根据当前示例政策P02，改签后的车票不支持退票。','policy_ref':'P02'}
    if voucher_printed(c,order['order_id']):
        return {'error':'已打印报销凭证，按P01/P07不可在本演示中退票；凭证交回流程尚未提供。','policy_ref':'P01/P07'}
    inv=c.execute('SELECT * FROM inventory WHERE train_no=? AND date=? AND seat_type=?',
                  (order['train_no'],order['date'],order['seat_type'])).fetchone()
    if not inv:return {'error':'原车次资料不可用，无法核对退款'}
    calculated=calculate(order['amount'],datetime.fromisoformat(order['date']+' '+inv['depart']),status=order['status'],kind=inv['kind'])
    if calculated.get('error'):return calculated
    rate=calculated['fee_rate'];fee=calculated['fee'];policy=calculated['policy_ref'];amount=Decimal(str(order['amount']))
    fingerprint=hashlib.sha256(json.dumps({'order':dict(order),'depart':inv['depart'],'kind':inv['kind']},sort_keys=True).encode()).hexdigest()
    return {'order_id':order['order_id'],'status':order['status'],'amount':float(amount),'fee_rate':float(rate),
            'fee':float(fee),'refund':calculated['refund'],
            'policy_ref':policy,'snapshot_sha256':fingerprint}


def match(c, train_no, date, seat_type=None, passenger=None):
    if not date:return {'error':'请补充出行日期，未执行退票。','requires_date':True,'orders':[]}
    if Date.fromisoformat(date).isoformat()!=date:raise ValueError('日期必须为YYYY-MM-DD')
    rows=c.execute("SELECT * FROM orders WHERE phone=? AND train_no=? AND date=? AND status IN ('paid','pending') ORDER BY order_id",
                   (config.CURRENT_USER_PHONE,train_no,date)).fetchall()
    result=[]
    for row in rows:
        if seat_type and row['seat_type']!=seat_type:continue
        names=json.loads(row['passengers'])
        if passenger and passenger not in names:continue
        inv=c.execute('SELECT * FROM inventory WHERE train_no=? AND date=? AND seat_type=?',(row['train_no'],row['date'],row['seat_type'])).fetchone()
        result.append({'order_id':row['order_id'],'train_no':row['train_no'],'date':row['date'],'seat_type':row['seat_type'],
            'from_city':dict(inv).get('from_city','未记录') if inv else '未记录','to_city':dict(inv).get('to_city','未记录') if inv else '未记录',
            'passengers':[n[:1]+'*' for n in names],'amount':row['amount'],'status':row['status'],
            'has_reschedules':rescheduled(c,row['order_id']),'quote':quote(c,row)})
    return {'orders':result,'count':len(result),'message':'' if result else '你没有该车次的可退订单。'}


def page_event(c, action, order_id, result):
    import uuid
    c.execute('CREATE TABLE IF NOT EXISTS page_operations (event_id TEXT PRIMARY KEY,action TEXT,order_id TEXT,source TEXT,detail TEXT,created_at TEXT)')
    c.execute('INSERT INTO page_operations VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,action,order_id,'page',json.dumps(result,ensure_ascii=False),config.now().isoformat()))
