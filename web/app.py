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
import streamlit.components.v1 as components
import config
from contextlib import nullcontext
from web.design import theme
from web.user_copy import workspace_label

from web.runtime import CALL_LOCK,refresh_conversations,render_value,render_environment
from web.workbench_config import WORKBENCH_PAGES


def workbench_page_label(value):
    return value


def main():
    st.set_page_config(page_title="Ticket Agent · 出行助手", page_icon=str(BASE/'assets/ticket-agent.ico'), layout="wide", initial_sidebar_state="auto")
    refresh_conversations(st.session_state.get('user_sessions',[])+st.session_state.get('lab_archives',[])
                          +([st.session_state['lab_session']] if 'lab_session' in st.session_state else []))
    st.set_option("client.toolbarMode","minimal")
    st.session_state.setdefault("default_live", render_value("PROVIDER") in ("deepseek","bailian"))
    st.session_state.setdefault("default_engine", render_value("ENGINE"))
    st.session_state.setdefault("theme", "深色" if st.query_params.get('appearance') == 'dark' else "浅色")
    with st.sidebar:
        st.markdown('<div class="ta-brand"><div class="ta-logo">T</div><div><b>Ticket Agent</b><small>出行助手 · 3.7</small></div></div>', unsafe_allow_html=True)
        with st.expander('模型设置（高级）', expanded=False):
            choices=["Legacy Mock","LangChain Mock","DeepSeek Live","Qwen3.8-Flash Live"]
            offline = os.getenv('TICKET_WEB_OFFLINE_ONLY') == '1'
            if offline:
                choices = choices[:2]
                if st.session_state.get('provider_selection') not in choices:
                    st.session_state.pop('provider_selection', None)
            provider = render_value("PROVIDER")
            initial = (3 if not offline and provider == "bailian" else
                       2 if not offline and provider == "deepseek" else
                       1 if render_value("ENGINE") == "langchain" else 0)
            selection=st.selectbox("新会话模型",choices,index=initial,key="provider_selection")
            st.session_state["default_live"]=selection.endswith("Live")
            st.session_state["default_engine"]="legacy" if selection=="Legacy Mock" else "langchain"
            st.session_state["default_provider"]="bailian" if selection=="Qwen3.8-Flash Live" else "deepseek"
            st.session_state["default_live_model"]="qwen3.8-flash" if selection=="Qwen3.8-Flash Live" else None
        workspaces = ["出行助手", "开发者工作台", "测试工作台"]
        routes = dict(zip(('client', 'developer', 'test'), workspaces, strict=True))
        requested = routes.get(st.query_params.get('workspace'))
        if 'workspace_mode' not in st.session_state and (requested or st.query_params.get('abc_run')):
            st.session_state['workspace_mode'] = requested or '测试工作台'
            ordinal = st.query_params.get('board')
            st.session_state['workspace_page'] = (WORKBENCH_PAGES[int(ordinal)-1]
                                                  if ordinal in ('1', '2', '3', '4', '5') else WORKBENCH_PAGES[0])
        mode = st.radio("工作空间", workspaces, key="workspace_mode",
                        format_func=workspace_label)
        route = next(key for key, name in routes.items() if name == mode)
        if st.query_params.get('workspace') != route:
            st.query_params['workspace'] = route
        if mode == "测试工作台":
            # Exactly five workbench entries; historical pages remain importable
            # for evidence/backward compatibility but are not routes.
            if st.session_state.get('workspace_page') not in WORKBENCH_PAGES:
                st.session_state['workspace_page'] = WORKBENCH_PAGES[0]
            page = st.radio("工作台导航", WORKBENCH_PAGES, key="workspace_page", format_func=workbench_page_label)
            board = str(WORKBENCH_PAGES.index(page) + 1)
            if st.query_params.get('board') != board:
                st.query_params['board'] = board
        elif mode == "开发者工作台":
            page = "开发者工作台"
        else:
            page = "出行助手"
        st.divider()
        selected_theme = st.radio("外观", ["深色", "浅色"], horizontal=True, key="theme")
        appearance = 'dark' if selected_theme == '深色' else 'light'
        if st.query_params.get('appearance') != appearance:
            st.query_params['appearance'] = appearance
    theme(selected_theme)
    # Streamlit keeps the scroll offset when the page changes; jump back to the
    # top so a new board never opens halfway down.
    if st.session_state.get('_ta_last_page') != page:
        st.session_state['_ta_last_page'] = page
        components.html(
            '<script>const d=window.parent.document;'
            'const el=d.querySelector("section.main")||d.querySelector(\'[data-testid="stAppViewContainer"]\');'
            'if(el){el.scrollTop=0;}</script>', height=0)
    with (nullcontext() if page == "出行助手" else CALL_LOCK):
        if page == "出行助手":
            from web.conversation import user_page
            with st.container(key='user_workspace'):
                user_page()
        elif page == "开发者工作台":
            from web.developer_workspace import developer_page
            from web.session_links import get_testable_sessions
            sessions=st.session_state.get("user_sessions",[])+st.session_state.get("lab_archives",[])
            if st.session_state.get("lab_session") is not None:
                sessions=sessions+[st.session_state["lab_session"]]
            restored = get_testable_sessions(sessions, st.query_params.get('session_id'), st.query_params.get('source','user'))
            developer_page(sessions + [s for s in restored if s not in sessions])
        elif page in WORKBENCH_PAGES:
            from web import consistency_audit_view as workbench
            sessions = st.session_state.get('user_sessions', [])
            callbacks = (lambda: workbench.competition_page(sessions), lambda: workbench.quality_page(sessions),
                         lambda: workbench.rag_page(sessions), workbench.lab_page,
                         lambda: workbench.trace_page([s.trace_dir for s in sessions]))
            callbacks[WORKBENCH_PAGES.index(page)]()


# Agent calls own CALL_LOCK; rendering the user page must not wait for an auxiliary request.
main()
