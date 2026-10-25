"""Explicit experiments only. Rerendering never calls the Agent."""
import re
import uuid
from datetime import timedelta
import streamlit as st
import config
from web.design import header, empty
from web.runtime import Conversation, live_ready, LIVE_AVAILABLE, scoped
from web.evidence import MUTATIONS, cases
from web.conversation import execute, show_business, show_remote_export
from web.trace_view import show_record

DESCRIPTIONS = dict(zip(MUTATIONS, ("M1 · 日期偏移一天", "M2 · 跳过锁座下单", "M3 · 重复派发工具", "M4 · 有限监控重入", "M5 · 政策误路由", "M6 · 删除政策引用", "M7 · 注入假车次 G9999", "M8 · 影子库并发重复订单")))


def lab_page():
    header("智能体测试实验室", "显式选择场景与变异，在独立模拟环境中观察执行事实。", "A 实验 · 非 B 正式成绩")
    config_col, run_col = st.columns([1, 2.35], gap="large")
    with config_col, st.container(border=True):
        st.markdown("### 实验配置")
        choices = ["Legacy Mock", "LangChain Mock", "DeepSeek Live · 只读", "Bailian Live · 只读"]
        selected = st.selectbox("执行模式", choices, key="lab_engine")
        live = "Live" in selected
        live_provider="bailian" if selected.startswith("Bailian") else "deepseek"
        case_id=st.text_input("测试用例 ID",value="interactive-lab",key="lab_case_id")
        engine = "legacy" if selected.startswith("Legacy") else "langchain"
        st.caption("工具集：query_tickets / search_policy" if live else "工具集：8 个本地模拟工具")
        st.markdown("**八种缺陷注入**")
        enabled = {}
        for name in MUTATIONS:
            disabled = live and name in ("skip_lock", "infinite_loop")
            value = st.checkbox(name, key="lab_mutation_"+name, disabled=disabled, help=DESCRIPTIONS[name])
            st.caption(DESCRIPTIONS[name] + (" · 当前工具集不适用" if disabled else ""))
            if value and not disabled:
                enabled[name] = 1 if name == "date_offset" else True
        def reset_mutations():
            for name in MUTATIONS:
                st.session_state["lab_mutation_"+name] = False
        st.button("恢复正常模式", on_click=reset_mutations, width="stretch")
        max_steps = st.number_input("最大模型步骤", min_value=1, max_value=8, value=8, step=1, disabled=live,
            help="仅离线实验；Live 沿用现有单轮安全限制")
        scenario = st.selectbox("并发场景", ["same_lock_two", "same_lock_many", "same_request_retry", "different_locks", "expired_lock", "worker_failure", "query_after_retry"])
    signature = (engine, live, live_provider, case_id, tuple(sorted(enabled.items())), max_steps)
    if st.session_state.get("lab_signature") != signature:
        st.session_state["lab_signature"] = signature
        session = Conversation("lab", engine=engine, live=live, live_provider=live_provider,case_id=case_id,initial_budget=True,mutations=enabled)
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
            send = st.form_submit_button("执行测试", type="primary", disabled=bool(enabled.get("concurrent_duplicate_order")) or live and not live_ready(live_provider))
        if send and text.strip():
            if live and not live_confirm:
                st.warning("尚未确认在线请求，未调用模型。")
            else:
                with scoped({"MAX_STEPS": int(max_steps)} if not live else {}):
                    execute(session, text, uuid.uuid4().hex)
                st.rerun()
        if enabled.get("concurrent_duplicate_order"):
            st.info("M8 对话执行不适用；请使用独立后端对照。")
        if st.button("运行并发订单对照（离线）", width="stretch"):
            with st.spinner("正在实际执行正常库与临时影子库对照…"):
                session.concurrency(scenario)
            st.success("实际对照已保存；0 次模型 API 请求。")
        if session.error:
            st.error("上次执行失败：" + session.error["category"] + "；未自动重试，也没有把旧结果作为新结果。")
        if live:
            show_remote_export(session)
        if session.history and not session.error:
            record = session.history[-1]
            with st.chat_message("user", avatar=":material/person:"):
                st.write(record["user_msg"])
            with st.chat_message("assistant", avatar=":material/smart_toy:"):
                st.write(record["reply"])
            show_business(session.results[-1])
        if session.audits:
            i = st.selectbox("本实验执行记录", range(len(session.audits)), index=len(session.audits)-1,
                format_func=lambda i: session.audits[i].get("trace_id", "记录")[:12] + " · " + str(session.audits[i].get("scenario", "Agent 对话")))
            show_record(session.audits[i], key="lab_trace")
        else:
            empty("待执行", "点击执行测试才调用 Agent。配置、浏览、主题切换与刷新不会触发请求；没有预设工具执行动画。")
