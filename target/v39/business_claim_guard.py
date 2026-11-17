"""V3.9 success claims require trusted context, executed evidence and live DB state.

Legacy execution claims remain owned by rag_faithfulness._execution_claims.
This guard covers the separate proposal/confirmation semantics of V3.9.
"""
import json,re,sqlite3
from datetime import datetime,timezone

PATTERNS={
    'inventory':r'(?:已(?:经)?(?:查询|查到|查得).{0,8}(?:余票|库存)|(?:余票|库存)查询成功)',
    'quote':r'(?:已(?:经)?(?:生成|取得|获取).{0,4}报价|报价(?:已生成|成功))',
    'hold':r'(?:已(?:经)?(?:完成)?(?:锁座|锁定(?:座位)?)|锁座(?:成功|完成))',
    'create':r'(?:已(?:经)?(?:完成)?(?:创建订单|建单|下单)|(?:创建订单|建单|下单)(?:成功|完成))',
    'pay':r'(?:已(?:经)?(?:完成)?(?:支付|付款|扣款)|(?:支付|付款)(?:成功|完成))',
    'cancel':r'(?:已(?:经)?取消(?:订单)?|取消成功)',
    'refund':r'(?:已(?:经)?(?:全部|全额)?(?:退款|退票)|(?:退款|退票)成功)',
    'change':r'(?:已(?:经)?改签|改签成功)'}


def claims(reply):
    found=[]
    for line in reply.splitlines():
        if line.lstrip().startswith('>'):continue
        # Quotes introduced as another speaker's words are not current actions.
        line=re.sub(r'(?:用户|您|你|原话|引用).{0,8}[“「\"][^”」\"]*[”」\"]','',line)
        for clause in re.split(r'[。！？!?；;，,\n]|但是|不过|而是|但(?=已|成功)',line):
            for kind,pattern in PATTERNS.items():
                for m in re.finditer(pattern,clause):
                    prefix=clause[:m.start()]
                    if re.search(r'尚未|还没有|未曾|并未|没有|并非|不是|不代表|如果|假如|若|是否|下一步|将会|将要|用户说|之前|此前|历史',prefix):continue
                    if re.search(r'吗|么|？|\?',clause):continue
                    found.append(dict(kind=kind,text=clause.strip(),claim=m.group()))
    return found


def check(reply,events,ctx,db_path,now=None,resolve_train=None,resolve_interval=None,user_message=''):
    asserted=claims(reply);findings=[];supported=[]
    if not asserted:return dict(status='not_applicable',findings=[],checks=[])
    now=now or datetime.now(timezone.utc)
    owned=lambda r: r and all(r.get(k)==v for k,v in [('session_id',ctx.session_id),('owner_phone',ctx.owner_phone),('scenario_id',ctx.scenario_id)])
    valid_events=[e for e in events if e.get('event')=='tool_end' and e.get('executed') is True and e.get('ok') is True and isinstance(e.get('result'),dict)]
    try:
        db=sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    except (sqlite3.Error,OSError):return dict(status='blocked',findings=[dict(reason='state_unavailable',claim=c) for c in asserted],checks=[])
    def get(table,key,value):
        r=db.execute('SELECT * FROM '+table+' WHERE '+key+'=?',(value,)).fetchone()
        return dict(r) if r else None
    def matches_number(numbers,trip_id,day):
        if not numbers:return True
        mapping={r['trip_id']:r.get('trip_short_name') for ev in valid_events if ev.get('tool')=='railway_query_trips' for r in ev['result'].get('data',[]) if isinstance(r,dict)}
        actual=mapping.get(trip_id)
        if actual is None and resolve_train:actual=resolve_train(trip_id,day)
        return numbers==[actual]
    try:
        for claim in asserted:
            ids=re.findall(r'V39-[A-Za-z0-9]+',claim['text']);numbers=re.findall(r'(?<![A-Za-z0-9])[GDCZTKYS]\d{1,6}(?![A-Za-z0-9])',claim['text'])
            dates=re.findall(r'\d{4}-\d{2}-\d{2}',claim['text']);seats=[v for k,v in [('二等座','SECOND'),('一等座','FIRST'),('商务座','BUSINESS')] if k in claim['text']]
            scopes=[(ids,r'V39-[A-Za-z0-9]+'),(numbers,r'(?<![A-Za-z0-9])[GDCZTKYS]\d{1,6}(?![A-Za-z0-9])'),(dates,r'\d{4}-\d{2}-\d{2}')]
            conflict=False
            for values,pattern in scopes:
                expected=list(dict.fromkeys(re.findall(pattern,user_message)))
                if len(expected)==1:
                    if values and list(dict.fromkeys(values))!=expected:conflict=True
                    elif not values:values.extend(expected)
            expected_seat=[v for k,v in [('二等座','SECOND'),('一等座','FIRST'),('商务座','BUSINESS')] if k in user_message]
            if len(expected_seat)==1:
                if seats and seats!=expected_seat:conflict=True
                elif not seats:seats.extend(expected_seat)
            if conflict:
                findings.append(dict(claim=claim,reason='claim_subject_conflicts_with_request'));continue
            proof=None
            # A UI commit is not a ToolMessage. Verify its original confirmation
            # receipt and owned ledger without pretending a new tool executed.
            if claim['kind'] in ('hold','create','pay','cancel','refund','change'):
                tool_for={'create':'railway_create_order','hold':'railway_create_order','pay':'railway_pay_order','cancel':'railway_cancel_order','refund':'railway_refund_order','change':'railway_change_order'}[claim['kind']]
                failed_attempt=any(e.get('tool')==tool_for and e.get('event')=='tool_end' and (e.get('ok') is False or isinstance(e.get('result'),dict) and e['result'].get('status')=='CONFIRMATION_REQUIRED') for e in events)
                from target.v39.read_model import read
                snapshot=read(db_path,ctx,now=now)
                candidates=[o for o in snapshot['orders'] if not ids or [o['order_id']]==list(dict.fromkeys(ids))]
                if not ids:
                    seen={e['result'].get('order_id') for e in valid_events if e.get('tool')=='railway_get_order'}
                    if seen:candidates=[o for o in candidates if o['order_id'] in seen]
                if not failed_attempt and len(candidates)==1:
                    o=candidates[0]
                    action={'hold':'CREATE_ORDER','create':'CREATE_ORDER','pay':'PAY','cancel':'CANCEL','refund':'REFUND','change':'CHANGE'}[claim['kind']]
                    receipt=next((r for r in reversed(snapshot['operations']) if r['order_id']==o['order_id'] and r['action']==action and r['database_verified']),None)
                    ui=any(e['event_type']=='UI_CONFIRMED_PROPOSAL' and json.loads(e['detail_json']).get('args',{}).get('proposal_id')==(receipt or {}).get('proposal_id') for e in snapshot['operation_events'])
                    matching=(not dates or dates==[o['service_date']]) and (not seats or seats==[o['seat_class']]) and matches_number(numbers,o['trip_id'],o['service_date'])
                    if receipt and ui and matching and o['ledger_verified']:
                        kind=claim['kind']
                        valid=(kind=='create' or kind=='hold' and o['hold_status'] in ('ACTIVE','CONSUMED') and not o['hold_expired_at_read'] and o['hold']['remaining_quantity']>0 or kind=='pay' and o['payment_status']=='SUCCEEDED' and o['order_status'] in ('PAID','CHANGED') or kind=='cancel' and o['order_status']=='CANCELLED' or kind=='refund' and (not re.search(r'全部|所有乘客',claim['text']) or o['active_item_count']==0) and ('全额' not in claim['text'] or o['net_paid_fen']==0) or kind=='change' and o['change_status']=='SUCCEEDED')
                        if valid:
                            supported.append(dict(claim=claim,call_id=receipt['tool_call_id'],tool=tool_for,operation_id=receipt['operation_id'],proof_source='committed_confirmation_receipt'))
                            continue
            if claim['kind']=='create':
                # A UI confirmation is a trusted business event even though the
                # model has no ToolMessage for it.  The persisted order is the
                # authority; never infer creation from the word "created".
                for persisted in db.execute('SELECT * FROM v39_orders WHERE session_id=? AND owner_phone=? AND scenario_id=? ORDER BY created_at DESC',(ctx.session_id,ctx.owner_phone,ctx.scenario_id)).fetchall():
                    order=dict(persisted)
                    if order.get('order_status') not in ('PENDING_PAYMENT','PAID','CHANGED'):continue
                    oid=order['order_id']
                    confirmed=False
                    for audit in db.execute("SELECT detail_json FROM v39_audit_events WHERE event_type='UI_CONFIRMED_PROPOSAL' AND aggregate_id=?",(ctx.session_id,)).fetchall():
                        try:
                            detail=json.loads(audit[0] or '{}')
                        except (ValueError,TypeError):
                            continue
                        if (detail.get('args') or {}).get('proposal_id')==order.get('proposal_id') or (detail.get('result') or {}).get('order_id')==oid:
                            confirmed=True;break
                    if not confirmed:continue
                    if ids and [oid]!=list(dict.fromkeys(ids)):continue
                    if dates and dates!=[order['service_date']]:continue
                    if seats and seats!=[order['seat_class']]:continue
                    if not matches_number(numbers,order['trip_id'],order['service_date']):continue
                    proof={'call_id':None,'tool':'railway_create_order'}
                    break
                if proof:
                    supported.append(dict(claim=claim,call_id=proof['call_id'],tool=proof['tool']))
                    continue
            for e in valid_events:
                result=e['result'];args=e.get('args',{});kind=claim['kind'];tool=e.get('tool')
                if kind=='inventory' and tool=='railway_check_inventory' and result.get('status') in ('SIMULATED_AVAILABLE','INVENTORY_SOLD_OUT','INVENTORY_INSUFFICIENT'):
                    # The result is an observation, not a reservation or purchase.
                    if not matches_number(numbers,args.get('trip_id'),args.get('service_date')):continue
                    if dates and dates!=[args.get('service_date')]:continue
                    if seats and seats!=[args.get('seat_class')]:continue
                    if type(result.get('available')) is not int or not resolve_interval:continue
                    interval=resolve_interval(args)
                    persisted=db.execute('SELECT capacity-held-sold FROM v39_inventory_segments WHERE scenario_id=? AND dataset_version=? AND trip_id=? AND service_date=? AND seat_class=? AND segment_index>=? AND segment_index<?',(ctx.scenario_id,interval['dataset_version'],args['trip_id'],args['service_date'],args['seat_class'],interval['origin']['position'],interval['destination']['position'])).fetchall()
                    if persisted and min(r[0] for r in persisted)==result['available']:proof=e;break
                if kind=='quote' and tool=='railway_quote_fare':
                    q=result.get('quote') or {};persisted=get('v39_quotes','quote_id',q.get('quote_id'))
                    if not owned(persisted) or persisted.get('status')!='ACTIVE':continue
                    if datetime.fromisoformat(persisted['expires_at'])<=now:continue
                    quote_ids=re.findall(r'(?<![A-Za-z0-9])Q[A-Za-z0-9]{4,}',claim['text'])
                    if quote_ids and quote_ids!=[persisted['quote_id']]:continue
                    if any(q.get(k)!=persisted.get(k) for k in ('quote_id','trip_id','service_date','seat_class','total_fen','quote_hash')):continue
                    if dates and dates!=[persisted['service_date']] or seats and seats!=[persisted['seat_class']] or not matches_number(numbers,persisted['trip_id'],persisted['service_date']):continue
                    proof=e;break
                if tool!='railway_get_order':continue
                oid=result.get('order_id');order=get('v39_orders','order_id',oid)
                if not owned(order) or ids and ids!=[oid]:continue
                if any(result.get(k)!=order.get(k) for k in ('order_id','trip_id','service_date','seat_class','order_status','payment_status','hold_id','total_fen','paid_total_fen','refunded_total_fen','fee_total_fen','change_count')):continue
                if dates and dates!=[order['service_date']] or seats and seats!=[order['seat_class']]:continue
                if not matches_number(numbers,order['trip_id'],order['service_date']):continue
                if kind=='hold':
                    h=get('v39_holds','hold_id',order['hold_id'])
                    if not owned(h) or h.get('remaining_quantity',0)<=0 or h.get('status') not in ('ACTIVE','CONSUMED'):continue
                    if h.get('order_id')!=oid or any(h.get(k)!=order.get(k) for k in ('trip_id','service_date','seat_class')):continue
                    if h.get('status')=='ACTIVE' and datetime.fromisoformat(h['expires_at'])<=now:continue
                elif kind=='create':
                    if order['order_status'] not in ('PENDING_PAYMENT','PAID','CHANGED'):continue
                elif kind=='pay':
                    tx=db.execute("SELECT 1 FROM v39_transactions WHERE order_id=? AND transaction_type='PAYMENT' AND status='SUCCEEDED'",(oid,)).fetchone()
                    if order['payment_status']!='SUCCEEDED' or order['order_status'] not in ('PAID','CHANGED') or not tx:continue
                elif kind=='cancel':
                    if order['order_status']!='CANCELLED':continue
                elif kind=='refund':
                    if not db.execute("SELECT 1 FROM v39_refund_requests WHERE order_id=? AND status='SUCCEEDED'",(oid,)).fetchone():continue
                    if re.search(r'全部|所有乘客',claim['text']) and order['active_item_count']!=0:continue
                    if '全额' in claim['text'] and order['net_paid_fen']!=0:continue
                elif kind=='change':
                    if order['order_status']!='CHANGED' or order['change_status']!='SUCCEEDED' or not db.execute("SELECT 1 FROM v39_change_requests WHERE order_id=? AND status='CONFIRMED'",(oid,)).fetchone():continue
                else:continue
                proof=e;break
            if proof:supported.append(dict(claim=claim,call_id=proof.get('call_id'),tool=proof.get('tool')))
            else:findings.append(dict(claim=claim,reason='no_matching_executed_persisted_state'))
    except (sqlite3.Error,ValueError,TypeError,KeyError):
        findings.append(dict(reason='state_validation_unavailable'))
    finally:db.close()
    return dict(status='blocked' if findings else 'supported',findings=findings,checks=supported)


def apply(reply,events,user_message=''):
    from target.v39.context import CURRENT
    from target.v39.registry import SERVICE
    ctx=CURRENT.get();service=SERVICE.get()
    if not ctx or not ctx.enabled or ctx.execution_mode=='baseline' or not service:return reply,None
    options=dict(now=service.now(),user_message=user_message,
        resolve_train=lambda tid,day:service.static.trip(tid,day)['data']['trip']['trip_short_name'],
        resolve_interval=lambda a:service.static.interval(a['trip_id'],a['service_date'],a['origin_stop_id'],a['destination_stop_id']))
    result=check(reply,events,ctx,service.store.path,**options)
    if result['status']=='blocked':
        projected=check('库存查询成功。已生成报价。已锁座。已创建订单。已支付。',events,ctx,service.store.path,**options)
        supported={c['claim']['kind']:c for c in projected['checks']}
        lines=['模型的业务成功声明未获匹配凭据支持，已改为以下核验状态：']
        for kind in ('inventory','quote'):
            proof=supported.get(kind)
            if proof:
                e=next(e for e in events if e.get('call_id')==proof['call_id'] and e.get('event')=='tool_end')
                if kind=='inventory':lines.append('模拟余票查询结果：'+str(e['result']['available'])+'张。')
                else:lines.append('模拟报价：'+format(e['result']['quote']['total_fen']/100,'.2f')+'元。')
        from target.v39.read_model import read,status_text
        snapshot=read(service.store.path,ctx,now=service.now())
        pending_actions=snapshot['pending_proposals'];orders=snapshot['orders']
        import re
        mentioned=set(re.findall(r'V39-[a-f0-9]{32}',user_message+' '+reply))
        actual=[o for o in orders if not mentioned or o['order_id'] in mentioned]
        for order in actual:
            lines.append(status_text(order))
        for kind,label in [('hold','锁座'),('create','建单'),('pay','支付')]:
            if kind in supported:
                lines.append(label+'：已核验相应凭据。')
            elif kind=='create' and any(p.get('action')=='CREATE_ORDER' for p in pending_actions):
                p=next(p for p in pending_actions if p.get('action')=='CREATE_ORDER')
                lines.append('建单：待你在界面确认（提案 '+str(p.get('proposal_id'))+'），尚未创建订单。')
            elif kind=='create' and orders:
                o=orders[0]
                lines.append('建单：已生成订单 '+o['order_id']+'，当前状态 '+o['order_status']+'。')
            elif kind=='pay' and actual and all(o['payment_status']=='SUCCEEDED' for o in actual):
                lines.append('本次操作的成功声明仍需对应回执；上述订单已有成功模拟支付记录，不代表本轮又支付了一次。')
            elif kind=='hold' and actual and any(o['hold_status'] in ('ACTIVE','CONSUMED') for o in actual):
                lines.append('模拟锁座由建单流程自动产生；锁定编号与数量以对应订单当前记录为准，不表示本轮独立执行锁座。')
            elif kind in ('hold','create','pay'):
                lines.append(label+'：尚无成功证据，不能视为已完成。')
        return '\n'.join(lines),result
    return reply,result
