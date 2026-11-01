"""Three panes bound to one selected run; debug runs are separate runs.

The middle pane may only show events whose ``run_id`` is the selected one. When
a run has no event file, the fallback comes from the saved audit and is labelled
as such, so a debug run can never be mistaken for the run being replayed.
"""
import uuid
import streamlit as st
from web.design import header, escape, processing_event
from web.developer import developer_page as configuration_page
from web.run_evidence import workflow_rows, policy_evidence
from web.run_view import call_rows, event_card, event_headline, load_events
from target.diagnostics import sanitize

MODE_LABELS = {"debug": "独立调试", "current": "当前运行", "history": "历史回放"}


def _run_mode(session, audit, sessions, debug):
    """One run is 'current', every other saved run is 'history', debug is its own."""
    if getattr(session,'read_only',False):return 'history'
    if debug is not None and session is debug:
        return "debug"
    newest = next((s for s in reversed(sessions) if getattr(s, "audits", None)), None)
    if session is newest and session.audits and session.audits[-1] is audit:
        return "current"
    return "history"


def _mode_chip(mode):
    return f'<span class="ta-mode ta-mode-{escape(mode)}">{escape(MODE_LABELS.get(mode, mode))}</span>'


def developer_page(sessions):
    header('Agent 开发者端 · 展示我们如何设计这个 Agent', '会话实验下一轮生效；正式Baseline只读。运行、配置旁证和历史证据分开核对。', '设计 / 运行 / 证据')
    debug = st.session_state.get('developer_debug')
    available = list(sessions) + ([debug] if debug and debug not in sessions else [])
    if not available:
        available = []

    # A finished debug run is focused on the next rerun, before any widget exists.
    focus = st.session_state.pop('dev_focus', None)
    if focus and available:
        for index, candidate in enumerate(available):
            if candidate.sid == focus[0]:
                st.session_state['dev_session_index'] = index
                st.session_state['dev_run_index'] = next((i for i,a in enumerate(candidate.audits)
                    if a.get('trace_id')==focus[1]), max(0, len(candidate.audits) - 1))

    _run_bar(available, debug)

    selected = None
    audit = None
    mode = 'history'
    if available:
        session_index = st.selectbox(
            '证据会话', range(len(available)), index=len(available) - 1,
            format_func=lambda n: f"{available[n].sid} · {len(available[n].audits)} 次运行"
                                  + (" · 独立调试" if debug is not None and available[n] is debug else ""),
            key='dev_session_index')
        selected = available[session_index]
        if selected.audits:
            run_index = st.selectbox(
                '运行记录', range(len(selected.audits)), index=len(selected.audits) - 1,
                format_func=lambda n: f"{n + 1:02} · {selected.audits[n].get('trace_id') or '未记录 Trace ID'}"
                                      f" · {MODE_LABELS[_run_mode(selected, selected.audits[n], sessions, debug)]}",
                key='dev_run_index')
            audit = selected.audits[run_index]
            mode = _run_mode(selected, audit, sessions, debug)

    from web.developer_config import editor,historical
    with st.expander('实时配置 · Baseline / Developer Override',expanded=True):
        editor(selected)
        historical(selected,audit)
    from web.train_data import settings as train_data_settings
    train_data_settings(selected)
    narrow = st.checkbox('纵向布局（窄屏）')
    left, middle, right = [st.container() for _ in range(3)] if narrow else st.columns([1.1, 1.35, 1.15], gap='medium')
    selected_event = None
    run_id = (audit or {}).get('trace_id')
    events = []

    with left, st.container(height=700, key='design_panel'):
        st.subheader('这次运行的配置')
        st.caption('提示词、工具 Schema 与权限规则来自当前源码；是否在本轮生效取决于运行模式与工具集，未逐条验证。')
        configuration_page([selected] if selected else [], compact=True)

    with middle, st.container(height=700, key='workflow_panel'):
        st.subheader('这次运行的事件')
        if not audit:
            st.caption('还没有选中运行。在右侧执行一次独立调试，或在用户端发送一条消息。')
        else:
            st.markdown(_run_identity(selected, audit, mode), unsafe_allow_html=True)
            events, meta = load_events(selected.trace_dir, run_id,selected.sid)
            nodes = events or workflow_rows(audit)
            if events:
                st.caption(f"{len(events)} 个已记录事件 · 只显示 run_id = {run_id} 的行")
            else:
                st.caption(f"该运行没有事件文件（{run_id}）；以下节点来自保存的审计旁证，不是同一次运行的事件流。")
            if audit.get('timestamp'):
                st.caption('运行时间：' + str(audit.get('timestamp')))
            select_key = 'selected_event_' + str(run_id)
            chosen = st.session_state.get(select_key, 0)
            if nodes:
                chosen = min(max(int(chosen or 0), 0), len(nodes) - 1)
            with st.container(key='workflow_nodes'):
                for index, node in enumerate(nodes):
                    label = event_headline(node) if events else f"{node.get('type', '节点')} · {node.get('status', '未记录')}"
                    if st.button(f'{index + 1:02}  {label}', key=select_key + '_' + str(index),
                                 type='primary' if index == chosen else 'secondary', width='stretch'):
                        st.session_state[select_key] = index
                        st.rerun()
            if nodes:
                selected_event = nodes[chosen]
            st.caption('点击节点在右栏查看证据。工具执行成功不等于整个业务成功。')

    with right, st.container(height=700, key='evidence_panel'):
        st.subheader('这次运行的证据')
        if audit:
            st.markdown(_run_identity(selected, audit, mode), unsafe_allow_html=True)
            if selected_event:
                st.markdown('**选中事件**')
                st.markdown(event_card(selected_event), unsafe_allow_html=True)
                with st.expander('原始事件 JSON（请求 / 响应 / 审计字段）', expanded=False):
                    with st.container(key='selected_evidence'):
                        st.json(sanitize(selected_event), expanded=False)
            _tool_evidence(selected, audit, events)
            with st.expander('政策引用与检索证据'):
                rows = policy_evidence(audit, _results_for(selected, audit))
                if not rows:
                    st.info('本次运行没有可关联的检索证据；不生成政策来源。')
                for row in rows:
                    st.json(row)
            with st.expander('自动判断与测试关联'):
                judgement = audit.get('judgement') or {}
                assertions = judgement.get('assertions') or []
                if not assertions:
                    st.caption('本次运行没有记录自动断言；未验证不等于通过。')
                for row in assertions:
                    if isinstance(row, dict):
                        st.caption(('✅' if row.get('passed') is True else '❌' if row.get('passed') is False else '·')
                                   + ' ' + str(row.get('assertion')) + ' · '
                                   + ('通过' if row.get('passed') is True else '未通过' if row.get('passed') is False else '未记录'))
                verdict = judgement.get('quality_verdict')
                st.caption('自动判断整体：' + (str(verdict) if verdict else '未记录') + '；不代表 B 正式测试成绩。')
                for event in (audit.get('mutation_events') or []):
                    if isinstance(event, dict) and event.get('status') != 'disabled':
                        st.caption('变异 ' + str(event.get('mutation_name') or event.get('mutation_id'))
                                   + ' · ' + str(event.get('status')))
            with st.expander('完整审计旁证'):
                st.json(sanitize(audit), expanded=False)
            # 用户端仅显示政策原文；完整检索与追问诊断在同一运行下只读展示。
            from web.conversation import _turn_policy, _policy_panel, _followup_lifecycle_panel
            public = audit.get('public_trace')
            if isinstance(public, dict):
                with st.expander('政策与追问诊断（原始记录）', expanded=False):
                    _policy_panel(_turn_policy(selected, public), technical=True)
                    saved = selected.followups_for(public)
                    if saved:
                        st.json(sanitize(saved), expanded=False)
                    st.json(sanitize(audit.get('error')), expanded=False)
            _followup_lifecycle_panel(selected, events)
        else:
            st.caption('还没有可回放的运行；先在下面执行一次独立调试，或在用户端发送一条消息。')
        st.divider()
        st.subheader('独立调试（独立运行）')
        st.caption('这里固定使用独立的 Legacy Mock 会话，不发真实 API 请求。执行后会生成本会话自己的运行 ID，'
                   '并自动切换为选中状态；它不会混入上方任何一次回放的事件。')
        with st.form('developer_debug_form'):
            message = st.text_input('调试消息', value='查明天上海到杭州的高铁二等座')
            submit = st.form_submit_button('执行离线调试')
        if submit:
            from web.runtime import Conversation
            if debug is None:
                debug = Conversation('lab', engine='legacy', live=False)
                st.session_state['developer_debug'] = debug
            try:
                status = st.empty()
                with st.spinner('正在执行离线 Agent…'):
                    debug.send(message, uuid.uuid4().hex,
                               event_callback=lambda event: status.markdown(processing_event(event),
                                                                            unsafe_allow_html=True))
                st.session_state['dev_focus'] = (debug.sid, None)
                st.rerun()
            except Exception:
                st.error('执行未完成，请查看异常旁证；没有自动重试。')

    # LangSmith management belongs to the developer workspace, not the user chat.
    from web.langsmith_panel import render as langsmith_panel
    langsmith_panel(selected, audit)


def _run_bar(available, debug):
    """One explicit place that says which run the three panes belong to."""
    total = sum(len(getattr(s, 'audits', [])) for s in available)
    st.markdown(
        '<div class="ta-runbar"><div><b>运行选择</b><span>三栏始终对应同一次运行；'
        '不同 run_id 的事件不会混在一起。</span></div>'
        f'<div class="ta-runbar-meta">{len(available)} 个会话 · {total} 次运行'
        f'{" · 1 个独立调试会话" if debug is not None else ""}</div></div>',
        unsafe_allow_html=True)


def _run_identity(session, audit, mode):
    run_id = escape(audit.get('trace_id') or '未记录 Trace ID')
    sid = escape(getattr(session, 'sid', '未记录会话'))
    events_note = '事件文件可读' if (session.trace_dir / 'run_events.jsonl').is_file() else '无事件文件'
    return (f'<div class="ta-run-id">{_mode_chip(mode)}'
            f'<code>{run_id}</code><span>{sid} · {events_note}</span></div>')


def _results_for(session, audit):
    public = audit.get('public_trace') or {}
    for index, record in enumerate(session.history):
        if record == public:
            return session.results[index]
    return session.results[-1] if session.results else []


def _tool_evidence(session, audit, events):
    public = audit.get('public_trace') or {}
    with st.expander('本轮输入与工具参数 / 结果', expanded=False):
        st.write('用户输入：', public.get('user_msg', '未记录'))
        st.write('结束原因：', public.get('finish_reason', '未记录'))
        rows = call_rows(events) if events else []
        if rows:
            st.markdown('**已记录的工具调用**')
            for row in rows:
                st.caption(f"{row['label']} · {row['status_text']} · {row['duration']}")
        else:
            st.caption('没有可读的工具事件；以下来自保存的执行结果，未推断执行状态。')
        results = _results_for(session, audit)
        if results:
            for result in results:
                st.json(sanitize(result), expanded=False)
        else:
            st.caption('本次运行没有保存工具结果。')
