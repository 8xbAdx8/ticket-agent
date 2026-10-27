"""Explicit experiments only. Rerendering never calls the Agent."""
import re
import os
import uuid
from datetime import timedelta
import streamlit as st
import config
from web.design import header, empty
from web.runtime import Conversation, live_ready, LIVE_AVAILABLE, scoped, tool_failure_hint
from web.evidence import MUTATIONS, cases
from web.conversation import execute, show_business, show_remote_export
from web.trace_view import show_record

DESCRIPTIONS = dict(zip(MUTATIONS, ("M1 · 日期偏移一天", "M2 · 跳过锁座下单", "M3 · 重复派发工具", "M4 · 有限监控重入", "M5 · 政策误路由", "M6 · 删除政策引用", "M7 · 注入假车次 G9999", "M8 · 影子库并发重复订单")))


def live_unavailable_reason(provider):
    if os.getenv('TICKET_WEB_OFFLINE_ONLY')=='1':
        return '当前为离线模式，真实模型请求已关闭；请使用在线启动入口。'
    key='DASHSCOPE_API_KEY' if provider=='bailian' else 'DEEPSEEK_API_KEY'
    if not os.getenv(key,'').strip():return key+' 未配置；请配置后重新启动，未发送模型请求。'
    if provider=='bailian' and not os.getenv('DASHSCOPE_BASE_URL','').strip():
        return 'DASHSCOPE_BASE_URL 未配置；请设置与账号地域匹配的地址。'
    return '模型配置不完整；请核对模型名称和服务地址。'


def lab_page():
    header("智能体测试实验室", "显式选择场景与变异，在独立模拟环境中观察执行事实。", "A 实验 · 非 B 正式成绩")
    config_col, run_col = st.columns([1, 2.35], gap="large")
    with config_col, st.container(border=True):
        st.markdown("### 实验配置")
        # Retain stable widget values for saved sessions; display the actual
        # full-sandbox capability instead of the former read-only label.
        choices = ["Legacy Mock", "LangChain Mock", "DeepSeek Live · 只读", "Qwen3.8-Flash Live · 只读"]
        selected = st.selectbox("执行模式", choices, key="lab_engine",
                                format_func=lambda name: name.replace('· 只读', '· 模拟票务'))
        live = "Live" in selected
        live_provider="bailian" if selected.startswith("Qwen") else "deepseek"
        case_id=st.text_input("测试用例 ID",value="interactive-lab",key="lab_case_id")
        engine = "legacy" if selected.startswith("Legacy") else "langchain"
        st.caption("工具集：8 个本地模拟工具；订单与支付均为模拟")
        st.markdown("**八种缺陷注入**")
        enabled = {}
        for name in MUTATIONS:
            disabled = False
            value = st.checkbox(name, key="lab_mutation_"+name, disabled=disabled, help=DESCRIPTIONS[name])
            st.caption(DESCRIPTIONS[name] + (" · 当前工具集不适用" if disabled else ""))
            if value and not disabled:
                enabled[name] = 1 if name == "date_offset" else True
        def reset_mutations():
            for name in MUTATIONS:
                st.session_state["lab_mutation_"+name] = False
        st.button("恢复正常模式", on_click=reset_mutations, width="stretch")
        max_steps = st.number_input("最大模型步骤", min_value=1, max_value=8, value=4 if live else 8, step=1, disabled=live,
            key='lab_steps_live' if live else 'lab_steps_mock',
            help="Live 单轮最多 4 次模型调用；离线实验可调整")
        scenario = st.selectbox("并发场景", ["same_lock_two", "same_lock_many", "same_request_retry", "different_locks", "expired_lock", "worker_failure", "query_after_retry"])
    signature = (engine, live, live_provider, case_id, tuple(sorted(enabled.items())), max_steps)
    if st.session_state.get("lab_signature") != signature:
        st.session_state["lab_signature"] = signature
        st.session_state['lab_allow_live']=False
        st.session_state['lab_allow_embedding']=False
        st.session_state['lab_submit_nonce']=uuid.uuid4().hex
        st.session_state['lab_concurrency_nonce']=uuid.uuid4().hex
        st.session_state.pop('lab_concurrency_notice',None)
        session = Conversation("lab", engine=engine, live=live, live_provider=live_provider,
                               live_model="qwen3.8-flash" if live_provider=="bailian" else None,case_id=case_id,mutations=enabled,
                               full_tools=live)
        st.session_state.setdefault("lab_archives", []).append(session)
        st.session_state["lab_session"] = session
    session = st.session_state["lab_session"]
    with run_col:
        st.caption("独立 SQLite / Trace · " + session.sid + " · 配置变化时新建实验；用户模式不受影响")
        preset = st.selectbox("测试场景", ["查票", "政策咨询", "无票监控", "模拟购票", "自定义", "B 原用例输入（A 实验复用）"])
        messages = {"查票": "查明天上海到杭州的高铁二等座", "政策咨询": "锁座后多久必须完成支付？", "无票监控": "抢明天北京到上海的票", "模拟购票": "订明天上海到杭州的高铁"}
        if preset == "B 原用例输入（A 实验复用）":
            originals = [c for c in cases() if engine in c.get("engines", ["legacy", "langchain"]) and c.get("turns") and all(isinstance(m, str) and m.strip() for m in c["turns"])]
            i = st.selectbox("原始用例", range(len(originals)), format_func=lambda i: originals[i]["id"] + " · " + originals[i]["name"])
            with st.expander("原始用例与断言（只读）"):
                st.json(originals[i])
            step = st.selectbox("本次发送哪一轮", range(len(originals[i]["turns"])), format_func=lambda i: "第 " + str(i+1) + " 轮")
            message = re.sub(r"<rel_date:([+-]?\d+)>", lambda m: (config.today()+timedelta(days=int(m[1]))).isoformat(), originals[i]["turns"][step])
            st.caption("仅复用输入逐轮执行；不执行 B 断言，不计入 B 成绩。原 setup 故障需由 B 正式执行器复现。")
        else:
            message = messages.get(preset, "")
        with st.form("lab_submit"):
            text = st.text_input("输入消息", value=message, key="lab_message_"+preset)
            live_confirm = st.checkbox("确认真实模型请求与费用", key="lab_allow_live") if live else False
            if live:
                session.rag_mode=st.selectbox('政策检索方式',['keyword','hybrid','vector'],key='lab_rag_mode')
                session.allow_rag_network=st.checkbox('允许本轮RAG调用真实Embedding（可能产生费用）',key='lab_allow_embedding')
                st.caption('Live累计请求次数不设上限；与出行助手使用相同策略，实验数据继续隔离。')
            send = st.form_submit_button("执行测试", key="lab_submit_"+st.session_state['lab_submit_nonce'], type="primary", disabled=bool(enabled.get("concurrent_duplicate_order")) or live and not live_ready(live_provider))
        if send and text.strip():
            if live and not live_confirm:
                st.warning("尚未确认在线请求，未调用模型。")
            else:
                # Queued clicks from this rendered widget retain the old key.
                # A deliberately new click after rerender gets the next nonce.
                request_id=st.session_state['lab_submit_nonce']
                st.session_state['lab_submit_nonce']=uuid.uuid4().hex
                with scoped({"MAX_STEPS": int(max_steps)} if not live else {}):
                    execute(session, text, request_id)
                st.rerun()
        if enabled.get("concurrent_duplicate_order"):
            st.info("M8 对话执行不适用；请使用独立后端对照。")
        if live and not live_ready(live_provider):
            st.warning(live_unavailable_reason(live_provider))
        if st.button("运行并发订单对照（离线）", key="lab_concurrency_"+st.session_state['lab_concurrency_nonce'], width="stretch"):
            st.session_state['lab_concurrency_nonce']=uuid.uuid4().hex
            try:
                with st.spinner("正在实际执行隔离的并发场景…"):
                    records=session.concurrency(scenario)
            except Exception as exc:
                notice=('error',"并发实验未完成（"+type(exc).__name__+"）；已保存的记录可查看，未自动重试。")
            else:
                if len(records)==1:
                    notice=('info',"正常库结果已保存；此场景不适用于 M8 缺陷注入，未运行影子库。0 次模型 API 请求。")
                else:
                    notice=('success',"实际对照已保存；0 次模型 API 请求。")
            st.session_state['lab_concurrency_notice']=notice
            st.rerun()
        notice=st.session_state.pop('lab_concurrency_notice',None)
        if notice:getattr(st,notice[0])(notice[1])
        if session.error:
            dimensions=(session.audits[-1].get('judgement',{}).get('dimensions',{}) if session.audits else {})
            guarded_fault=(any(enabled.get(name) for name in ('skip_lock','infinite_loop'))
                           and dimensions.get('injection_applied') is True
                           and dimensions.get('platform_defect_detected') is True
                           and session.error['category'] in ('tool_execution_failed','tool_call_limit_exceeded'))
            if guarded_fault:
                st.info('变异已注入，实验被业务或调用上限保护终止；请查看下方 Trace。结果不是购票成功。错误类别：'+session.error['category'])
            else:
                st.error(tool_failure_hint(session) or "上次执行失败：" + session.error["category"] + "；未自动重试，也没有把旧结果作为新结果。")
        if live:
            show_remote_export(session)
        if session.history and not session.error:
            record = session.history[-1]
            with st.chat_message("user", avatar=":material/person:"):
                st.write(record["user_msg"])
            with st.chat_message("assistant", avatar=":material/smart_toy:"):
                st.write(record["reply"])
            show_business(session.results[-1])
            if any(name in record['tool_sequence'] for name in ('monitor_seat','lock_seat','create_order','pay_order','cancel_order')):
                st.info('本轮工具操作使用独立模拟数据库，不涉及真实购票或扣款。')
        if session.audits:
            i = st.selectbox("本实验执行记录", range(len(session.audits)), index=len(session.audits)-1,
                format_func=lambda i: session.audits[i].get("trace_id", "记录")[:12] + " · " + str(session.audits[i].get("scenario", "Agent 对话")))
            show_record(session.audits[i], key="lab_trace")
        else:
            empty("待执行", "点击执行测试才调用 Agent。配置、浏览、主题切换与刷新不会触发请求；没有预设工具执行动画。")
