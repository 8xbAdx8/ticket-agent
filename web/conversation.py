"""Ordinary user mode; uses the same Conversation service as the lab.

Layout: hero + quick prompts (fresh conversation) → conversation column with a
run-status rail → composer. Every phase in the rail is read from the events the
current run actually recorded; nothing here infers a call that did not happen.
"""
import uuid
import streamlit as st
from web.design import header, empty, escape, PROCESSING, processing_event
from web.runtime import Conversation, operation_kind, live_ready, failure_hint, tool_failure_hint
from web.presentation import ticket_cards, order_card, policy_cards, TOOL_LABELS
from web import run_view, scroll_bridge
from web import user_copy

QUICK_PROMPTS = (
    ("查余票", "查明天上海到杭州的高铁二等座"),
    ("问政策", "锁座后多久必须完成支付？"),
    ("看订单", "查询我的订单"),
    ("退票费率", "退票手续费怎么算？"),
)


def unsafe_ticket_result(session, record):
    """Display guard only: retain original reply and tool events in the audit."""
    from target.diagnostics import digest
    record_hash=digest(record)
    for audit in reversed(session.audits):
        if audit.get('public_trace_sha256') != record_hash and audit.get('public_trace') != record:
            continue
        judgement=audit.get('judgement') or {}
        if (judgement.get('hallucination') or {}).get('hallucination_detected') is True:
            return True
        return any(a.get('assertion')=='query_result_train_authority' and a.get('passed') is False
                   for a in judgement.get('assertions',[]) if isinstance(a,dict))
    return False


def show_guarded_reply(session, record):
    if unsafe_ticket_result(session,record):
        st.warning('本次回答与查票记录不一致，已暂停展示车次。请在开发者工作空间核查；不要据此订票。')
    else:
        st.write(record['reply'])


def _policy_evidence(hits):
    """保留可供用户核对的条款；检索分数和技术位置在开发者端查看。"""
    with st.expander('参考政策原文', expanded=False):
        st.caption('政策来源：项目内示例政策，仅供演示。')
        if not hits:
            st.caption('本轮没有可引用的政策内容，证据不足。')
        for hit in hits:
            st.write(str(hit.get('doc_id') or '编号未记录') + ' · '
                     + str(hit.get('title') or '标题未记录'))
            st.write(hit.get('content') or '原文未记录')


def show_business(results, session=None):
    successful=[r for r in results if r.get("ok") and isinstance(r.get("result"),dict)]
    if not successful:
        return
    last=successful[-1]
    if last["tool"]=="search_policy":
        hits=last['result'].get('hits') or []
        if hits:
            st.markdown(policy_cards(last["result"]),unsafe_allow_html=True)
        st.caption("政策来源：项目内示例政策，仅供演示；请核对引用原文。")
        _policy_evidence(hits)
    elif last["tool"] in ("create_order","pay_order","cancel_order","query_order"):
        result=last["result"]
        for item in result.get("orders",[result] if result.get("order_id") else []):
            from web.payment import current_order, controls
            item, verified = current_order(session, item)
            from web.order_actions import replay_order,card_actions
            item=replay_order(session,item)
            st.markdown(order_card(item),unsafe_allow_html=True)
            controls(session, item, verified=verified)
            card_actions(session,item,verified)
    elif last["tool"]=="query_tickets":
        st.markdown('<div data-source-tool="' + escape(last['tool']) + '">'
                    + ticket_cards(last["result"]) + '</div>', unsafe_allow_html=True)
        if not last["result"].get("trains"):
            st.info("没有符合条件的班次，请调整路线、日期或席别后再查。")
        st.caption("车票信息：当前使用演示数据，最多展示20条；未提供的信息不作推断，不提供真实出票服务。")


def _followup_lifecycle(session, run_id, kind, **fields):
    """Append one follow-up lifecycle event to the run's existing event chain."""
    if getattr(session,'read_only',False):return
    from target import followups as followup_store
    try:
        followup_store.emit_event(session.trace_dir/'run_events.jsonl', run_id, session.sid, kind, **fields)
    except Exception:
        pass


def _live_request_allowed(session):
    """A live session may send after the user submits the composer; no extra checkbox."""
    return bool(session.live and st.session_state.get('user_compose_session')==session.sid)


def execute(session, message, request_id, origin=None,confirmation=None):
    placeholder=st.empty()
    rag_placeholder=st.empty()
    seen=[]
    previous_run=(session.audits[-1].get('trace_id') if session.audits else None)
    def update(event):
        seen.append(event)
        placeholder.markdown(user_copy.processing_markup(event), unsafe_allow_html=True)
        from web.policy_interaction import policy_view
        view=policy_view(session.sid,event.get('run_id'),events=seen)
        if view['status']!='not_searched':
            rag_placeholder.markdown(_policy_status_markup(view),unsafe_allow_html=True)
    placeholder.markdown(PROCESSING,unsafe_allow_html=True)
    try:
        consent=_live_request_allowed(session)
        origin=origin or {}
        options={'confirmation':confirmation} if confirmation is not None else {}
        session.send(message,request_id,event_callback=update,followup_authorized=consent,
                     followup_origin=origin if origin.get('run_id') else None,**options)
    except Exception:
        from target.reply_consistency import failure_notice
        notice=failure_notice(session.error["category"]) if session.error else None
        detail=tool_failure_hint(session)
        st.error(user_copy.error_message(session.error['category'] if session.error else None))
    finally:
        if session.audits and session.audits[-1].get('trace_id')!=previous_run:
            st.session_state['user_focus_run']=(session.sid,session.audits[-1]['trace_id'])
        placeholder.empty()
        rag_placeholder.empty()


def _turn_policy(session, record):
    """Associate by trace identity, never by audit position (failed runs append audits)."""
    from target.diagnostics import digest
    from web.evidence import read_jsonl
    from web.policy_interaction import policy_view
    identity=digest(record)
    audit=next((a for a in reversed(session.audits)
                if ((a.get('public_trace') or {}).get('session_id')==session.sid and
                    (a.get('public_trace')==record or a.get('public_trace_sha256')==identity))),None)
    run_id=(audit or {}).get('trace_id')
    events,event_meta=run_view.load_events(session.trace_dir,run_id)
    rag_records,meta=read_jsonl(session.trace_dir/'rag_runs.jsonl',limit=10000)
    view=policy_view(session.sid,run_id,events=events,rag_records=rag_records,audit=audit)
    view['read_incomplete']=bool(meta.get('invalid') or meta.get('truncated') or
                                 event_meta.get('invalid') or event_meta.get('truncated'))
    if view['status']=='not_searched' and record.get('tool_sequence'):
        from target.business_state import detect as detect_state
        state=detect_state(events)
        if state:
            view['status_label']='本轮无需政策检索'
            view['reason']='本轮执行的是模拟业务操作（'+str(state.get('state'))+'），没有调用政策检索；追问按业务状态生成。'
            view['business_state']=state.get('state')
    if view['status']=='not_searched' and 'search_policy' in record.get('tool_sequence',[]):
        view['status_label']='检索状态未记录'
        view['reason']='本轮 Trace 有检索调用记录，但缺少可关联的执行旁证，无法确认检索结果。'
    return view


def _policy_status_markup(view):
    return ('<div class="ta-policy-state" role="status" data-state="'+escape(view.get('status','unknown'))+'">'
            '<span class="ta-policy-dot"></span>'+escape(view.get('status_label','检索状态未记录'))+'</div>')


def _policy_panel(view, *, technical=True):
    """保留原诊断组件的默认能力；用户页面显式选择简化展示。"""
    hits = view.get('evidence') or []
    if not hits:
        st.markdown(_policy_status_markup(view), unsafe_allow_html=True)
        if view.get('status') == 'not_searched':
            st.caption('本轮没有查询政策。')
        elif view.get('reason'):
            st.caption('本轮没有可确认的政策内容。请补充问题或稍后重试。')
        if technical:
            st.json(view, expanded=False)
        return
    label = ('政策检索失败 · 本轮较早的参考政策' if view.get('status') == 'failed' else
             '本轮参考政策' if view.get('status') == 'retrieved' else '本轮政策查询未确认成功 · 参考内容')
    with st.expander(label + ' · ' + str(len(hits)) + ' 条', expanded=False):
        st.caption('政策来源：项目内示例政策，仅供演示，不代表现行铁路或航空规定。')
        if view.get('status') != 'retrieved':
            st.warning('最近一次政策查询未确认成功；以下为本轮较早返回的内容。')
        st.caption('找到相关条款不等于回答已被验证，请核对原文和适用条件。')
        if view.get('read_incomplete'):
            st.warning('部分记录无法读取，缺失信息不作推断。')
        for hit in hits:
            st.write('**' + str(hit.get('doc_id') or '编号未记录') + ' · '
                     + str(hit.get('title') or '标题未记录') + '**')
            st.write(hit.get('content') or '原文未记录')
            if technical:
                st.caption('版本：' + str(hit.get('version') or '未记录') + ' · 分数：'
                           + str(hit['score'] if hit.get('score') is not None else '未记录'))
                st.caption('支持最终结论：尚未验证')
        if technical:
            st.json(view, expanded=False)


def _queue_followup(sid, run_id, question):
    st.session_state['user_followup_request']={'sid':sid,'run_id':run_id,'question':question,'request_id':uuid.uuid4().hex}


def _followup_suggestions(session, record, view, offered=None):
    from target.followups import normal
    if view.get('status')=='failed':return
    saved=session.followups_for(record)
    if not saved:return  # Old history has no saved recommendations; no regeneration.
    asked={normal(h['user_msg']) for h in session.history}
    suggestions=[q for q in saved['suggestions'] if normal(q) not in asked]
    # These two existing actions now live on the authoritative order card, with
    # a shared explicit consent and the same atomic backend payment service.
    suggestions=[q for q in suggestions if q not in ('使用支付宝支付','使用微信支付')]
    suggestions=[q for q in suggestions if offered is None or q not in offered]
    if not suggestions:return
    if offered is not None:offered.update(suggestions)
    pending=st.session_state.get('pending_operation') or {}
    ready=(not session.read_only and not session.pending_action() and pending.get('sid')!=session.sid and
           (not session.live or (_live_request_allowed(session) and live_ready(session.live_provider))))
    shown_key='followup_displayed_'+str(view.get('run_id'))
    if not st.session_state.get(shown_key):
        st.session_state[shown_key]=True
        _followup_lifecycle(session,view.get('run_id'),'followup_displayed',
            followup_id=saved.get('followup_id'),generation_method=saved.get('generation_source'),
            provider=(saved.get('provider') if saved.get('generation_source')=='model' else None),
            model=(saved.get('model') if saved.get('generation_source')=='model' else None),
            selected=list(suggestions),latency_ms=saved.get('latency_ms'),
            token_usage=(saved.get('tokens') if saved.get('generation_source')=='model' else None),
            fallback_reason=saved.get('fallback_reason'),next_run_id=None)
    with st.container(key='policy_followups_'+str(view.get('run_id'))):
        st.markdown('**你可能还想了解**')
        st.caption('根据本轮已有信息整理；点击后将作为一条新消息发送，仍需完成必要的操作确认。')
        for n,question in enumerate(suggestions):
            st.button(question,key='policy_followup_'+session.sid+'_'+str(view.get('run_id'))+'_'+str(n),
                      on_click=_queue_followup,args=(session.sid,view.get('run_id'),question),
                      disabled=not ready,width='stretch')
        if session.live:
            st.caption('点击追问与普通消息一样计费；回答后整理追问可能额外使用一次模型服务。')
        if session.live and not ready:
            st.caption('请检查在线服务是否可用，并先完成待确认操作。')


def _consume_followup(session, busy):
    """Revalidate stale buttons and Live consent immediately before dispatch."""
    request=st.session_state.pop('user_followup_request',None)
    if not request:return None
    if request.get('sid')!=session.sid or busy:
        st.info('会话已切换或存在待确认操作，尚未发送这条追问。');return None
    if session.live and (not _live_request_allowed(session) or not live_ready(session.live_provider)):
        st.warning('当前会话或在线服务尚未就绪，这条追问没有发送。请核对当前会话和费用提示。');return None
    from target.followups import normal
    for record in session.history:
        saved=session.followups_for(record)
        if not saved or saved.get('run_id')!=request.get('run_id'):continue
        already={normal(h['user_msg']) for h in session.history}
        allowed=[q for q in saved['suggestions'] if normal(q) not in already]
        if request.get('question') in allowed:
            request['followup_id']=saved.get('followup_id')
            request['generation_method']=saved.get('generation_source')
            request['intent']=saved.get('intent')
            return request
    st.info('这条追问已发送过或没有可关联的本轮政策证据，未重复提交。')
    return None


def _followup_lifecycle_panel(session, events):
    """Independent follow-up lifecycle chain; never presented as a business tool."""
    rows=[e for e in events if str(e.get('event_type','')).startswith('followup_')]
    if not rows:return
    with st.expander('智能追问生命周期（独立事件链）',expanded=False):
        st.caption('与业务五阶段分开记录。未调用模型的事件不填写模型名、Token 或耗时，避免把离线回退伪装成真实调用。')
        for event in rows:
            kind=str(event.get('event_type','')).replace('followup_','')
            method=event.get('generation_method') or '—'
            called=event.get('model_called')
            model=event.get('model') if called is True else ('未调用模型' if called is False else '—')
            tokens=event.get('token_usage')
            token_text=(f"{tokens.get('prompt')}/{tokens.get('completion')}" if isinstance(tokens,dict) else ('未知' if called is True else '—'))
            latency=event.get('latency_ms')
            reason=event.get('fallback_reason')
            extra=[]
            if event.get('selected') and isinstance(event.get('selected'),list):
                extra.append('建议：'+'；'.join(event['selected'][:3]))
            elif event.get('question'):
                extra.append('点击：'+str(event['question']))
            if event.get('next_run_id'):extra.append('下一轮 run_id：'+str(event['next_run_id']))
            st.markdown(f"**{kind}** · 方式 `{method}` · 模型 {model} · Token {token_text} · "
                        f"耗时 {str(latency)+' ms' if isinstance(latency,(int,float)) else '—'}"
                        + (f" · 类型 `{event.get('followup_type')}`" if event.get('followup_type') else '')
                        + (f" · 业务状态 `{event.get('business_state')}`" if event.get('business_state') else '')
                        + (f" · 回退原因 `{reason}`" if reason else ''))
            if extra:st.caption(' · '.join(extra))
            st.caption('event_id '+str(event.get('event_id'))+' · previous '+str(event.get('previous_event_id')))


def _open_user_run(sid, run_id):
    st.session_state['dev_focus']=(sid,run_id)
    st.session_state['workspace_mode']='开发者工作台'


def _run_rail(session, events):
    """保留本轮状态与历史选择；原始事件和审计在开发者端查看。"""
    with st.container(key='user_rail'):
        st.markdown('<div class="ta-rail-head"><b>本次处理</b><span>来自本轮记录</span></div>', unsafe_allow_html=True)
        if not session.audits:
            st.caption('发送消息后，这里显示查询与订单处理的进度。')
            return
        index = len(session.audits) - 1
        if len(session.audits) > 1:
            index = st.selectbox('历史运行', range(len(session.audits)), index=index,
                                 format_func=lambda n: '第' + str(n + 1) + '次处理',
                                 key='user_run_' + session.sid)
        selected = session.audits[index]
        run_id = selected.get('trace_id')
        events, meta = run_view.load_events(session.trace_dir, run_id, session.sid)
        historical = session.read_only or index != len(session.audits) - 1
        st.markdown(user_copy.phase_markup(run_view.phase_states(events)), unsafe_allow_html=True)
        if meta.get('invalid') or meta.get('truncated'):
            st.warning('部分处理记录无法读取，请核对订单状态。')
        if historical:
            st.caption('正在查看已保存的历史记录；不会重新执行操作或产生模型费用。')
        if not events:
            st.caption('暂无可确认的处理进度，不能据此判断操作成功。')
        st.button('在开发者端查看此运行', key='user_to_trace_' + session.sid,
                  on_click=_open_user_run, args=(session.sid, run_id))
        if selected.get('error') or selected.get('contract_returned') is False:
            st.caption('本次处理未完成，请核对订单状态；不会用上次成功的结果代替本次结果。')
            with st.expander('技术诊断说明（开发者）', expanded=False):
                st.caption('本次运行未返回成功契约；不复用上一条成功 Trace。完整诊断在开发者工作空间。')


def _hero():
    st.markdown('<div class="ta-welcome"><div class="ta-eyebrow">出行，从这里开始</div>'
                '<h2>下一段旅程，<br>从一句话开始。</h2>'
                '<p>查车票、问政策、查看订单，用一句话告诉我。'
                '当前使用演示数据和示例政策，不提供真实出票服务。</p></div>',unsafe_allow_html=True)


def _quick_prompts():
    with st.container(key='quick_prompts'):
        columns=st.columns(len(QUICK_PROMPTS))
        for column,(title,text) in zip(columns,QUICK_PROMPTS):
            if column.button(title,key='quick_'+title,width='stretch',help=text):
                st.session_state["user_message"]=text


def _summary_markup(summary):
    run_id = summary.get("run_id") or "未记录"
    short = run_id if len(run_id) <= 16 else run_id[:12] + "…"
    status = summary.get("status") or "未记录"
    tone = {"已完成": "ok", "失败": "bad", "等待确认": "wait", "已拦截": "wait",
            "进行中": "live"}.get(status, "idle")
    return ('<div class="ta-summary">'
            '<div class="ta-summary-top">'
            f'<span class="ta-mode ta-mode-current">{escape(summary.get("mode_label") or "未记录")}</span>'
            f'<span data-run-id="{escape(run_id)}"></span>'
            f'<span class="ta-status ta-status-{tone}">{escape('本轮处理结束' if status == '已完成' else status)}</span>'
            '</div>'
            '<div class="ta-summary-line">本轮结果仅供演示，不代表已出票或真实支付。</div>'
            '</div>')


def _run_summary_bar(session, audit, events, mode_badge):
    """Always-visible description of the run on screen, plus the two jumps."""
    summary = run_view.run_summary(session, audit, events, mode_badge)
    matching=next((i for i,record in enumerate(session.history)
                   if (audit or {}).get('public_trace')==record),None)
    anchor = f"turn_{matching}" if matching is not None else ""
    with st.container(key='run_summary'):
        info, actions = st.columns([3.1, 1.6], gap='small')
        with info:
            st.markdown(_summary_markup(summary), unsafe_allow_html=True)
        with actions:
            jump_run, jump_latest = st.columns(2, gap='small')
            if jump_run.button('回到本次运行', key='scroll_to_run', width='stretch',
                               disabled=not anchor,
                               help='滚动对话到当前运行的结果，并高亮它'):
                scroll_bridge.request('run', anchor)
            if jump_latest.button('回到最新', key='scroll_to_latest', width='stretch',
                                  disabled=not session.history,
                                  help='滚动对话到最后一条消息'):
                scroll_bridge.request('bottom')
    return summary


def _conversation(session):
    """Messages, structured tool results, and the sandbox disclaimer."""
    with st.container(key='user_chat'):
        # Newest turn owns overlapping recommendations; older turns must not
        # consume them before the current answer is rendered.
        latest=session.followups_for(session.history[-1]) if session.history else None
        offered=set((latest or {}).get('suggestions',[]))
        for index, previous in enumerate(session.history):
            with st.container(key=f'turn_{index}'):
                with st.chat_message("user",avatar=":material/person:"):
                    st.write(previous["user_msg"])
                with st.chat_message("assistant",avatar=":material/smart_toy:"):
                    show_guarded_reply(session,previous)
                    view=_turn_policy(session,previous)
                    _policy_panel(view, technical=False)
                    if not unsafe_ticket_result(session,previous):
                        _followup_suggestions(session,previous,view,None if index==len(session.history)-1 else offered)
        if session.history and not session.error:
            if not unsafe_ticket_result(session,session.history[-1]):
                # Policy evidence now lives under its own answer, including history.
                show_business([r for r in session.results[-1] if r.get('tool')!='search_policy'], session)
            record=session.history[-1]
            if any(name in record['tool_sequence'] for name in ('monitor_seat','lock_seat','create_order','pay_order','cancel_order')):
                st.info('本轮仅处理演示订单，不会真实出票或扣款。')
            if any(not c["ok"] for s in record["steps"] for c in s["calls"]):
                st.warning("本轮有操作未成功，请核对订单状态；详细原因可在开发者工作空间查看。")
        if not session.history and not session.pending_action() and not st.session_state.get('guided_demo'):
            st.markdown('<p class="ta-chat-empty">对话会显示在这里；也可以先点上面的快捷问题，或从左侧选择模型新建会话。</p>',
                        unsafe_allow_html=True)


def _confirm_cards(session, action, pending, pending_here):
    """Confirmation cards belong to the conversation column, above the composer."""
    if action:
        with st.container(border=True,key='action_confirm'):
            st.markdown("**请确认本次操作**")
            st.write("操作：" + TOOL_LABELS.get(action['tool'], action['tool']))
            for label, value in user_copy.operation_details(action['args']):
                st.write(label + '：', value)
            st.caption("仅处理演示数据，不会真实出票或扣款；本次确认只适用于上面列出的操作。")
            yes, no = st.columns(2)
            approved = yes.button("确认此模拟操作", type="primary", width="stretch")
            declined = no.button("取消此模拟操作", width="stretch")
            if approved or declined:
                try:
                    session.confirm_action(approved, uuid.uuid4().hex,
                        followup_authorized=_live_request_allowed(session))
                except Exception:
                    st.error("操作未完成，请查看执行记录和订单状态。")
                if session.audits:st.session_state['user_focus_run']=(session.sid,session.audits[-1]['trace_id'])
                st.rerun()
    if pending_here:
        with st.container(border=True,key='pending_confirm'):
            st.markdown("**确认模拟操作**")
            if pending["message"].strip() in {"确认", "确定", "同意", "好的", "可以"} and session.history:
                st.caption("上一轮待确认内容：")
                st.write(session.history[-1].get("reply", ""))
            st.write(pending["message"])
            orders=[r["result"] for full in session.results for r in full if r.get("ok") and r["tool"] in ("create_order","query_order","pay_order") and isinstance(r.get("result"),dict) and r["result"].get("order_id")]
            if orders:
                st.markdown(order_card(orders[-1]),unsafe_allow_html=True)
            else:
                st.caption("尚无可核对的订单金额，请在继续前确认订单信息。")
            st.caption("本次仅改变演示订单状态，不会真实出票或扣款。取消和退票费用按项目示例政策计算。")
            yes,no=st.columns(2)
            if yes.button("确认执行模拟操作",type="primary",width="stretch"):
                st.session_state.pop("pending_operation",None)
                execute(session,pending["message"],pending["request_id"],confirmation={
                    'approved':True,'proposal':{'message':pending['message']},
                    'source_run_id':session.audits[-1].get('trace_id') if session.audits else None})
                st.rerun()
            if no.button("放弃本次操作",width="stretch"):
                st.session_state.pop("pending_operation",None)
                st.rerun()


def _composer(session, live_name):
    """The composer lives in the conversation column so narrow stacking keeps it
    between the transcript and the run-detail panel."""
    with st.container(key='user_compose'):
        if session.live:
            st.caption('当前使用 '+live_name+' 在线服务。发送主问题会产生模型使用费用；回答后整理追问可能额外使用一次模型服务，点击追问按新消息计费。费用仅属于当前会话所用服务。')
            allow_live=True
        else:
            allow_live=False
        with st.form("user_compose",clear_on_submit=True):
            row=st.columns([9,1.4],gap='small')
            message=row[0].text_input("输入消息",key="user_message",
                placeholder="例如：查明天上海到杭州的高铁二等座",label_visibility="collapsed")
            send=row[1].form_submit_button("发送",key='user_send_'+st.session_state['user_submit_nonce'],
                type="primary",disabled=session.read_only or session.live and not live_ready(session.live_provider))
            st.caption("查票、问政策可直接发送；锁座、下单、支付、退票会先请你确认。车票和订单均为演示数据，支付仅模拟状态，不会真实扣款。")
    return message, send, allow_live


def user_page():
    # Clear the composer on the run after a send; a widget key cannot be written
    # once this run has instantiated it.
    if st.session_state.pop('user_clear_input',False):
        st.session_state['user_message']=''
    sessions=st.session_state.setdefault("user_sessions",[])
    def activate(index):
        st.session_state['user_active_session_index']=index
        st.session_state['user_session_index']=index
        st.query_params['session_id']=sessions[index].sid
    def new_session():
        return Conversation("user",engine=st.session_state["default_engine"],live=st.session_state["default_live"],
                            live_provider=st.session_state.get("default_provider","deepseek"),
                            live_model=st.session_state.get("default_live_model"),interactive=True,
                            full_tools=st.session_state['default_live'])
    signature=(st.session_state["default_engine"],st.session_state["default_live"],st.session_state.get("default_provider","deepseek"),st.session_state.get('default_live_model'),'manual-live-v1')
    if not sessions:
        saved_sid=st.query_params.get('session_id')
        restored=None
        if saved_sid:
            try:
                from web.session_store import restore_by_sid
                restored=restore_by_sid(saved_sid)
            except (OSError,ValueError,TypeError,KeyError):
                st.session_state['restore_notice']='未找到完整的本地会话索引，已新建会话；原文件未修改。'
        sessions.append(restored or new_session())
        activate(0)
        st.session_state["user_provider_signature"]=signature
    elif st.session_state.get("user_provider_signature")!=signature:
        sessions.append(new_session())
        activate(len(sessions)-1)
        st.session_state["user_provider_signature"]=signature
    # Widget state is removed when this page is not rendered. Keep active history
    # selection in a non-widget key so a workbench visit cannot switch providers.
    current=st.session_state.get('user_session_index')
    if type(current) is not int or not 0<=current<len(sessions):
        saved=st.session_state.get('user_active_session_index',0)
        activate(max(0,min(saved if type(saved) is int else 0,len(sessions)-1)))
    with st.sidebar:
        if st.button("新建会话",width="stretch"):
            sessions.append(new_session())
            activate(len(sessions)-1)
        index=st.selectbox("历史会话",range(len(sessions)),format_func=lambda i:(sessions[i].history[0]["user_msg"][:18] if sessions[i].history else "新对话")+f" · {i+1}",key="user_session_index")
    st.session_state['user_active_session_index']=index
    session=sessions[index]
    focus=st.session_state.pop('user_focus_run',None)
    if focus and focus[0]==session.sid:
        st.session_state['user_run_'+session.sid]=next((i for i,a in enumerate(session.audits)
            if a.get('trace_id')==focus[1]),max(0,len(session.audits)-1))
    st.query_params['session_id']=session.sid
    if st.session_state.pop('restore_notice',None):st.info('未找到完整的本地会话索引，已新建会话；原文件未修改。')
    if session.read_only:st.info('已打开保存的历史会话，仅供查看，不会重新执行操作或产生模型费用。继续使用请新建会话。')
    if session.persistence_warning:st.warning(session.persistence_warning)
    live_name="Qwen3.8-Flash" if session.live_provider=="bailian" and session.live_model=="qwen3.8-flash" else session.live_model or "Qwen (兼容旧配置)" if session.live_provider=="bailian" else "DeepSeek"
    mode_badge=(live_name+" 在线 · 演示订单" if session.live and session.full_tools
                else live_name+" 在线 · 仅查询" if session.live else "离线演示")
    header("出行助手","查车票、问政策、查看订单，用一句话开始。",mode_badge)
    if (session.engine,session.live,session.live_provider)!=(st.session_state['default_engine'],st.session_state['default_live'],st.session_state.get('default_provider','deepseek')):
        st.info('正在查看历史会话，当前使用 '+(live_name+' 在线服务' if session.live else '离线演示')+'；左侧模型用于新建会话。')
    st.caption("车票信息使用演示数据，政策使用项目内示例条款；订单不真实出票，支付不会真实扣款。" if session.live else "当前为离线演示，不产生模型费用。车票为演示数据，政策为示例条款，不真实出票或扣款。")

    action = session.pending_action()
    pending=st.session_state.get("pending_operation")
    pending_here=bool(pending and pending["sid"]==session.sid)
    busy=bool(action) or pending_here or session.read_only
    followup=_consume_followup(session,busy)
    audit, events, event_meta = run_view.latest_run(session) if session.audits else (None, [], {})
    chosen=st.session_state.get('user_run_'+session.sid)
    if type(chosen) is int and 0<=chosen<len(session.audits):
        audit=session.audits[chosen]
        events,event_meta=run_view.load_events(session.trace_dir,audit.get('trace_id'),session.sid)
    if session.read_only or (audit is not None and audit is not session.audits[-1]):
        mode_badge='历史回放 · '+mode_badge

    welcome = not session.history and not busy
    _run_summary_bar(session, audit, events, mode_badge)

    if session.error:
        st.error(user_copy.error_message(session.error['category']))
        from web.policy_interaction import policy_view
        failed_policy=policy_view(session.sid,(audit or {}).get('trace_id'),events=events,audit=audit)
        if failed_policy['has_recorded_retrieval']:
            st.caption('最近未完成请求的知识库记录；不是上一条成功回答的证据。')
            _policy_panel(failed_policy, technical=False)

    if st.session_state.get('user_compose_session')!=session.sid:
        st.session_state['user_allow_embedding']=False
        st.session_state['user_rag_mode']=session.rag_mode or 'keyword'
        st.session_state['user_compose_session']=session.sid
        st.session_state['user_submit_nonce']=uuid.uuid4().hex

    def _chat_body():
        if welcome:
            _hero()
            from web.user_features import shortcuts
            shortcuts(session.sid)
        if (welcome or st.session_state.get('guided_demo')) and not session.read_only:
            from web.demo import demo_page
            demo_page()
        _conversation(session)
        if followup:
            with st.chat_message('user',avatar=':material/person:'):
                st.write(followup['question'])
            st.toast('已发送追问：'+followup['question'])
            execute(session,followup['question'],followup['request_id'],origin=followup)
            # Preserve the reader's scroll position; the existing bridge follows
            # only readers already at bottom. No explicit bottom jump here.
            st.rerun()

    # One column owns transcript → confirmations → composer so that stacking on
    # a narrow screen keeps the composer above the run-detail panel.
    chat_height = 560 if (session.history or busy) else 430

    def _column_body():
        with st.container(height=chat_height,key='user_chat_scroll'):
            _chat_body()
        if not session.read_only:_confirm_cards(session, action, pending, pending_here)
        return _composer(session, live_name)

    main, rail = st.columns([1.95,1],gap='large')
    with main:
        message, send, allow_live = _column_body()
    with rail:
        from web.user_features import render
        render(session)
        _run_rail(session, events)

    if session.read_only:return

    if session.live:
        with st.expander('高级设置 · 政策查询与费用',expanded=False):
            session.rag_mode=st.selectbox('政策检索方式',['keyword','hybrid','vector'],key='user_rag_mode')
            session.allow_rag_network=st.checkbox('允许本轮联网查询政策向量（可能产生额外费用；仅发送问题时执行）',key='user_allow_embedding')
            st.caption('此选项只授权政策查询所需的向量服务费用，不改变订单操作确认；当前政策仍为项目内示例条款。')

    if session.live and not live_ready(session.live_provider):
        st.info(live_name+" 在线服务暂不可用。可以查看已保存的会话；不会自动切换到其他服务。")
        with st.expander('服务诊断（开发者）', expanded=False):
            st.info('不会自动切换 Mock；当前服务的配置与诊断请在开发者工作空间核对。')
    with st.expander('更多模拟工具 · 行李费用 / 高铁改签',expanded=st.session_state.get('p3_refund_open')==session.sid):
        st.caption('费用计算和改签仅用于演示，不会调用在线模型或产生真实交易。')
        st.caption('行李费用与改签已移至常用功能。')
        from web.order_actions import refund_panel,notice
        refund_panel(session)
        st.caption('改签请先查询演示订单，再点击订单卡片上的“改签”，无需手填订单号。')
        notice(session)
    if send and action:
        st.warning("请先确认或取消待处理的模拟操作。")
    elif send and message.strip():
        from web.user_features import state as feature_state
        context=feature_state(session)
        if context.get('selected_train') and any(w in message for w in ('订','买')):
            t=context['selected_train'];message=f"{message}；车次{t['train_no']}，{t['date']}，{t['seat_type']}"
        if context.get('policy_context') and not operation_kind(message,session.history) and not any(w in message for w in ('订','买')):
            d=context['policy_context'];message+=f"；参考政策{d['doc_id']}（{d['source']}）：{d['content']}"
        from web.order_actions import route_refund_request
        if route_refund_request(session,message):
            st.session_state['user_clear_input']=True
            st.rerun()
        if session.live and not allow_live:
            st.warning("请先确认真实请求费用；尚未调用模型。")
        elif session.live and not session.full_tools and operation_kind(message, session.history):
            st.info("当前 Live 仅支持模拟查票和政策咨询，其余六个工具未开放。未发送请求。")
        else:
            request_id=st.session_state['user_submit_nonce']
            st.session_state['user_submit_nonce']=uuid.uuid4().hex
            if operation_kind(message, session.history) and not (session.interactive and session.live and session.full_tools):
                st.session_state["pending_operation"]={"sid":session.sid,"message":message,"request_id":request_id}
            else:
                execute(session,message,request_id)
            st.session_state['user_clear_input']=True
            scroll_bridge.request('bottom')
            st.rerun()

    # Mounted last so it observes the final layout of this render.
    scroll_bridge.mount(turns=len(session.history))


def show_remote_export(session):
    from target.observability import configuration_status,UPLOAD_SCOPE,export_payload
    state=configuration_status()
    with st.expander("LangSmith 可选远端追踪"):
        label=('配置错误，请检查集成中心' if state['state']=='configuration_error' else
               '未配置LangSmith Key' if not state['key_configured'] else
               '已启用脱敏导出，等待本轮导出核验' if state['enabled'] else '脱敏导出未开启')
        st.caption('状态：'+label+'；打开本区域不会上传。')
        st.write(UPLOAD_SCOPE)
        run=session.agent.langchain_engine.last_live_run if session.agent and session.agent.langchain_engine else None
        if not run:
            model='Qwen3.8-Flash' if session.live_provider=='bailian' else 'DeepSeek'
            st.info('当前 '+model+' 会话还没有已保存的执行记录。请先在下方发送一条消息，模型执行后才能预览并导出到LangSmith。切换模型或打开面板不会产生记录。')
            st.button('导出本轮并验证远端',disabled=True,key='remote_export_'+session.sid)
        if run:
            if run.get('provider')!=session.live_provider+'_live':
                st.error('执行记录的模型来源与当前会话不匹配，已停止导出。请检查Trace或新建会话。')
                return
            st.json(export_payload(run),expanded=False)
            previous=session.latest_remote_receipt()
            if previous:
                labels={'verified':'已核验，远端内容匹配','pending_verification':'已接受，暂时不可读，待验证',
                        'upload_outcome_unknown':'上传结果未知，先读取原ID核验','failed':'上次核验未通过，原ID保留'}
                st.caption('远端状态：'+labels.get(previous['remote_status'],previous['remote_status']))
                st.caption('已有远端运行ID：'+previous['remote_run_id']+'；不重复POST上传。')
                agree=st.checkbox('允许读取现有远端记录核验（最多3次GET，不重新上传）',key='remote_read_consent_'+session.sid)
                if st.button('重新核验现有远端记录（仅GET）',disabled=not agree,key='remote_read_'+session.sid):
                    session.recheck_export(consent=True)
                    st.rerun()
            else:
                agree=st.checkbox("我已检查脱敏内容，允许将以上本轮记录发送至 LangSmith",key="remote_consent_"+session.sid)
                st.caption('最多1次POST与3次GET；仅202后的404延迟读取，仍不可读则保留待验证。')
                if st.button("导出本轮并验证远端",disabled=not agree or not state["enabled"] or not state['key_configured'],key="remote_export_"+session.sid):
                    session.export_last(consent=True)
                    st.rerun()
        if session.remote_receipts:
            st.json(session.remote_receipts[-1])
