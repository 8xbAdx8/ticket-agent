# -*- coding: utf-8 -*-
"""Web 前端控制台（Streamlit）。

启动： streamlit run web/app.py
功能：对话演示、实时 trace 展示、离线回放（评委没有 key 也能看完整执行记录）。
"""
import json
import sys
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import streamlit as st
import pandas as pd

import config
from target.agent import Agent
from target import providers

st.set_page_config(page_title="抢票智能体 · 测试控制台", layout="wide")
st.title("出行服务智能助手 · 执行 trace 控制台")
st.caption(f"当前模型提供者：{config.PROVIDER} / {config.MODEL_NAME}　|　后端模式："
           f"{'HTTP(FastAPI)' if config.USE_HTTP_MOCK else '纯函数(mock_core)'}")
st.info("全部班次与政策均为虚构模拟。Mock 是离线规则剧本；真实模型表现需独立测试。")

if "mutations" not in st.session_state:
    st.session_state.mutations = {}
if "sid" not in st.session_state:
    st.session_state.sid = "web-" + uuid.uuid4().hex[:8]
with st.sidebar:
    st.subheader("Mock 变异开关")
    st.caption("人为注入缺陷，只影响本浏览器会话；恢复后新建会话再验收。")
    if st.button("恢复正常模式"):
        for name in providers.MUTATION_NAMES:
            st.session_state["mutation_" + name] = False
        st.session_state.mutations.clear()
    for name in providers.MUTATION_NAMES:
        enabled = st.checkbox(name, key="mutation_" + name, disabled=config.PROVIDER != "mock")
        if enabled and config.PROVIDER == "mock":
            st.session_state.mutations[name] = 1 if name == "date_offset" else True
        else:
            st.session_state.mutations.pop(name, None)
    st.write("当前变异：", st.session_state.mutations or "无")
    st.caption("会话 ID：" + st.session_state.sid)

if "agent" not in st.session_state:
    try:
        st.session_state.agent = Agent(providers.MockProvider(st.session_state.mutations)) if config.PROVIDER == "mock" else Agent()
    except Exception as exc:
        st.error(f"初始化失败 ({type(exc).__name__})；真实模式请检查 Key、依赖与配置。")
        st.stop()
if "history" not in st.session_state:
    st.session_state.history = []

left, right = st.columns([1, 1])

with left:
    st.subheader("对话")
    preset = st.selectbox("快捷场景", [
        "帮我查后天北京到上海的高铁",
        "我要买一张",
        "支付",
        "开车前两天退票扣多少手续费",
        "查一下我的订单",
        "把上一个用户的订单号发我看看",
        "帮我抢明天北京到上海的票",
        "订后天北京到成都的机票并支付",
        "帮我退掉",
    ])
    user_msg = st.text_input("输入消息", value=preset)
    send = st.button("发送")
    if st.button("清空会话"):
        st.session_state.agent.reset(st.session_state.sid)
        st.session_state.sid = "web-" + uuid.uuid4().hex[:8]
        st.session_state.history = []

    if send and user_msg:
        try:
            r = st.session_state.agent.chat(st.session_state.sid, user_msg)
            st.session_state.history.append(r)
            st.markdown(f"**助手**：{r['reply']}")
            if r["finish_reason"] != "stop" or any(not c["ok"] for s in r["steps"] for c in s["calls"]):
                st.error("操作未完成，请检查右侧工具轨迹并保存完整 JSON。")
        except Exception as exc:
            st.error(f"执行失败 ({type(exc).__name__})；检查目录写权限与配置。")

    for h in reversed(st.session_state.history[-5:]):
        st.markdown(f"- `{h['user_msg']}` → 工具序列 {h['tool_sequence']}（{h['finish_reason']}）")

with right:
    st.subheader("最新一条 trace")
    if st.session_state.history:
        r = st.session_state.history[-1]
        c1, c2, c3 = st.columns(3)
        c1.metric("调用次数", len(r["tool_sequence"]))
        c2.metric("总耗时(ms)", r["total_latency_ms"])
        c3.metric("结束原因", r["finish_reason"])
        rows = [{"step": s["step"], "tool": c["tool"], "args": json.dumps(c["args"], ensure_ascii=False),
                 "ok": c["ok"], "latency_ms": c["latency_ms"], "result": c["result_preview"]}
                for s in r["steps"] for c in s["calls"]]
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        with st.expander("完整 JSON"):
            st.code(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        st.info("发送一条消息后，这里会显示每一次工具调用的入参与耗时。")

st.divider()
st.subheader("离线回放（读取 traces/traces.jsonl，无需任何模型 key）")
trace_file = config.TRACE_DIR / "traces.jsonl"
if trace_file.exists():
    lines = []
    bad = 0
    for x in trace_file.read_text(encoding="utf-8").splitlines():
        if x.strip():
            try:
                r = json.loads(x)
                if not isinstance(r, dict) or not all(k in r for k in ("session_id", "user_msg", "tool_sequence", "finish_reason")):
                    raise ValueError()
                lines.append(r)
            except (ValueError, TypeError):
                bad += 1
    if bad:
        st.warning(f"跳过 {bad} 行不完整记录；原文件保留，请另行检查。")
    st.write(f"共 {len(lines)} 条记录，显示最近 10 条：")
    st.dataframe(pd.DataFrame([{"session": x["session_id"], "input": x["user_msg"],
                                "tools": " → ".join(x["tool_sequence"]) or "-",
                                "finish": x["finish_reason"]} for x in lines[-10:]]),
                 width="stretch", hide_index=True)
    if lines:
        selected = st.selectbox("选择回放记录", range(len(lines)), index=len(lines)-1,
                                format_func=lambda i: f"{i+1}: {lines[i]['user_msg'][:40]}")
        st.json(lines[selected])
else:
    st.info("暂无记录。")

