"""Resolve only sessions already in this browser or explicitly addressed by ID."""
from collections import OrderedDict
import secrets
from threading import Lock

import streamlit as st

from web.session_store import restore_by_sid
from web.workbench_config import WORKBENCH_PAGES

_ACTIVE = OrderedDict()
_LOCK = Lock()


def active_session(sid):
    token = st.query_params.get('resume')
    with _LOCK:
        entry = _ACTIVE.get(token)
        return entry if entry is not None and entry.sid == sid else None


def remember_active(session):
    if session.read_only:
        st.query_params.pop('resume', None)
        return
    token = getattr(session, '_browser_resume', None)
    if token is None:
        token = session._browser_resume = secrets.token_urlsafe(24)
    with _LOCK:
        _ACTIVE[token] = session
        _ACTIVE.move_to_end(token)
        if len(_ACTIVE) > 128:
            _ACTIVE.popitem(last=False)
    if st.query_params.get('resume') != token:
        st.query_params['resume'] = token


def get_testable_sessions(sessions, requested_sid=None, workspace='user'):
    available = {session.sid: session for session in sessions}
    if requested_sid and requested_sid not in available:
        try:
            restored = active_session(requested_sid) or restore_by_sid(requested_sid, workspace=workspace)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        else:
            available[restored.sid] = restored
    return list(available.values())


def open_test_console(sid, workspace='user'):
    if st.query_params.get('session_id') != sid:
        st.query_params.pop('abc_run', None)
        st.query_params.pop('abc_batch', None)
    st.query_params['session_id'] = sid
    st.query_params['source'] = workspace
    st.session_state['workspace_mode'] = '测试工作台'
    st.session_state['workspace_page'] = WORKBENCH_PAGES[0]
    st.query_params['board'] = '1'
    st.session_state['c_source_focus'] = sid


def open_developer(sid, run_id, workspace='user'):
    st.query_params['session_id'] = sid
    st.query_params['source'] = workspace
    st.session_state['workspace_mode'] = '开发者工作台'
    st.session_state['dev_focus'] = (sid, run_id)


def open_client(sid):
    st.query_params['session_id'] = sid
    st.query_params['source'] = 'user'
    st.query_params.pop('abc_batch', None)
    st.query_params.pop('abc_run', None)
    st.session_state['workspace_mode'] = '出行助手'
    st.session_state['user_source_focus'] = sid
