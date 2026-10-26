"""Ordinary user mode; uses the same Conversation service as the lab."""
import uuid
import streamlit as st
from web.design import header, empty, escape, PROCESSING
from web.runtime import Conversation, operation_kind, live_ready, failure_hint
from web.presentation import ticket_cards, order_card, policy_cards


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
        st.error((notice or "请求未完成；未自动重试。")+(" 错误类别："+session.error["category"] if session.error else "请核对模式与输入。"))
    finally:
        processing.empty()


def user_page():
    sessions=st.session_state.setdefault("user_sessions",[])
    def new_session():
        return Conversation("user",engine=st.session_state["default_engine"],live=st.session_state["default_live"],
                            live_provider=st.session_state.get("default_provider","deepseek"),
                            live_model=st.session_state.get("default_live_model"),interactive=True)
    signature=(st.session_state["default_engine"],st.session_state["default_live"],st.session_state.get("default_provider","deepseek"),'manual-live-v1')
    if not sessions:
        sessions.append(new_session())
        st.session_state["user_provider_signature"]=signature
    elif st.session_state.get("user_provider_signature")!=signature:
        sessions.append(new_session())
        st.session_state["user_session_index"]=len(sessions)-1
        st.session_state["user_provider_signature"]=signature
    with st.sidebar:
        if st.button("新建会话",width="stretch"):
            sessions.append(new_session())
            st.session_state["user_session_index"]=len(sessions)-1
        index=st.selectbox("历史会话",range(len(sessions)),format_func=lambda i:(sessions[i].history[0]["user_msg"][:18] if sessions[i].history else "新对话")+f" · {i+1}",key="user_session_index")
    session=sessions[index]
    live_name="Qwen3.8-Flash" if session.live_provider=="bailian" and session.live_model=="qwen3.8-flash" else session.live_model or "Qwen (兼容旧配置)" if session.live_provider=="bailian" else "DeepSeek"
    header("出行助手","查询模拟余票，了解票务政策。每次回答都以工具结果为依据。",live_name+" Live · 只读" if session.live else "离线 Mock")
    st.caption("真实模型负责理解与工具选择；所有票务数据为模拟。Qwen3.8-Flash已有V3.5真实闭环记录，DeepSeek有历史证据；新会话不等于已验证成功。" if session.live else "当前使用离线规则模型，不产生模型 API 费用。支持 8 个模拟工具。")
    if not session.history:
        st.markdown('<div class="ta-welcome"><h2>下一段旅程，<br>从一句话开始。</h2><p>告诉我出发地、目的地和日期，或直接咨询退改与支付政策。</p></div>',unsafe_allow_html=True)
        a,b=st.columns(2)
        if a.button("查明天上海到杭州的高铁",width="stretch"):
            st.session_state["user_message"]="查明天上海到杭州的高铁二等座"
        if b.button("锁座后多久必须完成支付？",width="stretch"):
            st.session_state["user_message"]="锁座后多久必须完成支付？"
    if session.error:
        st.error(failure_hint(session.error['category'])+' 错误类别：'+session.error['category'])
    for previous in session.history:
        with st.chat_message("user",avatar=":material/person:"):
            st.write(previous["user_msg"])
        with st.chat_message("assistant",avatar=":material/smart_toy:"):
            st.write(previous["reply"])
    if session.history and not session.error:
        show_business(session.results[-1])
        record=session.history[-1]
        with st.expander("本轮执行摘要"):
            st.write(" → ".join(record["tool_sequence"]) or "本轮未调用工具")
            st.caption(f"结束原因 {record['finish_reason']} · {record['total_latency_ms']} ms；stop 仅表示循环结束。")
        if any(not c["ok"] for s in record["steps"] for c in s["calls"]):
            st.warning("本轮存在失败的工具调用，请在工作台保存执行证据。")
    if session.live:
        show_remote_export(session)
    with st.form("user_compose"):
        message=st.text_input("输入消息",key="user_message",placeholder="例如：查明天上海到杭州的高铁二等座")
        allow_live=st.checkbox("确认发送真实 "+live_name+" 请求（会产生 API 费用）",key="user_allow_live") if session.live else False
        send=st.form_submit_button("发送",type="primary",disabled=session.live and (not live_ready(session.live_provider) or (session.initial_budget and not session.interactive)))
    if session.live and session.initial_budget and not session.interactive:
        st.info('该历史验收会话保留供回放。点击“新建会话”进入日常在线模式。')
    if session.live and not live_ready(session.live_provider):
        st.info(live_name+" 未配置完整或本次为离线验收。可查看历史证据；不会自动切换 Mock。")
    if send and message.strip():
        if session.live and not allow_live:
            st.warning("请先确认真实请求费用；尚未调用模型。")
        elif session.live and operation_kind(message):
            st.info("当前 Live 仅支持模拟查票和政策咨询，其余六个工具未开放。未发送请求。")
        elif operation_kind(message):
            st.session_state["pending_operation"]={"sid":session.sid,"message":message,"request_id":uuid.uuid4().hex}
            st.rerun()
        else:
            execute(session,message,uuid.uuid4().hex)
            st.rerun()
    pending=st.session_state.get("pending_operation")
    if pending and pending["sid"]==session.sid:
        with st.container(border=True):
            st.markdown("**确认模拟操作**")
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
        st.caption('状态：'+('已启用脱敏导出，等待本轮导出核验' if state['enabled'] else '脱敏导出未开启')+'；打开本区域不会上传。')
        st.write(UPLOAD_SCOPE)
        run=session.agent.langchain_engine.last_live_run if session.agent and session.agent.langchain_engine else None
        if run:
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
                if st.button("导出本轮并验证远端",disabled=not agree or not state["enabled"],key="remote_export_"+session.sid):
                    session.export_last(consent=True)
                    st.rerun()
        if session.remote_receipts:
            st.json(session.remote_receipts[-1])
