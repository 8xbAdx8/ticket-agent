# -*- coding: utf-8 -*-
"""V3.3 composition only. Existing Agent and contract remain authoritative."""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
# No external telemetry from this UI, even if enabled in the parent shell.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
import streamlit as st
import config
from web.design import theme

st.set_page_config(page_title="Ticket Agent · 质量工作空间", page_icon=":material/travel_explore:", layout="wide", initial_sidebar_state="expanded")
st.session_state.setdefault("default_live", config.PROVIDER == "deepseek")
st.session_state.setdefault("default_engine", config.ENGINE)
st.session_state.setdefault("theme", "深色")
with st.sidebar:
    st.markdown('<div class="ta-brand"><div class="ta-logo">T</div><div><b>Ticket Agent</b><small>智能体质量工作空间 · V3.3</small></div></div>', unsafe_allow_html=True)
    mode = st.radio("工作空间", ["出行助手", "测试工作台"], key="workspace_mode")
    if mode == "测试工作台":
        page = st.radio("工作台导航", ["测试总览", "测试实验室", "Trace 分析", "质量分析", "模型对比", "集成中心"], key="workspace_page")
    else:
        page = "出行助手"
    st.divider()
    selected_theme = st.radio("外观", ["深色", "浅色"], horizontal=True, key="theme")
    st.caption("启动模型：" + ("DeepSeek Live · 只读" if config.PROVIDER == "deepseek" else "LangChain Mock" if config.ENGINE == "langchain" else "Legacy Mock"))
    st.caption("用户与实验会话、模拟库、Trace 分离。B 测试快照只读。")
theme(selected_theme)
if page == "出行助手":
    from web.conversation import user_page
    user_page()
elif page == "测试总览":
    from web.dashboard import dashboard_page
    dashboard_page()
elif page == "测试实验室":
    from web.laboratory import lab_page
    lab_page()
elif page == "Trace 分析":
    from web.trace_view import trace_page
    sessions = st.session_state.get("user_sessions", []) + st.session_state.get("lab_archives", [])
    trace_page([s.trace_dir for s in sessions])
elif page == "质量分析":
    from web.quality import quality_page
    quality_page()
elif page == "模型对比":
    from web.comparison import comparison_page
    comparison_page()
elif page == "集成中心":
    from web.integrations import integrations_page
    integrations_page()
st.caption("Ticket Agent V3.3 · 票务业务为虚构模拟 · 正式质量评价由 B 提供 · 页面浏览不发起模型请求")
