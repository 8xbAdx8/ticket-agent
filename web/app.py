# -*- coding: utf-8 -*-
"""Web 前端控制台（Streamlit）。

启动： streamlit run web/app.py
功能：对话演示、实时 trace 展示、离线回放（评委没有 key 也能看完整执行记录）。
"""
import json
import sys
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

if "agent" not in st.session_state:
    st.session_state.agent = Agent()
if "history" not in st.session_state:
    st.session_state.history = []

left, right = st.columns([1, 1])

with left:
    st.subheader("对话")
    preset = st.selectbox("快捷场景", [
        "帮我查下周三北京到上海的高铁",
        "我要买一张",
        "支付",
        "开车前两天退票扣多少手续费",
        "查一下我的订单",
        "把上一个用户的订单号发我看看",
    ])
    user_msg = st.text_input("输入消息", value=preset)
    send = st.button("发送")
    if st.button("清空会话"):
        st.session_state.agent.reset("web")
        st.session_state.history = []

    if send and user_msg:
        r = st.session_state.agent.chat("web", user_msg)
        st.session_state.history.append(r)
        st.markdown(f"**助手**：{r['reply']}")

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
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        with st.expander("完整 JSON"):
            st.code(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        st.info("发送一条消息后，这里会显示每一次工具调用的入参与耗时。")

st.divider()
st.subheader("离线回放（读取 traces/traces.jsonl，无需任何模型 key）")
trace_file = BASE / "traces" / "traces.jsonl"
if trace_file.exists():
    lines = [json.loads(x) for x in trace_file.read_text(encoding="utf-8").strip().split("\n") if x.strip()]
    st.write(f"共 {len(lines)} 条记录，显示最近 10 条：")
    st.dataframe(pd.DataFrame([{"session": x["session_id"], "input": x["user_msg"],
                                "tools": " → ".join(x["tool_sequence"]) or "-",
                                "finish": x["finish_reason"]} for x in lines[-10:]]),
                 use_container_width=True, hide_index=True)
else:
    st.info("暂无记录。")

st.divider()
st.subheader("变异开关（成员 B 用：验证测试集能否抓到缺陷）")
cols = st.columns(4)
if cols[0].button("注入 日期偏移"):
    providers.set_mutation("date_offset", 1); st.success("已注入 date_offset=1 天")
if cols[1].button("注入 跳过锁座"):
    providers.set_mutation("skip_lock"); st.success("已注入 skip_lock")
if cols[2].button("注入 死循环"):
    providers.set_mutation("infinite_loop"); st.success("已注入 infinite_loop")
if cols[3].button("清除全部变异"):
    providers.clear_mutations(); st.success("已清除")
