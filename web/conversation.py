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
        st.warning('本轮查票结果与模拟数据库不一致，已暂停展示车次，请在 Trace 中核查原始证据。')
    else:
        st.write(record['reply'])


def _policy_evidence(hits):
    """Real document id / version / location / text, or an explicit gap."""
    with st.expander('政策证据 · 文档编号 / 版本 / 位置 / 原文', expanded=False):
        if not hits:
            st.caption('未记录：本轮 search_policy 没有返回可引用的政策片段，证据不足。')
            return
        for hit in hits:
            st.markdown('**' + escape(hit.get('doc_id') or '未记录') + '** · 版本 '
                        + escape(hit.get('version') or '未记录'))
            score = hit.get('score')
            st.caption('来源位置：' + str(hit.get('source') or '未记录')
                       + ' · 检索分数：' + (str(score) if score is not None else '未记录'))
            st.write(hit.get('content') or '原文未记录')


def show_business(results):
    successful=[r for r in results if r.get("ok") and isinstance(r.get("result"),dict)]
    if not successful:
        return
    last=successful[-1]
    if last["tool"]=="search_policy":
        hits=last['result'].get('hits') or []
        if hits:
            st.markdown(policy_cards(last["result"]),unsafe_allow_html=True)
        st.caption("来源：本地模拟政策文档；引用编号与位置来自 search_policy 的实际返回。")
        _policy_evidence(hits)
    elif last["tool"] in ("create_order","pay_order","cancel_order","query_order"):
        result=last["result"]
        for item in result.get("orders",[result] if result.get("order_id") else []):
            st.markdown(order_card(item),unsafe_allow_html=True)
    elif last["tool"]=="query_tickets":
        st.markdown(ticket_cards(last["result"]),unsafe_allow_html=True)
        if not last["result"].get("trains"):
            st.info("没有符合条件的模拟班次。")
        st.caption("以上为 query_tickets 本轮实际返回，最多展示 20 条；缺失字段保持“未提供”，不补造。")


def _followup_lifecycle(session, run_id, kind, **fields):
    """Append one follow-up lifecycle event to the run's existing event chain."""
    from target import followups as followup_store
    try:
        followup_store.emit_event(session.trace_dir/'run_events.jsonl', run_id, session.sid, kind, **fields)
    except Exception:
        pass


def execute(session, message, request_id, origin=None):
    placeholder=st.empty()
    rag_placeholder=st.empty()
    seen=[]
    def update(event):
        seen.append(event)
        placeholder.markdown(processing_event(event) if event.get('event_type','').startswith('followup_') else
                             '<div class="ta-live">'+run_view.phase_at(event,seen[:-1])+'</div>',
                             unsafe_allow_html=True)
        from web.policy_interaction import policy_view
        view=policy_view(session.sid,event.get('run_id'),events=seen)
        if view['status']!='not_searched':
            rag_placeholder.markdown(_policy_status_markup(view),unsafe_allow_html=True)
    placeholder.markdown(PROCESSING,unsafe_allow_html=True)
    try:
        consent=bool(session.live and st.session_state.get('user_compose_session')==session.sid
                     and st.session_state.get('user_allow_live'))
        origin=origin or {}
        session.send(message,request_id,event_callback=update,followup_authorized=consent,
                     followup_origin=origin if origin.get('run_id') else None)
    except Exception:
        from target.reply_consistency import failure_notice
        notice=failure_notice(session.error["category"]) if session.error else None
        detail=tool_failure_hint(session)
        st.error((detail or notice or "请求未完成；未自动重试。")+(" 错误类别："+session.error["category"] if session.error else "请核对模式与输入。"))
    finally:
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


def _policy_panel(view):
    """Only this turn's recorded retrieval; no document lookup or reply parsing."""
    hits=view.get('evidence') or []
    if not hits:
        st.markdown(_policy_status_markup(view),unsafe_allow_html=True)
        if view.get('reason'):st.caption(view['reason'])
        return
    label=('已检索知识库' if view.get('status')=='retrieved' else
           str(view.get('status_label') or '检索状态未记录')+' · 含本轮较早返回的证据')
    with st.expander(label+' · '+str(len(hits))+' 条证据',expanded=False):
        if view.get('status')!='retrieved':
            st.warning('本轮最近一次检索未确认成功；下面保留较早实际返回的文档，不能当作最近检索成功。')
            if view.get('reason'):st.caption(view['reason'])
        st.caption('检索命中不等于支持最终回答。引用内容与结论的对应关系尚未验证。')
        st.caption('本轮 run_id / Trace ID：'+str(view.get('run_id') or '未记录'))
        if view.get('read_incomplete'):st.warning('部分旁证无法读取或超出范围；缺失信息不作推断。')
        for hit in hits:
            st.write('**'+str(hit.get('doc_id') or '未记录')+' · '+str(hit.get('title') or '标题未记录')+'**')
            st.caption('版本：'+str(hit.get('version') or '未记录')+' · 模式：'+
                {'keyword':'Keyword','vector':'Vector','hybrid':'Hybrid'}.get(hit.get('mode'),'未记录')+
                ' · 排名：'+str(hit['rank'] if hit.get('rank') is not None else '未记录')+
                ' · 分数：'+str(hit['score'] if hit.get('score') is not None else '未记录'))
            st.write(hit.get('content') or '政策原文未记录')
            st.caption('原文位置：'+str(hit.get('source') or '未记录'))
            entered=hit.get('entered_context')
            st.caption('本轮回答上下文：'+('已记录进入模型请求' if entered is True else '已记录未进入' if entered is False else '未记录')+
                       ' · 支持最终结论：尚未验证')
            st.caption('关联事件：'+'、'.join(str(x) for x in hit.get('event_ids',[]) if x) if hit.get('event_ids') else '关联事件：未记录')
        with st.expander('本轮详细证据记录（本页查看）'):
            st.json(view,expanded=False)


def _queue_followup(sid, run_id, question):
    st.session_state['user_followup_request']={'sid':sid,'run_id':run_id,'question':question,'request_id':uuid.uuid4().hex}


def _followup_suggestions(session, record, view, offered=None):
    from target.followups import normal
    if view.get('status')=='failed':return
    saved=session.followups_for(record)
    if not saved:return  # Old history has no saved recommendations; no regeneration.
    asked={normal(h['user_msg']) for h in session.history}
    suggestions=[q for q in saved['suggestions'] if normal(q) not in asked]
    suggestions=[q for q in suggestions if offered is None or q not in offered]
    if not suggestions:return
    if offered is not None:offered.update(suggestions)
    pending=st.session_state.get('pending_operation') or {}
    ready=(not session.pending_action() and pending.get('sid')!=session.sid and
           (not session.live or (st.session_state.get('user_compose_session')==session.sid and
                                st.session_state.get('user_allow_live') and live_ready(session.live_provider))))
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
        st.caption('模型推荐 · 已保存，本页回放不调用模型' if saved['generation_source']=='model' else
                   '操作型推荐 · 依据本轮真实工具结果；点击仍走原有确认流程' if saved['generation_source']=='action_rule' else
                   '规则推荐 · 基于本轮执行证据，不增加模型请求')
        for n,question in enumerate(suggestions):
            st.button(question,key='policy_followup_'+session.sid+'_'+str(view.get('run_id'))+'_'+str(n),
                      on_click=_queue_followup,args=(session.sid,view.get('run_id'),question),
                      disabled=not ready,width='stretch')
        if session.live and not ready:st.caption('先在输入区确认真实请求费用，并完成待确认操作。点击追问将按普通消息计费。')
        with st.expander('追问生成记录',expanded=False):
            st.caption('生成来源：'+saved['generation_source']+' · 回退原因：'+str(saved.get('fallback_reason') or '无'))
            st.caption('run_id：'+saved['run_id']+' · 规则版本：'+saved['prompt_version'])
            st.json(saved,expanded=False)


def _consume_followup(session, busy):
    """Revalidate stale buttons and Live consent immediately before dispatch."""
    request=st.session_state.pop('user_followup_request',None)
    if not request:return None
    if request.get('sid')!=session.sid or busy:
        st.info('会话已切换或存在待确认操作，尚未发送这条追问。');return None
    if session.live and (st.session_state.get('user_compose_session')!=session.sid or
                         not st.session_state.get('user_allow_live') or not live_ready(session.live_provider)):
        st.warning('请先确认真实请求费用；这条追问尚未发送。');return None
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


def _run_rail(session, events):
    """Right rail: what the current run actually did."""
    with st.container(key='user_rail'):
        if not session.history:
            st.markdown('<div class="ta-rail-head"><b>本次运行</b><span>尚未开始</span></div>',unsafe_allow_html=True)
            st.markdown('<p class="ta-rail-empty">发送一句话后，这里会按真实事件显示查票、检索政策、等待确认和执行的阶段，'
                        '以及每次工具调用的状态与耗时。</p>',unsafe_allow_html=True)
            st.markdown('<p class="ta-rail-empty">运行状态只来自本轮记录；没有记录到的阶段显示“未发生”。</p>',
                        unsafe_allow_html=True)
            return
        st.markdown('<div class="ta-rail-head"><b>本次运行</b><span>来自本轮记录</span></div>',unsafe_allow_html=True)
        st.markdown(run_view.phase_strip(run_view.phase_states(events)),unsafe_allow_html=True)
        if not events:
            st.caption('本次运行没有可读的事件文件；阶段显示为未记录，不能据此推断执行结果。')
        st.markdown('<div class="ta-rail-sub">工具调用</div>'+run_view.call_list(run_view.call_rows(events)),
                    unsafe_allow_html=True)
        _followup_lifecycle_panel(session, events)
        record=session.history[-1]
        with st.expander('执行记录与 Trace 证据'):
            st.write(" → ".join(record["tool_sequence"]) or "本轮未调用工具")
            st.caption(f"结束原因 {record['finish_reason']} · {record['total_latency_ms']} ms；stop 仅表示循环结束。")
            for step in record.get('steps',[]):
                for call in step.get('calls',[]):
                    latency=call.get('latency_ms')
                    st.caption(f"{call.get('tool','未知工具')} · Trace 返回 {'成功' if call.get('ok') is True else '失败' if call.get('ok') is False else '未知'} · 耗时 {str(latency)+' ms' if isinstance(latency,(int,float)) else '未记录'}；是否实际执行以旁证为准。")
            matching=next((a for a in reversed(session.audits) if a.get('public_trace')==record),None)
            if matching:
                from web.run_evidence import policy_evidence
                evidence=policy_evidence(matching,session.results[-1])
                if evidence:
                    st.write('本轮政策引用与检索关联')
                    st.json(evidence,expanded=False)
                from web.trace_view import timeline_items
                for event in timeline_items(matching,record):
                    if event['kind'] in ('模型/规则输出','参数校验旁证','实际执行','未执行（含拦截）','执行状态未知','公共 Trace 工具调用'):
                        from target.diagnostics import sanitize
                        st.write(event['kind']+' · '+event['title'])
                        st.json(sanitize(event['data']), expanded=False)
            else:
                st.caption('没有可关联的审计旁证；不能推断工具执行状态。')


def _hero():
    st.markdown('<div class="ta-welcome"><div class="ta-eyebrow">YOUR JOURNEY, TRACEABLE</div>'
                '<h2>下一段旅程，<br>从一句话开始。</h2>'
                '<p>查询模拟余票、完成模拟购票、核对政策原文。每一步工具调用都从本轮真实记录读出，'
                '可追溯到 Trace，不补造缺失字段。</p></div>',unsafe_allow_html=True)


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
            f'<code title="{escape(run_id)}">{escape(short)}</code>'
            f'<span class="ta-status ta-status-{tone}">{escape(status)}</span>'
            '</div>'
            f'<div class="ta-summary-line">{escape(run_view.run_summary_line(summary))}</div>'
            '</div>')


def _run_summary_bar(session, audit, events, mode_badge):
    """Always-visible description of the run on screen, plus the two jumps."""
    summary = run_view.run_summary(session, audit, events, mode_badge)
    anchor = f"turn_{len(session.history) - 1}" if session.history else ""
    with st.container(key='run_summary'):
        info, actions = st.columns([3.1, 1.6], gap='small')
        with info:
            st.markdown(_summary_markup(summary), unsafe_allow_html=True)
        with actions:
            jump_run, jump_latest = st.columns(2, gap='small')
            if jump_run.button('回到本次运行', key='scroll_to_run', width='stretch',
                               disabled=not session.history,
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
                    _policy_panel(view)
                    if not unsafe_ticket_result(session,previous):
                        _followup_suggestions(session,previous,view,None if index==len(session.history)-1 else offered)
        if session.history and not session.error:
            if not unsafe_ticket_result(session,session.history[-1]):
                # Policy evidence now lives under its own answer, including history.
                show_business([r for r in session.results[-1] if r.get('tool')!='search_policy'])
            record=session.history[-1]
            if any(name in record['tool_sequence'] for name in ('monitor_seat','lock_seat','create_order','pay_order','cancel_order')):
                st.info('本轮操作发生在模拟票务沙箱；未购买真实车票，也没有真实扣款。')
            if any(not c["ok"] for s in record["steps"] for c in s["calls"]):
                st.warning("本轮存在失败的工具调用，请在工作台保存执行证据。")
        if not session.history and not session.pending_action() and not st.session_state.get('guided_demo'):
            st.markdown('<p class="ta-chat-empty">对话会显示在这里；也可以先点上面的快捷问题，或从左侧选择模型新建会话。</p>',
                        unsafe_allow_html=True)


def _confirm_cards(session, action, pending, pending_here):
    """Confirmation cards belong to the conversation column, above the composer."""
    if action:
        with st.container(border=True,key='action_confirm'):
            st.markdown("**请确认模型提出的模拟操作**")
            st.write("操作：" + TOOL_LABELS.get(action['tool'], action['tool']))
            st.json(action['args'], expanded=True)
            st.caption("仅操作当前模拟数据库；确认只适用于上面列出的这一次工具调用。")
            yes, no = st.columns(2)
            approved = yes.button("确认此模拟操作", type="primary", width="stretch")
            declined = no.button("取消此模拟操作", width="stretch")
            if approved or declined:
                try:
                    session.confirm_action(approved, uuid.uuid4().hex,
                        followup_authorized=bool(session.live and st.session_state.get('user_compose_session')==session.sid
                            and st.session_state.get('user_allow_live')))
                except Exception:
                    st.error("操作未完成，请查看执行记录和订单状态。")
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
                st.caption("尚无可核对的订单金额；具体结果以工具返回为准。")
            st.caption("可能改变当前隔离模拟库的库存或订单状态，不涉及真实购票或扣款。取消/退票费用按后端实际政策计算。后端原有授权、身份及幂等校验继续生效。")
            yes,no=st.columns(2)
            if yes.button("确认执行模拟操作",type="primary",width="stretch"):
                st.session_state.pop("pending_operation",None)
                execute(session,pending["message"],pending["request_id"])
                st.rerun()
            if no.button("放弃本次操作",width="stretch"):
                st.session_state.pop("pending_operation",None)
                st.rerun()


def _composer(session, live_name):
    """The composer lives in the conversation column so narrow stacking keeps it
    between the transcript and the run-detail panel."""
    with st.container(key='user_compose'):
        if session.live:
            allow_live=st.checkbox("确认发送真实 "+live_name+" 请求（会产生 API 费用）",key="user_allow_live")
        else:
            allow_live=False
        with st.form("user_compose",clear_on_submit=True):
            row=st.columns([9,1.4],gap='small')
            message=row[0].text_input("输入消息",key="user_message",
                placeholder="例如：查明天上海到杭州的高铁二等座",label_visibility="collapsed")
            send=row[1].form_submit_button("发送",key='user_send_'+st.session_state['user_submit_nonce'],
                type="primary",disabled=session.live and not live_ready(session.live_provider))
            st.caption("查票、问政策可直接发送；锁座、下单、支付、退票会先请你确认。所有票务、订单与支付均为模拟。")
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
    def new_session():
        return Conversation("user",engine=st.session_state["default_engine"],live=st.session_state["default_live"],
                            live_provider=st.session_state.get("default_provider","deepseek"),
                            live_model=st.session_state.get("default_live_model"),interactive=True,
                            full_tools=st.session_state['default_live'])
    signature=(st.session_state["default_engine"],st.session_state["default_live"],st.session_state.get("default_provider","deepseek"),st.session_state.get('default_live_model'),'manual-live-v1')
    if not sessions:
        sessions.append(new_session())
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
    live_name="Qwen3.8-Flash" if session.live_provider=="bailian" and session.live_model=="qwen3.8-flash" else session.live_model or "Qwen (兼容旧配置)" if session.live_provider=="bailian" else "DeepSeek"
    mode_badge=(live_name+" Live · 模拟票务" if session.live and session.full_tools
                else live_name+" Live · 只读" if session.live else "离线 Mock")
    header("出行助手","用一句话查模拟余票、订票、查政策；每一步工具调用状态都来自本轮真实事件。",mode_badge)
    if (session.engine,session.live,session.live_provider)!=(st.session_state['default_engine'],st.session_state['default_live'],st.session_state.get('default_provider','deepseek')):
        st.info('正在查看历史会话，当前使用 '+(live_name+' Live' if session.live else '离线 Mock')+'；左侧模型用于新建会话。')
    st.caption("真实模型负责理解与工具选择；所有票务数据为模拟。Qwen3.8-Flash已有V3.5真实闭环记录，DeepSeek有历史证据；新会话不等于已验证成功。" if session.live else "当前使用离线规则模型，不产生模型 API 费用。支持 8 个模拟工具。")

    action = session.pending_action()
    pending=st.session_state.get("pending_operation")
    pending_here=bool(pending and pending["sid"]==session.sid)
    busy=bool(action) or pending_here
    followup=_consume_followup(session,busy)
    audit, events, event_meta = run_view.latest_run(session) if session.audits else (None, [], {})

    welcome = not session.history and not busy
    _run_summary_bar(session, audit, events, mode_badge)

    if session.error:
        st.error((tool_failure_hint(session) or failure_hint(session.error['category']))+' 错误类别：'+session.error['category'])
        from web.policy_interaction import policy_view
        failed_policy=policy_view(session.sid,(audit or {}).get('trace_id'),events=events,audit=audit)
        if failed_policy['has_recorded_retrieval']:
            st.caption('最近未完成请求的知识库记录；不是上一条成功回答的证据。')
            _policy_panel(failed_policy)

    if st.session_state.get('user_compose_session')!=session.sid:
        st.session_state['user_allow_live']=False
        st.session_state['user_allow_embedding']=False
        st.session_state['user_rag_mode']=session.rag_mode or 'keyword'
        st.session_state['user_compose_session']=session.sid
        st.session_state['user_submit_nonce']=uuid.uuid4().hex

    def _chat_body():
        if welcome:
            _hero()
            _quick_prompts()
        if welcome or st.session_state.get('guided_demo'):
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
        _confirm_cards(session, action, pending, pending_here)
        return _composer(session, live_name)

    if session.history or action:
        main, rail = st.columns([1.95,1],gap='large')
        with main:
            message, send, allow_live = _column_body()
        with rail:
            # Collapsed by default: the summary bar already carries the live
            # status, and a stacked narrow layout must stay inside the viewport.
            with st.expander('运行详情与 Trace', expanded=False):
                _run_rail(session, events)
    else:
        message, send, allow_live = _column_body()

    if session.live:
        show_remote_export(session)

    if session.live:
        with st.expander('高级设置 · 政策检索与联网',expanded=False):
            session.rag_mode=st.selectbox('政策检索方式',['keyword','hybrid','vector'],key='user_rag_mode')
            session.allow_rag_network=st.checkbox('允许本轮RAG调用真实Embedding（可能产生费用；仅发送问题时执行）',key='user_allow_embedding')
            st.caption('本地累计请求次数不设上限；订单和支付均为模拟，单轮步数与超时保护仍然生效。')

    if session.live and not live_ready(session.live_provider):
        st.info(live_name+" 未配置完整或本次为离线验收。可查看历史证据；不会自动切换 Mock。")
    with st.expander('更多模拟工具 · 行李费用 / 高铁改签'):
        st.caption('以下两项直接调用既有模拟业务函数，不经过模型；结果只作用于当前隔离模拟库。')
        with st.expander('模拟行李费用计算（高铁政策 P06）'):
            st.caption('输入一名旅客携带品总重量，以及需要检查的一件物品的尺寸。只计算模拟超重费用。')
            with st.form('baggage_calculator'):
                person=st.selectbox('旅客类型',['成人','儿童'],key='baggage_person')
                weight=st.text_input('携带品总重量（千克）',key='baggage_weight')
                cols=st.columns(3)
                length=cols[0].text_input('长（厘米）',key='baggage_length')
                width=cols[1].text_input('宽（厘米）',key='baggage_width')
                height=cols[2].text_input('高（厘米）',key='baggage_height')
                calculate=st.form_submit_button('计算模拟行李费用')
            if calculate:
                try:
                    from target.baggage import calculate_baggage
                    result=calculate_baggage(person,weight,length,width,height)
                    st.write('免费额度：'+result['free_kg']+' 千克；超重：'+result['excess_kg']+' 千克。')
                    st.write('模拟超重费用：¥'+result['weight_fee_yuan']+'（来源：P06）')
                    st.write('该物品尺寸总和：'+result['item_sum_cm']+' 厘米；'+result['size_status'])
                    st.caption(result['note'])
                except ValueError as exc:
                    st.warning(str(exc))
        with st.expander('模拟高铁改签（P02 / P03）'):
            st.caption('仅操作当前会话的已支付模拟订单。差价只做记录，不进行支付或退款；改签后不支持退票。')
            with st.form('reschedule_preview'):
                order_id=st.text_input('模拟订单号',key='reschedule_order')
                new_train=st.text_input('目标车次',key='reschedule_train')
                new_date=st.text_input('目标日期（YYYY-MM-DD）',key='reschedule_date')
                new_seat=st.selectbox('目标席别',['二等座','一等座','商务座'],key='reschedule_seat')
                preview_clicked=st.form_submit_button('预览改签')
            if preview_clicked:
                st.session_state.pop('reschedule_pending',None)
                try:
                    from target.reschedule import preview
                    proposal=preview(session.root/'tickets.db',order_id.strip(),new_train.strip(),new_date.strip(),new_seat)
                    st.session_state['reschedule_pending']={'sid':session.sid,'proposal':proposal}
                except (ValueError,TypeError) as exc:
                    st.warning(str(exc))
            pending_reschedule=st.session_state.get('reschedule_pending')
            if pending_reschedule and pending_reschedule['sid']==session.sid:
                proposal=pending_reschedule['proposal']
                st.json(proposal)
                yes,no=st.columns(2)
                if yes.button('确认执行模拟改签',key='reschedule_confirm'):
                    st.session_state.pop('reschedule_pending',None)
                    try:
                        from target.reschedule import confirm
                        result=confirm(session.root/'tickets.db',proposal)
                        st.success('模拟改签完成；差额仅作记录。')
                        st.json(result)
                    except (ValueError,TypeError) as exc:
                        st.warning(str(exc))
                if no.button('取消改签',key='reschedule_cancel'):
                    st.session_state.pop('reschedule_pending',None)
                    st.info('已取消，本次未改签。')
    if send and action:
        st.warning("请先确认或取消待处理的模拟操作。")
    elif send and message.strip():
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
