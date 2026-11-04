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
from contextlib import nullcontext
from web.design import theme
from web.user_copy import workspace_label

from web.runtime import CALL_LOCK,refresh_conversations,render_value,render_environment


def main():
    st.set_page_config(page_title="Ticket Agent · 出行助手", page_icon=":material/travel_explore:", layout="wide", initial_sidebar_state="auto")
    refresh_conversations(st.session_state.get('user_sessions',[])+st.session_state.get('lab_archives',[])
                          +([st.session_state['lab_session']] if 'lab_session' in st.session_state else []))
    st.set_option("client.toolbarMode","minimal")
    st.session_state.setdefault("default_live", render_value("PROVIDER") in ("deepseek","bailian"))
    st.session_state.setdefault("default_engine", render_value("ENGINE"))
    st.session_state.setdefault("theme", "浅色")
    with st.sidebar:
        st.markdown('<div class="ta-brand"><div class="ta-logo">T</div><div><b>Ticket Agent</b><small>出行助手 · 3.7</small></div></div>', unsafe_allow_html=True)
        with st.expander('模型设置（高级）', expanded=False):
            choices=["Legacy Mock","LangChain Mock","DeepSeek Live","Qwen3.8-Flash Live"]
            qwen_ready=bool(os.getenv("DASHSCOPE_API_KEY","").strip())
            initial=3 if (qwen_ready or render_value("PROVIDER")=="bailian") else 2 if render_value("PROVIDER")=="deepseek" else 1 if render_value("ENGINE")=="langchain" else 0
            selection=st.selectbox("新会话模型",choices,index=initial,key="provider_selection")
            st.session_state["default_live"]=selection.endswith("Live")
            st.session_state["default_engine"]="legacy" if selection=="Legacy Mock" else "langchain"
            st.session_state["default_provider"]="bailian" if selection=="Qwen3.8-Flash Live" else "deepseek"
            st.session_state["default_live_model"]="qwen3.8-flash" if selection=="Qwen3.8-Flash Live" else None
        mode = st.radio("工作空间", ["出行助手", "开发者工作台", "测试工作台"], key="workspace_mode",
                        format_func=workspace_label)
        if mode == "测试工作台":
            page = st.radio("工作台导航", ["测试总览", "测试实验室", "Trace 分析", "质量分析", "模型对比", "RAG 知识库", "集成中心", "V3.7 离线验收"], key="workspace_page",format_func=lambda value:'离线回归中心' if value=='V3.7 离线验收' else value)
        elif mode == "开发者工作台":
            page = "开发者工作台"
        else:
            page = "出行助手"
        st.divider()
        selected_theme = st.radio("外观", ["深色", "浅色"], horizontal=True, key="theme")
        st.caption("模型选项仅用于新建会话；在线服务可能产生模型使用费用。")
        st.caption("用户空间用于出行咨询；开发者空间查看技术诊断；测试控制台独立保留。")
    theme(selected_theme)
    with (nullcontext() if page == "出行助手" else CALL_LOCK):
        if page == "出行助手":
            from web.conversation import user_page
            with st.container(key='user_workspace'):
                user_page()
        elif page == "开发者工作台":
            from web.developer_workspace import developer_page
            sessions=st.session_state.get("user_sessions",[])+st.session_state.get("lab_archives",[])
            if st.session_state.get("lab_session") is not None:
                sessions=sessions+[st.session_state["lab_session"]]
            developer_page(sessions)
        elif page == "V3.7 离线验收":
            from web.v37_console import page as acceptance_page
            acceptance_page()
        elif page == "测试总览":
            from web.competition_view import competition_page
            sessions = st.session_state.get("user_sessions", []) + st.session_state.get("lab_archives", [])
            competition_page(sessions)
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
        if page != '出行助手':
            st.caption("Ticket Agent 3.7 · 当前使用演示数据，不提供真实出票服务。")


# Agent calls own CALL_LOCK; rendering the user page must not wait for an auxiliary request.
main()
