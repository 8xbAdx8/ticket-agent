"""One owned, committed SQLite snapshot. Never expires or writes business rows."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import json, sqlite3
from target.v39.context import digest


def read(path, ctx, *, now=None, order_id=None):
    ctx.require()
    path=Path(path).resolve()
    from target.v39.store import ROOT, safe_path
    safe_path(path)
    if path.is_relative_to(ROOT/'data/v39'):
        raise ValueError('PRODUCT_DATABASE_READ_BLOCKED')
    stamp=(now or datetime.now(timezone.utc)).isoformat()
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True, isolation_level=None)) as c:
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
        owned=(ctx.session_id,ctx.owner_phone,ctx.scenario_id)
        rows=lambda sql,args=():[dict(r) for r in c.execute(sql,args)]
        orders=rows('SELECT * FROM v39_orders WHERE session_id=? AND owner_phone=? AND scenario_id=? ORDER BY created_at DESC,rowid DESC',owned)
        if ctx.tool_whitelist and 'railway_get_order' not in ctx.tool_whitelist:orders=[]
        if order_id and not any(o['order_id']==order_id for o in orders):raise ValueError('ORDER_FORBIDDEN')
        quotes=rows('SELECT * FROM v39_quotes WHERE session_id=? AND owner_phone=? AND scenario_id=? ORDER BY created_at DESC,rowid DESC',owned)
        proposals=rows('SELECT * FROM v39_proposals WHERE session_id=? AND owner_phone=? AND scenario_id=? ORDER BY created_at,rowid',owned)
        if ctx.tool_whitelist and 'railway_get_order' not in ctx.tool_whitelist:proposals=[p for p in proposals if p['order_id'] is None]
        order_ids={o['order_id'] for o in orders};proposal_ids={p['proposal_id'] for p in proposals}
        operations=[]
        for o in orders:
            oid=o['order_id']
            for table,field in [('v39_order_items','items'),('v39_transactions','transactions'),('v39_refund_requests','refunds'),('v39_change_requests','changes'),('v39_refund_items','refund_items')]:
                o[field]=rows('SELECT * FROM '+table+' WHERE order_id=?',(oid,))
            o['hold']=next(iter(rows('SELECT * FROM v39_holds WHERE hold_id=? AND session_id=? AND owner_phone=? AND scenario_id=?',(o['hold_id'],*owned))),None)
            o['hold_status']=(o['hold'] or {}).get('status','UNKNOWN')
            o['hold_expired_at_read']=bool(o['hold_status']=='ACTIVE' and o['hold']['expires_at']<=stamp)
            o['passenger_ids']=[i['item_id'] for i in o['items'] if i['item_status']=='ACTIVE']
            o['transaction_records']=o['transactions']
            o['inventory']=rows('SELECT i.*,s.quantity AS hold_segment_quantity,s.inventory_role FROM v39_hold_segments s JOIN v39_inventory_segments i USING(scenario_id,dataset_version,trip_id,service_date,seat_class,segment_index) WHERE s.hold_id=? ORDER BY segment_index',(o['hold_id'],))
            o['operation_events']=rows("SELECT * FROM v39_audit_events WHERE aggregate_type='order' AND aggregate_id=? ORDER BY created_at,event_id",(oid,))
            o['pending_proposals']=[p['proposal_id'] for p in proposals if p['order_id']==oid and p['state']=='PENDING' and p['expires_at']>stamp]
            successful=[t for t in o['transactions'] if t['status']=='SUCCEEDED']
            net=sum(t['amount_fen']*(1 if t['direction']=='DEBIT' else -1) for t in successful)
            o['ledger_verified']=net==o['net_paid_fen'] and (o['payment_status']!='SUCCEEDED' or net==o['total_fen']+o['fee_total_fen'])
        events=[]
        quote_ids={q['quote_id'] for q in quotes}
        for e in rows("SELECT * FROM v39_audit_events WHERE aggregate_type='page' AND aggregate_id=? ORDER BY created_at,event_id",(ctx.session_id,)):
            detail=json.loads(e['detail_json']);args=detail.get('args') or {};result=detail.get('result') or {}
            if isinstance(result,dict) and (args.get('scenario_id')==ctx.scenario_id or args.get('proposal_id') in proposal_ids or result.get('order_id') in order_ids or (result.get('quote') or {}).get('quote_id') in quote_ids):events.append(e)
        for p in proposals:
            payload=json.loads(p['payload_json']);p['payload']=payload
            key='confirm:'+ctx.session_id+':'+p['proposal_id']+':'+p['action']
            receipt=next(iter(rows("SELECT * FROM v39_idempotency WHERE scope='confirm' AND key=?",(key,))),None)
            result=json.loads(receipt['response_json']) if receipt else None
            oid=(result or {}).get('order_id') or p.get('order_id')
            order=next((o for o in orders if o['order_id']==oid),None)
            if receipt:
                proof=False
                if order:
                    if p['action']=='CREATE_ORDER':proof=order['proposal_id']==p['proposal_id']
                    elif p['action']=='PAY':proof=any(t['idempotency_key']==p['proposal_id'] and t['transaction_type']=='PAYMENT' and t['status']=='SUCCEEDED' for t in order['transactions'])
                    elif p['action'] in ('REFUND','CANCEL') and (result or {}).get('refund_id'):
                        proof=any(r['refund_id']==result['refund_id'] and r['status']=='SUCCEEDED' for r in order['refunds'])
                    elif p['action']=='CANCEL':proof=order['order_status']=='CANCELLED'
                    elif p['action']=='CHANGE':proof=any(r['idempotency_key']==p['proposal_id'] and r['status']=='CONFIRMED' for r in order['changes'])
                status='FAILED' if receipt['status']=='FAILED' or (result or {}).get('error') else 'SUCCEEDED' if proof else 'UNKNOWN'
            else:
                status='PENDING_CONFIRMATION' if p['state']=='PENDING' and p['expires_at']>stamp else 'FAILED' if p['state'] in ('EXPIRED','SECRET_LOST') or p['state']=='PENDING' else 'NOT_STARTED' if p['state']=='CANCELLED' else 'UNKNOWN'
            confirmation=next((e for e in reversed(events) if e['event_type']=='UI_CONFIRMED_PROPOSAL' and json.loads(e['detail_json']).get('args',{}).get('proposal_id')==p['proposal_id']),None)
            detail=json.loads(confirmation['detail_json']) if confirmation else {}
            operations.append(dict(operation_id=key,proposal_id=p['proposal_id'],order_id=oid,action=p['action'],status=status,
                tool_call_id=detail.get('args',{}).get('tool_call_id'),actual_result=result,database_verified=status=='SUCCEEDED',
                before=detail.get('args',{}).get('before'),after=detail.get('result',{}).get('after'),
                created_at=p['created_at'],finished_at=receipt['created_at'] if receipt else None))
        pending=[p for p in proposals if p['state']=='PENDING' and p['expires_at']>stamp]
        snapshot=dict(schema='ticket-business-read-model/1',session_id=ctx.session_id,source='LOCAL_SQLITE_COMMITTED',
            scenario_id=ctx.scenario_id,orders=orders,quotes=quotes,pending_proposals=pending,proposals=proposals,
            operations=operations,operation_events=events+[e for o in orders for e in o['operation_events']],updated_at=stamp)
        snapshot['state_sha256']=digest({k:v for k,v in snapshot.items() if k!='updated_at'})
        return snapshot


def brief(order):
    if not order:return None
    keys=('order_id','trip_id','service_date','seat_class','order_status','payment_status','refund_status','change_status','hold_status','passenger_ids','total_fen','paid_total_fen','refunded_total_fen','fee_total_fen','net_paid_fen','version')
    return {k:order.get(k) for k in keys}


def status_text(order):
    text=f"订单 {order['order_id']} 当前已提交状态：{order['order_status']}；模拟支付 {order['payment_status']}；有效乘客 {order['active_item_count']} 人。"
    if order['hold_status']=='ACTIVE':
        text+=f" 建单流程自动锁定模拟座位，锁定编号 {order['hold_id']}，有效期至 {order['hold']['expires_at']}。"
    if order['payment_status']=='SUCCEEDED':
        tx=[t['transaction_id'] for t in order['transactions'] if t['status']=='SUCCEEDED' and t['transaction_type']=='PAYMENT']
        text+=' 成功模拟支付流水：'+('、'.join(tx) if tx else '未能核验，需检查账本')+'。'
    return text+' 所有交易均为本地模拟。'
