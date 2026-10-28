# -*- coding: utf-8 -*-
"""V3.3 composition only. Existing Agent and contract remain authoritative."""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
# LangChain invocation is always inside tracing_context(enabled=False).
# LangSmith export is a separate consented action, never an automatic callback.
import streamlit as st
import config
from web.design import theme

from web.runtime import CALL_LOCK,refresh_conversations


def main():
    st.set_page_config(page_title="Ticket Agent · 质量工作空间", page_icon=":material/travel_explore:", layout="wide", initial_sidebar_state="expanded")
    refresh_conversations(st.session_state.get('user_sessions',[])+st.session_state.get('lab_archives',[])
                          +([st.session_state['lab_session']] if 'lab_session' in st.session_state else []))
    st.set_option("client.toolbarMode","minimal")
    st.session_state.setdefault("default_live", config.PROVIDER in ("deepseek","bailian"))
    st.session_state.setdefault("default_engine", config.ENGINE)
    st.session_state.setdefault("theme", "深色")
    with st.sidebar:
        st.markdown('<div class="ta-brand"><div class="ta-logo">T</div><div><b>Ticket Agent</b><small>智能体质量工作空间 · V3.5</small></div></div>', unsafe_allow_html=True)
        choices=["Legacy Mock","LangChain Mock","DeepSeek Live","Qwen3.8-Flash Live"]
        initial=3 if config.PROVIDER=="bailian" else 2 if config.PROVIDER=="deepseek" else 1 if config.ENGINE=="langchain" else 0
        selection=st.selectbox("新会话模型",choices,index=initial,key="provider_selection")
        st.session_state["default_live"]=selection.endswith("Live")
        st.session_state["default_engine"]="legacy" if selection=="Legacy Mock" else "langchain"
        st.session_state["default_provider"]="bailian" if selection=="Qwen3.8-Flash Live" else "deepseek"
        st.session_state["default_live_model"]="qwen3.8-flash" if selection=="Qwen3.8-Flash Live" else None
        mode = st.radio("工作空间", ["出行助手", "测试工作台"], key="workspace_mode")
        if mode == "测试工作台":
            page = st.radio("工作台导航", ["测试总览", "测试实验室", "Trace 分析", "质量分析", "模型对比", "RAG 知识库", "集成中心"], key="workspace_page")
        else:
            page = "出行助手"
        st.divider()
        selected_theme = st.radio("外观", ["深色", "浅色"], horizontal=True, key="theme")
        st.caption("新会话模型："+selection+(" · 八工具模拟沙箱" if selection.endswith("Live") else ""))
        st.caption("用户与实验会话、模拟库、Trace 分离。B 测试快照只读。")
    theme(selected_theme)
    if page == "出行助手":
        from web.conversation import user_page
        user_page()
    elif page == "测试总览":
        from web.dashboard import dashboard_page
        sessions = st.session_state.get("user_sessions", []) + st.session_state.get("lab_archives", [])
        dashboard_page([s.trace_dir for s in sessions], [s.trace_dir for s in st.session_state.get("lab_archives", [])])
    elif page == "测试实验室":
        from web.laboratory import lab_page
        lab_page()
    elif page == "Trace 分析":
        from web.trace_view import trace_page
        sessions = st.session_state.get("user_sessions", []) + st.session_state.get("lab_archives", [])
        trace_page([s.trace_dir for s in sessions])
    elif page == "质量分析":
        from web.quality import quality_page
        sessions=st.session_state.get("user_sessions",[])+st.session_state.get("lab_archives",[])
        quality_page(sessions)
    elif page == "模型对比":
        from web.comparison import comparison_page
        sessions=st.session_state.get("user_sessions",[])+st.session_state.get("lab_archives",[])
        comparison_page([s.trace_dir for s in sessions])
    elif page == "集成中心":
        from web.integrations import integrations_page
        integrations_page()
    elif page == "RAG 知识库":
        from web.rag_page import rag_page
        sessions=st.session_state.get("user_sessions",[])+st.session_state.get("lab_archives",[])
        rag_page(sessions)
    st.caption("Ticket Agent V3.5 · 票务业务为虚构模拟 · 正式质量评价由 B 提供 · 页面浏览不发起模型请求")


# Serialize rendering with calls because legacy configuration is module-scoped.
with CALL_LOCK:
    main()
