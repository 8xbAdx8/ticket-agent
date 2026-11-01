"""Read-only, owned order projection. Never authorizes a business write."""
from contextlib import closing
import json
import sqlite3
import config
from datetime import datetime,timedelta
from target.order_refund import exists,quote


def orders(path, order_id=None):
    if not path.is_file():return []
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        c.row_factory=sqlite3.Row
        sql='SELECT * FROM orders WHERE phone=?';args=[config.CURRENT_USER_PHONE]
        if order_id:sql+=' AND order_id=?';args.append(order_id)
        result=[]
        for row in c.execute(sql+' ORDER BY created_at DESC,order_id',args):
            o=dict(row)
            effective=o['status']
            lock=c.execute('SELECT expire_at FROM locks WHERE lock_id=?',(o['lock_id'],)).fetchone()
            if effective=='pending' and lock and datetime.fromisoformat(lock['expire_at'])<=config.now():effective='expired'
            payment=c.execute('SELECT * FROM demo_payments WHERE order_id=?',(o['order_id'],)).fetchone() if exists(c,'demo_payments') else None
            refund=c.execute('SELECT detail FROM refunds WHERE order_id=?',(o['order_id'],)).fetchone() if exists(c,'refunds') else None
            change=c.execute('SELECT detail FROM reschedules WHERE order_id=?',(o['order_id'],)).fetchone() if exists(c,'reschedules') else None
            inv=c.execute('SELECT * FROM inventory WHERE train_no=? AND date=? AND seat_type=?',(o['train_no'],o['date'],o['seat_type'])).fetchone()
            o.update(payment_record=dict(payment) if payment else None,refund_record=json.loads(refund[0]) if refund else None,
                     reschedule=json.loads(change[0]) if change else None,has_reschedules=bool(change))
            if payment:o['pay_type']=payment['pay_type']
            o['display_status']='已改签' if change and o['status']=='paid' else {'pending':'待支付','paid':'已支付','cancelled':'已取消','refunded':'已退款','expired':'已过期'}.get(effective,'未知')
            o['effective_status']=effective
            o['payment_status']='已记录支付' if payment else '支付记录未提供'
            o['refund_status']=o['refund_record']['status'] if refund else '无退款或取消记录'
            o['reschedule_status']='已改签' if change else '未改签'
            o['original_payment_amount']=payment['amount'] if payment else None
            o['new_ticket_amount']=o['reschedule']['new_amount'] if change else None
            o['difference']=o['reschedule']['difference'] if change else None
            o['from_city']=dict(inv).get('from_city','未记录') if inv else '未记录';o['to_city']=dict(inv).get('to_city','未记录') if inv else '未记录'
            q=quote(c,row)
            if effective=='expired':q={'error':'订单已过期，不能支付或退票'}
            o['refund_quote']=q
            in_time=inv is not None and config.now()<=datetime.fromisoformat(o['date']+' '+inv['depart'])+timedelta(hours=2)
            o['actions']={'pay':{'allowed':effective=='pending','reason':'仅未过期的待支付订单可支付'},
              'refund':{'allowed':'error' not in q,'reason':q.get('error','需要费用预览和确认')},
              'reschedule':{'allowed':o['status']=='paid' and not change and inv is not None and inv['kind']=='高铁' and in_time,'reason':'仅时间有效、未改签的已支付高铁订单可改签'},
              'payment_record':{'allowed':bool(payment),'reason':'没有已记录支付凭证'},'refund_record':{'allowed':bool(refund),'reason':'没有退款/取消记录'}}
            o.pop('phone',None);o['passengers_display']=[n[:1]+'*' for n in json.loads(o['passengers'])]
            result.append(o)
        return result


def consistent(tool_order, current):
    return all(tool_order.get(k)==current.get(k) for k in ('order_id','train_no','date','seat_type','amount','status'))
