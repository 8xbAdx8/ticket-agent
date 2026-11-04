"""UI intents and durable operation metadata around the existing Conversation."""
import threading,uuid,concurrent.futures
from datetime import datetime,timezone,timedelta
from html import escape

LOCK=threading.RLock()
POOL=concurrent.futures.ThreadPoolExecutor(max_workers=4,thread_name_prefix='ticket-conversation')
ACTIVE_STATES={'QUEUED','RUNNING'}


def now():return datetime.now(timezone.utc).isoformat()


def busy(session):
    future=getattr(session,'_chat_future',None)
    return bool(future and not future.done()) or any(r['status'] in ACTIVE_STATES for r in getattr(session,'operations',[]))


def enqueue(sid,message,entry='shortcut',label=None,origin=None):
    import streamlit as st
    session=next((s for s in st.session_state.get('user_sessions',[]) if s.sid==sid),None)
    if session and (session.read_only or busy(session) or session.pending_action()):return False
    if st.session_state.get('agent_submission'):return False
    st.session_state['agent_submission']=dict(sid=sid,message=message,entry=entry,label=label or message,
        origin=origin or {},request_id=uuid.uuid4().hex)
    return True


def consume(session):
    import streamlit as st
    row=st.session_state.pop('agent_submission',None)
    return row if row and row['sid']==session.sid and not session.read_only and not busy(session) else None


def quick_message(session,name):
    import streamlit as st
    if name=='查余票':
        # The original default route and station IDs are stable GTFS facts.  A
        # city-only prompt is ambiguous (Shanghai has five stations), so the
        # shortcut must carry the explicit station codes rather than asking the
        # user to type them again.
        return '查询2026-11-05 上海虹桥到杭州东的铁路车次；出发站编码AOH，到达站编码HGH。'
    return {'问政策':'查询与当前问题相关的项目示例退改政策，条件不足时请询问。',
        '看订单':'查询我当前的订单，只读取本人订单。',
        '退票费率':'查询项目示例退票手续费规则，计算前请确认票价和发车时间。',
        '行李费用':'查询项目示例行李重量、尺寸和超重费用规定，计算前请确认所需信息。',
        '改签':'查看我的订单并查询可改签方案；不要直接执行改签，交易仍需确认。'}[name]


def launch(sid,name):
    import streamlit as st
    from web.user_features import open_panel
    open_panel(sid,name)
    session=next((s for s in st.session_state.get('user_sessions',[]) if s.sid==sid),None)
    if session:
        enqueue(sid,quick_message(session,name),'quick:'+name,name)


def begin(session,message,request_id,entry):
    from target.diagnostics import digest
    with LOCK:
        if not hasattr(session,'operations'):session.operations=[]
        previous=next((r for r in session.operations if r['request_id']==request_id),None)
        if previous:
            if previous['input_hash']!=digest(message):raise ValueError('IDEMPOTENCY_CONFLICT')
            if previous['status'] in ACTIVE_STATES:raise ValueError('请求正在执行，未重复提交')
            if request_id in session.receipts:return previous,False
            raise ValueError('该请求已结束，请主动重试并使用新的请求标识')
        if request_id in session.receipts:return None,False
        if any(r['status'] in ACTIVE_STATES for r in session.operations):raise ValueError('当前会话正在处理另一条请求')
        row=dict(request_id=request_id,input_hash=digest(message),run_id=None,session_id=session.sid,
            operation=message,entry=entry,provider=session.live_provider if session.live else 'mock',
            model=session.live_model,status='QUEUED',started_at=now(),ended_at=None,tools=[],error=None,
            agent_started=False,stage='请求已排队',tokens=None)
        session.operations.append(row);session.root.mkdir(parents=True,exist_ok=True)
        session.save_replay()
        return row,True


def observe(session,row,event):
    if event.get('session_id')!=session.sid:return
    with LOCK:
        first=not row['run_id'] and event.get('run_id')
        if event.get('run_id'):row['run_id']=event['run_id']
        row['status']='RUNNING';row['agent_started']=True
        row['provider']=event.get('provider') or row['provider'];row['model']=event.get('model') or row['model']
        kind=event.get('event_type');tool=event.get('tool')
        row['stage']={'user_input':'已收到请求','model_start':'Agent正在理解请求',
            'tool_start':'正在调用授权工具','tool_result':'工具已返回结果','railway_tool_result':'工具已返回结果','railway_tool_error':'工具执行失败','model_end':'模型已返回响应',
            'agent_returned':'回答已完成'}.get(kind,row['stage'])
        if kind=='model_start' and row['tools']:row['stage']='Agent正在处理工具结果'
        if kind in ('tool_result','railway_tool_result') and event.get('executed') is True:
            row['tools'].append(dict(tool=tool,call_id=event.get('call_id'),status=event.get('status')))
        if first:session.save_replay()


def finish(session,row,result=None,error=None):
    with LOCK:
        audit=next((a for a in reversed(session.audits) if a.get('trace_id')==row['run_id']),None)
        category=(session.error or {}).get('category') if error else None
        if error:
            blocked=category in ('observed_token_budget_exhausted','permission_denied','invalid_safety_limits') or str(category or '').startswith('acceptance_') or (
                isinstance(error,ValueError) and any(w in str(error) for w in ('权限','授权','只读','确认','未配置','未就绪')))
            row['status']='BLOCKED' if blocked else 'FAILED'
            row['error']=dict(category=category or type(error).__name__)
        else:
            events=(audit or {}).get('framework_events') or []
            recovered={e.get('failed_call_id') for e in events if e.get('event')=='railway_read_recovered'}
            failed=[e for e in events if e.get('event')=='tool_end' and e.get('ok') is False and e.get('call_id') not in recovered]
            unavailable=[e for e in events if e.get('event')=='tool_end' and isinstance(e.get('result'),dict)
                and e['result'].get('status') in ('SOURCE_UNAVAILABLE','OUT_OF_COVERAGE','LIVE_DISABLED','SNAPSHOT_MISSING','SNAPSHOT_EXPIRED','INVALID_SNAPSHOT')]
            proposal=any(e.get('event')=='tool_end' and isinstance(e.get('result'),dict)
                and e['result'].get('status')=='CONFIRMATION_REQUIRED' for e in events)
            row['status']='BLOCKED' if session.pending_action() or proposal or failed or unavailable or not row.get('run_id') else 'SUCCEEDED'
            if row['status']=='BLOCKED':row['error']=dict(category='awaiting_confirmation' if session.pending_action() or proposal else 'tool_not_completed')
        row['ended_at']=now();row['stage']={'SUCCEEDED':'本轮处理结束','FAILED':'请求未完成','BLOCKED':'需要核对或确认'}[row['status']]
        if (row.get('error') or {}).get('category')=='model_output_truncated':row['stage']='模型文字未完整返回；交易状态以数据库为准'
        if result:row['tokens']=result.get('tokens');row['result_summary']=result.get('reply','')[:240]
        if session.live:
            live=getattr(getattr(session.agent,'langchain_engine',None),'last_live_run',None) or {}
            row['tokens']=live.get('tokens');row['observed_tokens']=live.get('observed_tokens')
        if row['run_id']:
            from target.followups import emit_event
            emit_event(session.trace_dir/'run_events.jsonl',row['run_id'],session.sid,'ui_operation_completed',
                operation_status=row['status'],entry=row['entry'],request_id=row['request_id'],agent_started=row['agent_started'])
        session.save_replay()


def markup(row):
    if not row:return ''
    label={'QUEUED':'已排队','RUNNING':'处理中','SUCCEEDED':'本轮处理结束','FAILED':'未完成','BLOCKED':'已拦截 / 等待确认','CANCELLED':'已取消'}.get(row['status'],row['status'])
    if (row.get('error') or {}).get('category')=='awaiting_confirmation':label='等待你确认'
    if (row.get('error') or {}).get('category')=='model_output_truncated':label='回答未完成'
    e=lambda v:escape(str(v or '未记录'))
    labels={'railway_search_stations':'查找车站','railway_query_trips':'查询静态车次','railway_trip_stops':'查询经停站',
        'railway_check_inventory':'查询模拟余票','railway_quote_fare':'生成模拟报价','railway_get_order':'查询本人订单','search_policy':'检索示例政策',
        'railway_create_order':'生成建单提案','railway_pay_order':'生成支付提案','railway_refund_order':'生成退票提案','railway_change_order':'生成改签提案','railway_cancel_order':'生成取消提案'}
    provider={'mock':'离线演示','deepseek':'DeepSeek','deepseek_live':'DeepSeek','bailian':'Qwen','bailian_live':'Qwen'}.get(row.get('provider'),row.get('provider'))
    try:started=datetime.fromisoformat(row['started_at']).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError,TypeError,KeyError):started=None
    model='本地演示' if row.get('provider')=='mock' else row.get('model')
    if row.get('kind')=='page_business':provider,model='本地模拟业务','未调用模型'
    executed=[t for t in row.get('tools',[]) if t.get('executed') is not False]
    stage=row.get('stage') or ''
    stage_line='' if stage==label else '<p>'+e(stage)+'</p>'
    return '<div class="ta-operation" data-operation-state="'+e(row['status'])+'"><b>'+e(label)+'</b>'+stage_line+'<small>'+e(provider)+' · '+e(model)+'</small><p>'+e(row.get('operation'))+'</p><small>开始 '+e(started)+'</small>'+('<p>已执行工具：'+e('、'.join(labels.get(t['tool'],t['tool']) for t in executed))+'</p>' if executed else '')+('</div>')


def history(session):
    current=[r for r in getattr(session,'operations',[]) if r.get('session_id')==session.sid];known={r.get('run_id') for r in current}
    verified=[]
    snapshot=(getattr(session,'business_view',None) or {}).get('railway')
    event_ids={(__import__('json').loads(e['detail_json']).get('args') or {}).get('operation_id') for e in (snapshot or {}).get('operation_events',[]) if e.get('detail_json')}
    for row in current:
        native_match=any(o['operation_id']==row.get('business_native_operation_id') and o['database_verified'] for o in (snapshot or {}).get('operations',[]))
        if row.get('kind')=='page_business' and row['status']=='SUCCEEDED' and row.get('run_id') not in event_ids and not native_match:
            row=dict(row,status='BLOCKED',stage='当前数据库尚未核验该页面操作回执',error=dict(category='business_receipt_unverified'))
        verified.append(row)
    current=verified
    legacy=[]
    for audit in session.audits:
        if audit.get('trace_id') in known:continue
        trace=audit.get('public_trace') or {}
        if trace.get('session_id') and trace['session_id']!=session.sid:continue
        legacy.append(dict(run_id=audit['trace_id'],session_id=session.sid,request_id=audit['trace_id'],
            operation=trace.get('user_msg','历史运行'),entry='saved_trace',provider=audit.get('provider'),model=audit.get('model'),
            started_at=audit.get('timestamp'),ended_at=audit.get('timestamp'),tools=[],agent_started=True,
            status='FAILED' if audit.get('error') or audit.get('contract_returned') is False else 'CANCELLED' if trace.get('user_msg')=='取消模拟操作' else 'SUCCEEDED',
            error=audit.get('error'),stage='来自已保存记录',tokens=trace.get('tokens')))
    return sorted(legacy+current,key=lambda r:r.get('started_at') or '')


def chat_turns(session):
    """Join view-only failures to original public replies without forging Trace."""
    with LOCK:
        records=list(session.history)
        if not getattr(session,'operations',[]):return [(i,r,None) for i,r in enumerate(records)]
        mapping={}
        for i,record in enumerate(records):
            audit=session._audit_for(record)
            if audit:mapping[audit['trace_id']]=(i,record)
        output=[];seen=set()
        for operation in history(session):
            if operation.get('kind')=='page_business':continue
            match=mapping.get(operation.get('run_id'))
            if match:
                output.append((*match,operation));seen.add(match[0])
            elif operation.get('ended_at') and operation['status'] in ('FAILED','BLOCKED','CANCELLED'):
                output.append((None,None,operation))
        return [(i,r,None) for i,r in enumerate(records) if i not in seen]+output


def submit(session,message,request_id,*,entry='chat',origin=None,authorized=False,confirmation=None):
    """No Streamlit calls in this worker: reruns cannot cancel an in-flight Agent."""
    with LOCK:
        if busy(session):return getattr(session,'_chat_future',None)
        session._queued_submission=dict(message=message,request_id=request_id)
        session._chat_notified=False
        operation,fresh=begin(session,message,request_id,entry)
        if not fresh:return None
        def work():
            try:
                result=session.send(message,request_id,followup_authorized=authorized,followup_origin=origin,
                    confirmation=confirmation,entry=entry,defer_followups=True,_operation=operation)
                from web.followup_jobs import schedule
                schedule(session,result,authorized=authorized)
                return result
            except Exception:
                return None  # Conversation preserved the error, audit and final operation.
        session._chat_future=POOL.submit(work)
        return session._chat_future


def cancel_queued(session):
    with LOCK:
        future=getattr(session,'_chat_future',None)
        if not future or not future.cancel():return False
        row=next((r for r in reversed(session.operations) if r['request_id']==session._queued_submission['request_id']),None)
        if row:row.update(status='CANCELLED',stage='已取消排队，尚未调用Agent。',ended_at=now())
        session.save_replay();return True
