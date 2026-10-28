"""Ordinary user mode; uses the same Conversation service as the lab."""
import uuid
import streamlit as st
from web.design import header, empty, escape, PROCESSING
from web.runtime import Conversation, operation_kind, live_ready, failure_hint, tool_failure_hint
from web.presentation import ticket_cards, order_card, policy_cards



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

def show_business(results):
    successful=[r for r in results if r.get("ok") and isinstance(r.get("result"),dict)]
    if not successful:
        return
    last=successful[-1]
    if last["tool"]=="search_policy":
        st.markdown(policy_cards(last["result"]),unsafe_allow_html=True)
        st.caption("来源：本地模拟政策文档；引用编号来自 search_policy 实际结果。")
    elif last["tool"] in ("create_order","pay_order","cancel_order","query_order"):
        result=last["result"]
        for item in result.get("orders",[result] if result.get("order_id") else []):
            st.markdown(order_card(item),unsafe_allow_html=True)
    elif last["tool"]=="query_tickets":
        st.markdown(ticket_cards(last["result"]),unsafe_allow_html=True)
        if not last["result"].get("trains"):
            st.info("没有符合条件的模拟班次。")
        st.caption("卡片来自本轮工具结果，最多展示 20 条；不会为填补缺失字段再次查询。")


def execute(session, message, request_id):
    processing=st.empty()
    processing.markdown(PROCESSING,unsafe_allow_html=True)
    try:
        session.send(message,request_id)
    except Exception:
        from target.reply_consistency import failure_notice
        notice=failure_notice(session.error["category"]) if session.error else None
        detail=tool_failure_hint(session)
        st.error((detail or notice or "请求未完成；未自动重试。")+(" 错误类别："+session.error["category"] if session.error else "请核对模式与输入。"))
    finally:
        processing.empty()


def user_page():
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
    header("出行助手","查询模拟余票，了解票务政策。每次回答都以工具结果为依据。",live_name+" Live · 模拟票务" if session.live and session.full_tools else live_name+" Live · 只读" if session.live else "离线 Mock")
    if (session.engine,session.live,session.live_provider)!=(st.session_state['default_engine'],st.session_state['default_live'],st.session_state.get('default_provider','deepseek')):
        st.info('正在查看历史会话，当前使用 '+(live_name+' Live' if session.live else '离线 Mock')+'；左侧模型用于新建会话。')
    st.caption("真实模型负责理解与工具选择；所有票务数据为模拟。Qwen3.8-Flash已有V3.5真实闭环记录，DeepSeek有历史证据；新会话不等于已验证成功。" if session.live else "当前使用离线规则模型，不产生模型 API 费用。支持 8 个模拟工具。")
    if not session.history:
        st.markdown('<div class="ta-welcome"><h2>下一段旅程，<br>从一句话开始。</h2><p>告诉我出发地、目的地和日期，或直接咨询退改与支付政策。</p></div>',unsafe_allow_html=True)
        a,b=st.columns(2)
        if a.button("查明天上海到杭州的高铁",width="stretch"):
            st.session_state["user_message"]="查明天上海到杭州的高铁二等座"
        if b.button("锁座后多久必须完成支付？",width="stretch"):
            st.session_state["user_message"]="锁座后多久必须完成支付？"
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
    if session.error:
        st.error((tool_failure_hint(session) or failure_hint(session.error['category']))+' 错误类别：'+session.error['category'])
    for previous in session.history:
        with st.chat_message("user",avatar=":material/person:"):
            st.write(previous["user_msg"])
        with st.chat_message("assistant",avatar=":material/smart_toy:"):
            show_guarded_reply(session,previous)
    if session.history and not session.error:
        if not unsafe_ticket_result(session,session.history[-1]):
            show_business(session.results[-1])
        record=session.history[-1]
        if any(name in record['tool_sequence'] for name in ('monitor_seat','lock_seat','create_order','pay_order','cancel_order')):
            st.info('本轮操作发生在模拟票务沙箱；未购买真实车票，也没有真实扣款。')
        with st.expander("本轮执行摘要"):
            st.write(" → ".join(record["tool_sequence"]) or "本轮未调用工具")
            st.caption(f"结束原因 {record['finish_reason']} · {record['total_latency_ms']} ms；stop 仅表示循环结束。")
        if any(not c["ok"] for s in record["steps"] for c in s["calls"]):
            st.warning("本轮存在失败的工具调用，请在工作台保存执行证据。")
    if session.live:
        show_remote_export(session)
    if st.session_state.get('user_compose_session')!=session.sid:
        st.session_state['user_allow_live']=False
        st.session_state['user_allow_embedding']=False
        st.session_state['user_rag_mode']=session.rag_mode or 'keyword'
        st.session_state['user_compose_session']=session.sid
        st.session_state['user_submit_nonce']=uuid.uuid4().hex
    with st.form("user_compose"):
        message=st.text_input("输入消息",key="user_message",placeholder="例如：查明天上海到杭州的高铁二等座")
        allow_live=st.checkbox("确认发送真实 "+live_name+" 请求（会产生 API 费用）",key="user_allow_live") if session.live else False
        if session.live:
            session.rag_mode=st.selectbox('政策检索方式',['keyword','hybrid','vector'],key='user_rag_mode')
            session.allow_rag_network=st.checkbox('允许本轮RAG调用真实Embedding（可能产生费用；仅发送问题时执行）',key='user_allow_embedding')
            st.caption('本地累计请求次数不设上限；订单和支付均为模拟，单轮步数与超时保护仍然生效。')
        send=st.form_submit_button("发送",key='user_send_'+st.session_state['user_submit_nonce'],type="primary",disabled=session.live and not live_ready(session.live_provider))
    if session.live and not live_ready(session.live_provider):
        st.info(live_name+" 未配置完整或本次为离线验收。可查看历史证据；不会自动切换 Mock。")
    action = session.pending_action()
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
            st.rerun()
    if action:
        from web.presentation import TOOL_LABELS
        with st.container(border=True):
            st.markdown("**请确认模型提出的模拟操作**")
            st.write("操作：" + TOOL_LABELS.get(action['tool'], action['tool']))
            st.json(action['args'], expanded=True)
            st.caption("仅操作当前模拟数据库；确认只适用于上面列出的这一次工具调用。")
            yes, no = st.columns(2)
            approved = yes.button("确认此模拟操作", type="primary", width="stretch")
            declined = no.button("取消此模拟操作", width="stretch")
            if approved or declined:
                try:
                    session.confirm_action(approved, uuid.uuid4().hex)
                except Exception:
                    st.error("操作未完成，请查看执行记录和订单状态。")
                st.rerun()
    pending=st.session_state.get("pending_operation")
    if pending and pending["sid"]==session.sid:
        with st.container(border=True):
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
