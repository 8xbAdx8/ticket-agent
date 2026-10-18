# -*- coding: utf-8 -*-
"""实际 Agent 前端：所有卡片来自本轮工具结果，公共 Trace 保持原样。"""
import json
import os
import sys
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import pandas as pd
import streamlit as st
import config
from target.agent import Agent
from target import providers
from target.deepseek_runtime import VALIDATION_NOTICE
from target.fault_injection import from_env, STAGES, MUTATION_NAMES
from web.audit_view import show_audit, show_audit_replay, show_linked_audit
from web.presentation import (TOOL_LABELS, escape, turn_cursor, collect_results,
                              ticket_cards, order_card, policy_cards, code_excerpt)

PROCESSING_STATUS_HTML = '''<div class="ticket-agent-processing" role="status" aria-live="polite">
<span class="ticket-agent-processing-icon" aria-hidden="true"></span><span>正在处理请求...</span></div>'''


def show_business(results):
    """展示工具事实，不从模型自然语言推断价格、余票或订单状态。"""
    successful = [r for r in results if r["ok"] and isinstance(r["result"], dict)]
    orders = [r for r in successful if r["tool"] in ("create_order", "pay_order", "cancel_order", "query_order")]
    policies = [r for r in successful if r["tool"] == "search_policy"]
    queries = [r for r in successful if r["tool"] == "query_tickets"]
    if orders:
        result = orders[-1]["result"]
        items = result.get("orders", [result] if "order_id" in result else [])
        if not items:
            st.info("工具查询结果：暂无订单。")
        for item in items[:10]:
            st.markdown(order_card(item), unsafe_allow_html=True)
        st.caption("模拟订单状态来自工具返回；不会自动支付。超过 10 条请查看工具原始结果。")
    elif policies:
        result = policies[-1]["result"]
        st.markdown(policy_cards(result), unsafe_allow_html=True)
        if not result.get("hits"):
            st.info("本轮未检索到匹配政策。")
    elif queries:
        result = queries[-1]["result"]
        st.markdown(ticket_cards(result), unsafe_allow_html=True)
        if not result.get("trains"):
            st.info("工具查询结果：没有符合条件的班次。")
        st.caption("价格与余票来自本轮模拟查询结果；下单后库存可能变化。")


def show_trace(record, results=None):
    st.subheader("最新一条 trace")
    if record is None:
        st.info("发送一条消息后，这里显示实际工具调用、参数与耗时。")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("调用次数", len(record["tool_sequence"]))
    c2.metric("总耗时(ms)", record["total_latency_ms"])
    c3.metric("结束原因", record["finish_reason"])
    if record["provider"] == "deepseek_live":
        st.caption(f"API 报告 Token：输入 {record['tokens']['prompt']} / 输出 {record['tokens']['completion']}")
    rows = [{"step": s["step"], "tool": c["tool"], "args": c["args"], "ok": c["ok"],
             "latency_ms": c["latency_ms"], "result": c["result_preview"]}
            for s in record["steps"] for c in s["calls"]]
    st.markdown("**执行步骤摘要 · 实际工具调用**")
    if not rows:
        st.caption("本轮未调用工具。")
    for index, row in enumerate(rows, 1):
        st.markdown(f'''<div class="tool-row"><span class="tool-number">{index}</span>
          <div class="tool-info"><b>{escape(row['tool'])}</b><div class="muted">{escape(TOOL_LABELS.get(row['tool'], row['tool']))} · {'执行成功' if row['ok'] else '执行失败'}</div></div>
          <span class="tool-time">{escape(row['latency_ms'])} ms</span></div>''', unsafe_allow_html=True)
    if rows:
        selected = st.selectbox("工具参数与结果", range(len(rows)),
                                format_func=lambda i: f"{i+1}. {rows[i]['tool']}",
                                key=f"active_call_{record['session_id']}_{len(st.session_state.history)}")
        st.code(json.dumps(rows[selected]["args"], ensure_ascii=False, indent=2), language="json")
        with st.expander("工具原始结果"):
            if results and len(results) == len(rows):
                st.json(results[selected]["result"])
            else:
                st.code(rows[selected]["result"])
                st.caption("历史契约只保存 result_preview；截断内容不会补造。")
        with st.expander("工具调用表"):
            st.dataframe(pd.DataFrame([dict(row, args=json.dumps(row["args"], ensure_ascii=False)) for row in rows]),
                         width="stretch", hide_index=True)
    with st.expander("完整 JSON"):
        st.code(json.dumps(record, ensure_ascii=False, indent=2), language="json")
    st.caption("stop 表示循环结束；任务是否完成仍需检查回复与工具结果。耗时沿用 Agent 统计口径。")
    st.download_button("下载本轮 Trace", json.dumps(record, ensure_ascii=False, indent=2),
                       file_name="ticket-agent-trace.json", mime="application/json")


def show_replay():
    st.subheader("离线回放（读取 traces/traces.jsonl，无需任何模型 key）")
    trace_file = config.TRACE_DIR / "traces.jsonl"
    if not trace_file.exists():
        st.info("暂无记录。")
        return
    records, bad = [], 0
    for line in trace_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict) or not all(k in record for k in ("session_id", "user_msg", "tool_sequence", "finish_reason")):
                raise ValueError()
            records.append(record)
        except (ValueError, TypeError):
            bad += 1
    if bad:
        st.warning(f"跳过 {bad} 行不完整记录；原文件保留，请另行检查。")
    st.write(f"共 {len(records)} 条记录，显示最近 10 条：")
    st.dataframe(pd.DataFrame([{"session": x["session_id"], "input": x["user_msg"],
                                "tools": " → ".join(x["tool_sequence"]) or "-", "finish": x["finish_reason"]}
                               for x in records[-10:]]), width="stretch", hide_index=True)
    if records:
        selected = st.selectbox("选择回放记录", range(len(records)), index=len(records)-1,
                                format_func=lambda i: f"{i+1}: {records[i]['user_msg'][:40]}")
        st.caption("原始记录回放，不执行新的业务操作，也不恢复旧会话记忆。")
        st.json(records[selected])
        show_linked_audit(records[selected],config.TRACE_DIR)


st.set_page_config(page_title="Ticket Agent · 出行工作空间", page_icon="🎫", layout="wide")
st.markdown("<style>" + (BASE / "web/theme.css").read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)
engine_label = ("LangChain Mock" if config.PROVIDER == "mock" else "LangChain Live") if config.ENGINE == "langchain" else (
    "原生 Python Mock" if config.PROVIDER == "mock" else "原生 Python Live")
if config.PROVIDER == "deepseek":
    engine_label = "DeepSeek Live · 全工具模拟沙箱" if os.getenv("DEEPSEEK_LIVE_TEST_PROFILE") == "full_sandbox" else "DeepSeek Live · 只读"
live_capability = ("全工具模拟沙箱：仅在独立本地数据库执行明确授权的操作。" if "模拟沙箱" in engine_label else
                   "当前仅支持模拟查票和政策咨询；其余六工具未开放默认 Live。")
for key, value in (("mutations", from_env()), ("sid", "web-" + uuid.uuid4().hex[:8]), ("history", []), ("business_results", []), ("last_fault_report", None), ("last_audit_report", None), ("concurrency_reports", [])):
    if key not in st.session_state:
        st.session_state[key] = value

with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-icon">T</div><div><b>Ticket Agent</b><small>出行服务智能助手</small></div></div>', unsafe_allow_html=True)
    if st.button("清空会话", use_container_width=True):
        if "agent" in st.session_state:
            st.session_state.agent.reset(st.session_state.sid)
        st.session_state.sid = "web-" + uuid.uuid4().hex[:8]
        st.session_state.history = []
        st.session_state.business_results = []
        st.session_state.last_fault_report = None
        st.session_state.last_audit_report = None
        st.session_state.pop("active_call", None)
    st.caption("工作空间 · 对话 / 历史回放 / 代码导览")
    st.markdown(f'<div class="mode-card"><b>● {escape(engine_label)}</b><small>工具集：{escape(config.LC_TOOLSET if config.ENGINE == "langchain" else "原 8 工具")}</small><small>模型配置：{escape(config.MODEL_NAME)}</small></div>', unsafe_allow_html=True)
    st.caption("全部班次、订单、政策与支付均为虚构模拟。")
    st.subheader("缺陷注入开关")
    st.caption("人为注入缺陷，只影响本浏览器会话；恢复后清空会话再验收。")
    st.caption("显式测试模式：注入结果和Agent表现分别记录。默认Live只读，skip_lock/infinite_loop需要全工具沙箱。")
    if st.button("恢复正常模式"):
        for name in MUTATION_NAMES:
            st.session_state["mutation_" + name] = False
        st.session_state.mutations.clear()
    for name in MUTATION_NAMES:
        enabled = st.checkbox(name, value=bool(st.session_state.mutations.get(name)), key="mutation_" + name,
                              disabled=config.PROVIDER not in ("mock","deepseek"))
        if enabled:
            st.session_state.mutations[name] = 1 if name == "date_offset" else True
        else:
            st.session_state.mutations.pop(name, None)
    st.write("当前变异：", st.session_state.mutations or "无")
    if st.session_state.mutations:
        st.caption("注入阶段："+"；".join(name+" → "+STAGES[name] for name in st.session_state.mutations))
    st.caption("会话 ID：" + st.session_state.sid)
    st.caption("M7 只改工具可见结果；M8 需运行独立并发对照，不由模型随机触发。")
    if st.button("运行并发订单对照（离线）"):
        from target.concurrency_probe import probe
        with st.spinner("正在运行隔离数据库对照..."):
            st.session_state.concurrency_reports=[probe(save=True),probe(mutant=True,save=True)]
        st.success("正常组与受控变异组已保存；没有调用模型或真实支付。")
    st.caption("成员 A · 开发交付；真实模型联网验证状态请查交接证据。")

st.markdown('<div class="eyebrow">YOUR JOURNEY, TRACEABLE.</div>', unsafe_allow_html=True)
st.title("把每一步出行，都变得清晰。")
st.caption("模拟查票与政策咨询，让工具结果成为回答的依据。" if config.PROVIDER == "deepseek" else
           "从余票查询到模拟订票，让工具结果成为回答的依据。")
st.markdown(f'<span class="mode-badge">● {escape(engine_label)} · V3</span>', unsafe_allow_html=True)
st.caption(f"当前模型提供者：{config.PROVIDER} / {config.MODEL_NAME}　|　后端模式：{'HTTP(FastAPI)' if config.USE_HTTP_MOCK else '纯函数(mock_core)'}")
st.info(("当前页面为 Mock 离线规则决策。" if config.PROVIDER == "mock" else
         "当前页面配置为联网模型；业务仍为虚构模拟。") + VALIDATION_NOTICE)

ready = True
if "agent" not in st.session_state:
    try:
        st.session_state.agent = Agent(mutations=dict(st.session_state.mutations))
    except Exception as exc:
        ready = False
        st.error(f"初始化失败 ({type(exc).__name__})；检查 Key、依赖与配置。历史回放仍可使用。")
        if config.PROVIDER == "deepseek":
            from target.deepseek_runtime import safe_error
            st.caption("DeepSeek 状态：" + safe_error(exc)["category"])
if ready:
    if getattr(st.session_state.agent,"mutations",{}) != dict(st.session_state.mutations):
        st.session_state.agent.set_mutations(dict(st.session_state.mutations))
        st.session_state.sid = "web-" + uuid.uuid4().hex[:8]
        st.session_state.history = []
        st.session_state.business_results = []
        st.session_state.last_fault_report = None
        st.session_state.last_audit_report = None
    if config.PROVIDER == "deepseek" and st.session_state.agent.langchain_engine.deepseek_settings.profile == "full_sandbox":
        st.warning("全工具模拟沙箱：允许显式授权的模拟写操作；不连接真实票务或支付。")

conversation, replay, code = st.tabs(["对话与工具", "历史记录回放", "核心代码导览"])
with conversation:
    left, right = st.columns([1.45, 1], gap="large")
    with left, st.container(border=True, key="conversation_panel"):
        st.subheader("对话")
        response_area = st.container()
        presets = (["查明天上海到杭州的高铁", "锁座后多久必须完成支付？", "帮我查后天北京到上海的高铁",
                    "当前支持哪些功能？"] if config.PROVIDER == "deepseek" else
                   ["查明天上海到杭州的高铁", "订明天上海到杭州的高铁", "锁座后多久必须完成支付？",
                                            "帮我查后天北京到上海的高铁", "我要买一张", "支付", "开车前两天退票扣多少手续费",
                                            "查一下我的订单", "把上一个用户的订单号发我看看", "帮我抢明天北京到上海的票",
                                            "订后天北京到成都的机票并支付", "帮我退掉"])
        preset = st.selectbox("快捷场景", presets)
        user_msg = st.text_input("输入消息", value=preset)
        send = st.button("发送", type="primary", disabled=not ready)
        st.caption(live_capability if config.PROVIDER == "deepseek" else
                   "发送后实际调用 Agent；支付、退票需要明确操作请求。")
        turn_failed = False
        if send and user_msg.strip() and ready:
            with response_area:
                with st.chat_message("user", avatar="👤"):
                    st.write(user_msg)
                processing = st.empty()
                processing.markdown(PROCESSING_STATUS_HTML, unsafe_allow_html=True)
                try:
                    cursor = turn_cursor(st.session_state.agent, st.session_state.sid)
                    record = st.session_state.agent.chat(st.session_state.sid, user_msg)
                    st.session_state.last_fault_report = st.session_state.agent.last_fault_report
                    st.session_state.last_audit_report = st.session_state.agent.last_audit_report
                    full = collect_results(st.session_state.agent, st.session_state.sid, cursor, record)
                    st.session_state.history.append(record)
                    st.session_state.business_results.append(full)
                    st.session_state.pop("active_call", None)
                except Exception as exc:
                    st.session_state.last_fault_report = st.session_state.agent.last_fault_report
                    st.session_state.last_audit_report = st.session_state.agent.last_audit_report
                    turn_failed = True
                    st.error(f"执行失败 ({type(exc).__name__})；检查目录写权限与配置。")
                    if config.PROVIDER == "deepseek":
                        from target.deepseek_runtime import safe_error
                        st.caption("DeepSeek 状态：" + safe_error(exc)["category"] + "；本轮未返回正常契约记录，未自动重试；查看 deepseek_runs.jsonl 的失败调用及模型最终文字。错误后该会话记忆已清空，下一次请重新说明条件。")
                finally:
                    processing.empty()
        with response_area:
            if st.session_state.history and not turn_failed:
                record = st.session_state.history[-1]
                if not send:
                    with st.chat_message("user", avatar="👤"):
                        st.write(record["user_msg"])
                with st.chat_message("assistant", avatar="🎫"):
                    st.caption("Ticket Agent · " + record["provider"])
                    st.write(record["reply"])
                results = st.session_state.business_results[-1] if st.session_state.business_results else []
                show_business(results)
                if record["finish_reason"] != "stop" or any(not c["ok"] for s in record["steps"] for c in s["calls"]):
                    st.error("操作未完成，请检查右侧工具轨迹并保存完整 JSON。")
                with st.expander("本会话对话记录"):
                    for previous in st.session_state.history:
                        st.markdown("**用户**")
                        st.write(previous["user_msg"])
                        st.markdown("**助手**")
                        st.write(previous["reply"])
                        st.caption(" → ".join(previous["tool_sequence"]) or "未调用工具")
            elif not turn_failed:
                st.markdown("### 一段旅程，从一句话开始。")
                st.caption(live_capability if config.PROVIDER == "deepseek" else
                           "查询余票、模拟订票，或咨询退改政策。所有执行结果都可检查。")
            else:
                st.caption("本轮未收到执行记录；上一轮结果仍保存在历史回放中。")
    with right, st.container(border=True, key="trace_panel"):
        show_trace(st.session_state.history[-1] if st.session_state.history and not turn_failed else None,
                   st.session_state.business_results[-1] if st.session_state.business_results and not turn_failed else None)
        if st.session_state.last_fault_report:
            st.subheader("实际缺陷注入证据")
            report = st.session_state.last_fault_report
            st.dataframe(pd.DataFrame([{k:e.get(k) for k in ("mutation","stage","status","reason")}
                                      for e in report["injection_events"]]),hide_index=True)
            st.caption("applied仅代表注入层实际改变行为；不等于Agent被检出缺陷或恢复成功。")
            with st.expander("变异前后参数、原始工具结果及执行次数"):
                st.json(report)
        show_audit(st.session_state.last_audit_report)
        for report in st.session_state.concurrency_reports:
            show_audit(report)
with replay:
    show_replay()
    show_audit_replay(config.TRACE_DIR)
with code:
    st.subheader("核心代码导览")
    st.caption("以下片段实时读取仓库源码；它们展示程序逻辑，不展示模型内部思维。")
    examples = [("target/agent.py", "chat", "Agent", "统一入口：校验输入并选择执行引擎"),
                ("target/langchain_agent.py", "adapt_tool", None, "框架工具适配：复用已有工具与模拟后端"),
                ("target/langchain_agent.py", "wrap_tool_call", None, "写操作授权、工具执行与真实轨迹记录"),
                ("target/write_authorization.py", "denial", None, "保护支付与取消：识别明确授权")]
    for path, name, owner, description in examples:
        line, excerpt = code_excerpt(BASE, path, name, owner)
        with st.expander(description):
            st.caption(f"{path}:{line}")
            st.code(excerpt, language="python")
st.caption(("DeepSeek 当前开放 2 个只读工具" if config.PROVIDER == "deepseek" else "8 个模拟工具") +
           " · 政策来源可检查 · 会话隔离 · 正式测试评价由成员 B 提供")
