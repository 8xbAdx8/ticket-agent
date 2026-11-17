"""View-only request feedback derived from existing operation/run events."""
from html import escape

ICONS={'PENDING':'○','RUNNING':'●','SUCCEEDED':'✓','FAILED':'!','BLOCKED':'⊘','WAITING':'◉','UNKNOWN':'○','CANCELLED':'–'}


def tools(events,active):
    rows=[]
    for event in events:
        kind=event.get('event_type');name=event.get('tool')
        if not name or kind not in ('tool_start','tool_result','railway_tool_result','railway_tool_error'):continue
        call=event.get('call_id')
        row=next((r for r in reversed(rows) if call and r['call_id']==call),None)
        if row is None and kind!='tool_start':
            row=next((r for r in reversed(rows) if r['tool']==name and (not call or not r['call_id'])),None)
        if kind=='tool_start':
            if row is None:
                row=dict(tool=name,call_id=call,status='RUNNING');rows.append(row)
        else:
            if row is None:
                row=dict(tool=name,call_id=call);rows.append(row)
            row['status']={'succeeded':'SUCCEEDED','failed':'FAILED','blocked':'BLOCKED'}.get(event.get('status'),'UNKNOWN')
            if event.get('executed') is False:row['status']='BLOCKED'
    # An interrupted or restored run must not animate an old start indefinitely.
    return [dict(r,status='UNKNOWN') if r['status']=='RUNNING' and not active else r for r in rows]


def state(operation,events,*,active=False):
    """No writes, invented tool progress, percentages or simulated token stream."""
    op=operation or {};status=op.get('status','UNKNOWN');category=(op.get('error') or {}).get('category')
    if category=='awaiting_confirmation':return dict(state='WAITING',text='等待你确认',moving=False)
    if status=='UNKNOWN':return dict(state='UNKNOWN',text='数据库结果待核验，请勿重复交易',moving=False)
    if status=='PARTIAL':return dict(state='BLOCKED',text='订单与库存不一致，已停止后续操作',moving=False)
    if status=='FAILED':return dict(state='FAILED',text='请求超时' if category in ('timeout','request_timeout') else '本次请求未完成',moving=False)
    if status=='BLOCKED':return dict(state='BLOCKED',text='本次处理已阻止，请核对详情',moving=False)
    if status=='CANCELLED':return dict(state='CANCELLED',text='请求已取消',moving=False)
    if status=='SUCCEEDED':return dict(state='SUCCEEDED',text='本轮处理结束',moving=False)
    if not active:return dict(state='UNKNOWN',text='历史处理记录 · 当前未执行',moving=False)
    if status=='QUEUED':return dict(state='PENDING',text='请求已排队',moving=False)
    calls=tools(events,True)
    running=[r for r in calls if r['status']=='RUNNING']
    if running:return dict(state='RUNNING',text='正在调用 '+running[-1]['tool'],moving=True)
    waiting=False;generating=False;confirmation=False
    for e in events:
        kind=e.get('event_type')
        if kind=='model_start':waiting=True;generating=False
        elif kind in ('model_delta','model_token'):generating=True
        elif kind in ('model_end','model_error'):waiting=False;generating=False
        elif kind=='confirmation_requested':confirmation=True
        elif kind in ('user_confirmation','confirmation_declined','operation_resumed'):confirmation=False
    if confirmation:return dict(state='WAITING',text='等待你确认',moving=False)
    if generating:return dict(state='RUNNING',text='AI 正在生成回复',moving=True)
    if waiting:return dict(state='RUNNING',text='AI 正在思考',moving=True)
    return dict(state='RUNNING',text='正在处理请求',moving=True)


def markup(view):
    status=view['state'];text=escape(view['text'])
    indicator=('<span class="ta-wait-dots" aria-hidden="true"><i></i><i></i><i></i></span>' if view['moving']
               else '<span class="ta-motion-symbol" aria-hidden="true">'+ICONS[status]+'</span>')
    return f'<div class="ta-request-feedback is-{status.lower()}" role="status" aria-live="polite" aria-atomic="true" data-request-state="{status}">{indicator}<span>{text}</span></div>'


def tool_markup(rows):
    names={'RUNNING':'调用中','SUCCEEDED':'工具返回成功','FAILED':'工具返回失败','BLOCKED':'已拦截，未执行','UNKNOWN':'结果未记录'}
    return '<ul class="ta-motion-tools" aria-label="实际工具状态">'+''.join(
        f'<li data-tool-state="{r["status"]}"><span class="ta-motion-symbol" aria-hidden="true">{ICONS[r["status"]]}</span><span>{escape(r["tool"])}<small>{names[r["status"]]}</small></span></li>' for r in rows)+'</ul>'


def live(session):
    from web import interaction,run_view
    with interaction.LOCK:
        operations=getattr(session,'operations',[])
        operation=dict(operations[-1]) if operations else {}
        active=interaction.busy(session) and not getattr(session,'read_only',False)
    events,_=run_view.load_events(session.trace_dir,operation.get('run_id'),session.sid)
    return operation,events,state(operation,events,active=active)
