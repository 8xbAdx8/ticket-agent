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
    if future and not future.done():return True
    active=[r for r in getattr(session,'operations',[]) if r['status'] in ACTIVE_STATES]
    # A QUEUED row with no run_id means the worker never entered Conversation.send
    # (or died before observe()).  Such a row is persisted in session-replay.json
    # and would otherwise block every later message after a restart.  Release it
    # once, with a visible state, instead of leaving the UI stuck on 请求已排队.
    if active and all(r['status']=='QUEUED' and not r.get('run_id') for r in active):
        with LOCK:
            for row in active:
                row['status']='CANCELLED'
                row['stage']='上一条请求未完成，已释放排队，请重新发送。'
                row['ended_at']=now()
                row['error']=dict(category='request_not_started')
            try:session.save_replay()
            except Exception:pass
        return False
    return bool(active)


def _declined(sid,reason):
    """Never fail silently: the user panels render this notice on the next run."""
    import streamlit as st
    st.session_state['feature_notice_'+sid]=reason
    return False


def enqueue(sid,message,entry='shortcut',label=None,origin=None):
    import streamlit as st
    session=next((s for s in st.session_state.get('user_sessions',[]) if s.sid==sid),None)
    if session and session.read_only:
        return _declined(sid,'这是保存的历史会话，仅供查看；请新建会话后再发起查询。')
    if session and (busy(session) or session.pending_action()):
        return _declined(sid,'上一条请求仍在处理或等待确认，请稍后再试；没有重复提交。')
    if st.session_state.get('agent_submission'):
        return _declined(sid,'已有一条请求在排队，请稍后再试；没有重复提交。')
    st.session_state.pop('feature_notice_'+sid,None)
    st.session_state['agent_submission']=dict(sid=sid,message=message,entry=entry,label=label or message,
        origin=origin or {},request_id=uuid.uuid4().hex)
    return True


def consume(session):
    import streamlit as st
    row=st.session_state.pop('agent_submission',None)
    return row if row and row['sid']==session.sid and not session.read_only and not busy(session) else None


def quick_message(session,name):
    """Informational shortcut wording, retained for callers that still need it.

    '查余票' is deliberately absent: that shortcut only opens its form now.
    The old shortcut embedded '出发站编码AOH' / '到达站编码HGH' together with a
    hard-coded service date; it bypassed the conditions the customer had just
    entered (client handover note, finding #2).  Station codes now come from
    the two-level picker in user_features.ticket_search_panel, and the date
    from railway_defaults.default_service_date() — never from this module.
    """
    return {'问政策':'查询与当前问题相关的项目示例退改政策，条件不足时请询问。',
        '看订单':'查询我当前的订单，只读取本人订单。',
        '退票费率':'查询项目示例退票手续费规则，计算前请确认票价和发车时间。',
        '行李费用':'查询项目示例行李重量、尺寸和超重费用规定，计算前请确认所需信息。',
        '改签':'查看我的订单并查询可改签方案；不要直接执行改签，交易仍需确认。'}.get(name)


def launch(sid,name):
    """One contract for all six shortcuts: button = open panel only.

    The panel's own submit action issues exactly one request, carrying the
    conditions the customer actually entered.
    """
    from web.user_features import open_panel
    open_panel(sid,name)


def begin(session,message,request_id,entry,hash_text=None):
    """Create the QUEUED row.

    ``message`` is the customer's own wording (shown on the operation row);
    ``hash_text`` is what the backend will actually receive.  Conversation.send
    verifies ``input_hash == digest(message_it_received)``, so when A-side
    intake re-routes the text the hash must be taken from the re-routed text,
    otherwise every request dies as a silent QUEUED row.
    """
    from target.diagnostics import digest
    signed=hash_text if hash_text is not None else message
    with LOCK:
        if not hasattr(session,'operations'):session.operations=[]
        previous=next((r for r in session.operations if r['request_id']==request_id),None)
        if previous:
            if previous['input_hash']!=digest(signed):raise ValueError('IDEMPOTENCY_CONFLICT')
            if previous['status'] in ACTIVE_STATES:raise ValueError('请求正在执行，未重复提交')
            if request_id in session.receipts:return previous,False
            raise ValueError('该请求已结束，请主动重试并使用新的请求标识')
        if request_id in session.receipts:return None,False
        if any(r['status'] in ACTIVE_STATES for r in session.operations):raise ValueError('当前会话正在处理另一条请求')
        row=dict(request_id=request_id,input_hash=digest(signed),run_id=None,session_id=session.sid,
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
    labels={'railway_search_stations':'查找车站','railway_query_trips':'查询车次时刻','railway_trip_stops':'查询经停站',
        'railway_check_inventory':'查询余票','railway_quote_fare':'生成报价','railway_get_order':'查询本人订单','search_policy':'检索政策条款',
        'railway_create_order':'生成订单','railway_pay_order':'生成支付确认卡','railway_refund_order':'生成退票确认卡','railway_change_order':'生成改签确认卡','railway_cancel_order':'生成取消确认卡'}
    provider={'mock':'内置规则','deepseek':'DeepSeek','deepseek_live':'DeepSeek','bailian':'Qwen','bailian_live':'Qwen'}.get(row.get('provider'),row.get('provider'))
    try:started=datetime.fromisoformat(row['started_at']).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError,TypeError,KeyError):started=None
    model='本地规则' if row.get('provider')=='mock' else row.get('model')
    if row.get('kind')=='page_business':provider,model='本页办理',None
    executed=[t for t in row.get('tools',[]) if t.get('executed') is not False]
    stage=row.get('stage') or ''
    stage_line='' if stage==label else '<p>'+e(stage)+'</p>'
    return '<div class="ta-operation" data-operation-state="'+e(row['status'])+'"><b>'+e(label)+'</b>'+stage_line+'<small>'+e(provider)+((' · '+e(model)) if model else '')+'</small><p>'+e(row.get('operation'))+'</p><small>开始 '+e(started)+'</small>'+('<p>已处理：'+e('、'.join(labels.get(t['tool'],t['tool']) for t in executed))+'</p>' if executed else '')+('</div>')


def history(session):
    current=[r for r in getattr(session,'operations',[]) if r.get('session_id')==session.sid];known={r.get('run_id') for r in current}
    verified=[]
    snapshot=(getattr(session,'business_view',None) or {}).get('railway')
    event_ids={(__import__('json').loads(e['detail_json']).get('args') or {}).get('operation_id') for e in (snapshot or {}).get('operation_events',[]) if e.get('detail_json')}
    for row in current:
        native_match=any(o['operation_id']==row.get('business_native_operation_id') and o['database_verified'] for o in (snapshot or {}).get('operations',[]))
        if row.get('kind')=='page_business' and row['status']=='SUCCEEDED' and row.get('run_id') not in event_ids and not native_match:
            row=dict(row,status='BLOCKED',stage='订单状态待核验，请稍后查看',error=dict(category='business_receipt_unverified'))
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
        # A-side intake: keep the customer's own wording on the operation row,
        # but hand the backend a query it can actually route.  Without this,
        # undated natural-language trip requests produce zero tool calls.
        from web.railway_queries import normalize_chat_text
        session.pending_select_number=None
        agent_text,service_day=normalize_chat_text(message,session)
        try:
            from web.railway_queries import passenger_hint
            hint=passenger_hint(message)
            if hint:
                session.passenger_hint=hint
                # A widget key that already holds a value overrides the default,
                # so an older empty field would swallow the name just given.
                import streamlit as st
                prefix='business_passengers_'+session.sid
                for key_name in [k for k in st.session_state.keys() if str(k).startswith(prefix)]:
                    st.session_state.pop(key_name,None)
        except Exception:
            pass
        # The hash must match the text Conversation.send() receives (runtime.py
        # verifies it); signing the customer's wording here caused a silent
        # "提交标识不匹配" and left the row QUEUED forever.
        operation,fresh=begin(session,message,request_id,entry,hash_text=agent_text)
        if not fresh:return None
        if service_day:
            try:
                import streamlit as st
                st.session_state['a_trip_day_'+session.sid]=service_day
            except Exception:
                pass
        def work():
            try:
                result=session.send(agent_text,request_id,followup_authorized=authorized,followup_origin=origin,
                    confirmation=confirmation,entry=entry,defer_followups=True,_operation=operation)
                from web.followup_jobs import schedule
                schedule(session,result,authorized=authorized)
                return result
            except Exception as exc:
                # Conversation.send() verifies the operation before entering its
                # own try/finally, so a failure there never reaches finish().
                # Without this guard the UI shows "请求已排队" forever.
                try:
                    if operation.get('status')=='QUEUED':finish(session,operation,error=exc)
                except Exception:
                    pass
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
