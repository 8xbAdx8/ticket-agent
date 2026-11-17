"""C workbench page entry points. The application owns their navigation."""
import json
import os
import re

import streamlit as st

from target.scenario_workbench import (
    LiveWorkbenchModel, RUN_ROOT, STAGED_MAX_HTTP, Workbench, _run_case, export_bundle, load_run_results, read_manifest, run_directory,
)
from target.scenario_abc_budget import BATCH_ROOT, R2_ROOT
from target.api_config import status as api_status
from web import scenario_inspection, trace_inspection, workbench_explain
from web.design import empty, escape, header, kpis, table
from web.workbench_config import WORKBENCH_PAGES
from web.workbench_evidence_view import approved_case_ids, case_evidence, render_execution, render_metrics, render_plan, styles

POINTER = 'c_workbench_pointer'
WAITING = '请先在「AI 场景总测试」完成一次 AI 测试。'
TITLES = WORKBENCH_PAGES
LABEL = {'passed': '通过', 'failed': '失败', 'indeterminate': '无法判定', 'not_run': '未执行',
         'WAITING': '等待', 'RUNNING': '进行中', 'COMPLETED': '已完成', 'FAILED': '失败',
         'AWAITING_REVIEW': '待人工审核', 'APPROVED': '已人工批准'}
TOPICS = {
    'RAG': ('RAG 检索质量', '用例要求检索政策、核对条款或验证引用时，这里会汇总该类执行。',
            '查询超过 48 小时退票手续费，并引用条款编号。'),
    '多轮': ('多轮对话质量', '用例需要连续输入，并检查后续步骤是否沿用前序已给定的条件。',
            '先查广州到深圳的车次，再看下一页并比较两班车。'),
    '安全': ('对抗性与安全测试', '用例需要验证越权请求、未确认交易或异常诱导能否被拦截。',
            '未确认就要求直接支付，核对是否有订单或交易写入。'),
}
BOUNDARY_EXAMPLES = {
    '输入不完整': '缺少日期或站点时，检查是否先澄清。',
    '超长上下文': '上下文很长时，检查场景前面给定的查询条件是否仍被保留。',
    '工具异常返回': '工具异常后，检查回复是否忠实于失败回执。',
    '并发与重复': '重复提交同一请求时，检查隔离库是否出现重复订单。',
    '状态冲突': '订单状态与操作条件冲突时，检查系统是否阻止写入。',
}


def _acceptance_root():
    return R2_ROOT if st.query_params.get('abc_batch') == 'r2' else BATCH_ROOT


def _accepted_source():
    if os.getenv('TICKET_ABC_ACCEPTANCE_UI') != '1':
        return None
    try:
        root = _acceptance_root()
        source = json.loads((root/'source.json').read_text(encoding='utf8'))
        if (source['session_id'] != st.query_params.get('session_id')
                or not re.fullmatch(r'pilot-source-[0-9a-f]{32}', source['directory'])):
            return None
        from web.session_store import restore_session
        if root == R2_ROOT and source.get('source_area') != BATCH_ROOT.name:
            return None
        return restore_session(BATCH_ROOT/source['directory'], expected_sid=source['session_id'])
    except (OSError, ValueError, KeyError, TypeError):
        return None


STANDALONE_SID = 'agent-scenarios'


def _standalone_session():
    """The workbench tests the Agent as a whole; no user conversation is needed.

    A deliberately minimal session object keeps the sealed evidence chain
    (sid / engine / standalone flag) intact without replaying or fabricating a
    dialogue.  Acceptance replays still resolve their own real session through
    the query-parameter path below.
    """
    from types import SimpleNamespace
    session = st.session_state.get('c_standalone_session')
    if session is None:
        session = SimpleNamespace(
            sid=STANDALONE_SID, mode='user', engine='legacy', live=False,
            live_provider=None, read_only=False, history=[], audits=[], results=[],
            business_receipts=[], trace_dir=None, workbench_source='standalone',
            standalone_scenarios=True)
        st.session_state['c_standalone_session'] = session
    return session


def _user_session(sessions=()):
    if not st.query_params.get('session_id'):
        return _standalone_session()
    sessions = st.session_state.get('user_sessions', sessions)
    requested = st.query_params.get('session_id')
    selected = st.session_state.get('c_source_session')
    if requested:
        source = _accepted_source()
        if source is not None:
            return source
        extra = [*st.session_state.get('lab_archives', []), st.session_state.get('lab_session'),
                 st.session_state.get('developer_debug')]
        if selected is not None and selected.mode == 'lab' and selected.sid == requested:
            if any(item is selected for item in extra):
                return selected
        from web.session_links import get_testable_sessions
        owned = next((item for item in sessions if item.sid == requested), None)
        if owned is not None:
            return owned
        return next(iter(get_testable_sessions([], requested, st.query_params.get('source','user'))), None)
    index = st.session_state.get('user_active_session_index', 0)
    if type(index) is int and 0 <= index < len(sessions):
        session = sessions[index]
        if getattr(session, 'mode', None) == 'user':
            return session
    source = _accepted_source()
    if source is not None:
        return source
    return None


def _source_workspace(session):
    if session is st.session_state.get('developer_debug'):
        return 'developer'
    return getattr(session,'workbench_source','lab' if session.mode == 'lab' else 'user')


def _select_source(sid):
    if st.query_params.get('session_id') != sid:
        st.query_params['session_id'] = sid
        st.query_params.pop('abc_run', None)
        st.query_params.pop('abc_batch', None)
        st.query_params.pop('resume', None)
        st.session_state.pop(POINTER, None)


def _source_selector(sessions, box=None):
    from target.scenario_workbench_evidence import snapshot_conversation
    from web.session_links import get_testable_sessions
    requested = st.query_params.get('session_id')
    sources = [*sessions, *st.session_state.get('lab_archives', []),
               st.session_state.get('lab_session'), st.session_state.get('developer_debug')]
    available = get_testable_sessions([item for item in sources if item is not None], requested,
                                      st.query_params.get('source','user'))
    acceptance = _accepted_source()
    if acceptance is not None:
        available.append(acceptance)
    by_sid = {item.sid: item for item in available if item.history}
    if not by_sid:
        return None
    focus = st.session_state.pop('c_source_focus', None) or requested
    if focus not in by_sid:
        current = _user_session(sessions)
        focus = current.sid if current and current.sid in by_sid else next(iter(by_sid))
    st.session_state['c_source_pick'] = focus
    def select():
        _select_source(st.session_state['c_source_pick'])
    sid = (box or st).selectbox('来源会话', list(by_sid), key='c_source_pick', on_change=select,
                       format_func=lambda key: f"{_source_workspace(by_sid[key])} · {key} · "
                                               f"{'Live' if by_sid[key].live else 'Mock'}")
    _select_source(sid)
    session = by_sid[sid]
    session.workbench_source = _source_workspace(session)
    if st.query_params.get('source') != session.workbench_source:
        st.query_params['source'] = session.workbench_source
    st.session_state['c_source_session'] = session
    snapshot = snapshot_conversation(session)
    st.session_state['c_source_snapshot'] = snapshot
    turns = snapshot['turns']
    # Demo layout: the whole conversation is the test input.  Scope radios,
    # return-to-client buttons and raw-JSON expanders belong to the low-level
    # evidence drawer, not to the single configuration block judges see.
    st.session_state['c_turn_ids'] = None
    st.session_state['c_source_has_trace'] = any(
        row['execution_evidence'] == 'available' for row in turns)
    return session


def _new_source_run(session, *, replace_interrupted=False):
    return Workbench.start(session.sid, replace_interrupted=replace_interrupted)


def _run_root(run_id):
    pointer = st.session_state.get(POINTER, {})
    if pointer.get('run_id') == run_id and pointer.get('acceptance') is True:
        return (R2_ROOT if pointer.get('batch') == 'r2' else BATCH_ROOT)/'generated-cases'
    return RUN_ROOT


def current_test_run(sessions=()):
    session = _user_session(sessions)
    pointer = st.session_state.get(POINTER, {})
    requested = st.query_params.get('abc_run')
    if (session and requested and (not pointer or pointer.get('run_id') != requested)
            and st.query_params.get('session_id') == session.sid):
        acceptance = os.getenv('TICKET_ABC_ACCEPTANCE_UI') == '1' and _accepted_source() is not None
        root = _acceptance_root()/'generated-cases' if acceptance else RUN_ROOT
        run = read_manifest(requested, session.sid, root=root)
        st.session_state[POINTER] = {'run_id': requested, 'session_id': session.sid, 'acceptance': acceptance,
                                     'batch': st.query_params.get('abc_batch') if acceptance else None}
        return run
    if session is None:
        return None
    if not requested and pointer.get('session_id') != session.sid:
        latest = Workbench.latest(session.sid)
        if latest:
            return read_manifest(latest, session.sid)
    if pointer.get('session_id') != session.sid:
        return None
    return read_manifest(pointer['run_id'], session.sid, root=_run_root(pointer['run_id']))


def _current(sessions=(), *, completed=True):
    try:
        run = current_test_run(sessions)
        if run and (not completed or run['status'] == 'COMPLETED'):
            return load_run_results(run['run_id'], run['session_id'], root=_run_root(run['run_id'])) if completed else run
    except (KeyError, ValueError, OSError):
        st.error('当前运行证据缺失或完整性校验未通过。')
    return None


def _inspection_context(sessions=()):
    """Real conversation evidence + this run's sealed result, for every board.

    A judge who just walked through one ticket purchase must see detailed
    inspection rows even when no AI test run exists yet, so the snapshot is
    rebuilt from the live session when the workbench pointer is empty.
    """
    snapshot = st.session_state.get('c_source_snapshot')
    if not snapshot:
        session = _user_session(sessions)
        if session is not None:
            try:
                from target.scenario_workbench_evidence import snapshot_conversation
                snapshot = snapshot_conversation(session)
            except (ValueError, OSError, TypeError, KeyError):
                snapshot = None
    run = current_test_run(sessions)
    summary = _current(sessions) if run and run['status'] == 'COMPLETED' else None
    directory = run_directory(run['run_id'], _run_root(run['run_id'])) if run else None
    return snapshot, summary, directory


def _show(title, note):
    styles()
    header(title, note, badge='测试控制台')


def _rate(stat):
    return '未取得样本' if stat['value'] is None else f"{stat['value']:.1%} · {stat['numerator']}/{stat['denominator']}"


def _status(value):
    return LABEL.get(value, value)


def _model_source(run):
    source = run.get('model_source')
    return {'deterministic_model_fixture': 'Mock 离线',
            'live_model': 'Live 模型',
            'r2_live_model': 'Live Agent 验收'}.get(source, source or '等待生成')


def _numbers(summary):
    normal = summary['normal_quality']
    render_metrics([('客观断言 · 通过 / 已执行常规', _rate(normal['objective_rate'])),
                    ('AI 评判 · 通过 / 可判定常规', _rate(normal['judge_rate'])),
                    ('链路覆盖 · 已覆盖 / 42 个单元', _rate(summary['coverage_rate'])),
                    ('证据完整 · 完整 / 全部生成', _rate(summary['evidence_rate']))])
    if missing_refs := summary.get('judge_missing_evidence_refs'):
        st.warning(f'{missing_refs} 条 AI 评判缺少证据引用，记为无法判定。已保留客观断言和执行记录。')


def _run_approval(run, directory):
    try:
        return approved_case_ids(directory, run)
    except (OSError, ValueError, KeyError, TypeError):
        st.warning('人工批准凭据暂不可核验。')
        return None


def _open_workbench(page, dimension=None, lab_section=None):
    st.session_state['workspace_page'] = page
    if dimension is not None:
        st.session_state['c_gap_focus'] = dimension
    if lab_section is not None:
        st.session_state['c_lab_section'] = lab_section


def _guide_actions(key, dimension=None, *, has_summary=False):
    st.button('前往 AI 场景总测试', key=f'{key}_scenarios', on_click=_open_workbench, args=(TITLES[0],))
    if has_summary:
        label = f'查看{dimension}缺口' if dimension else '查看质量分析中的缺口'
        st.button(label, key=f'{key}_gaps', on_click=_open_workbench, args=(TITLES[1], dimension))


def _review_cases(run):
    if not run or run['status'] not in ('AWAITING_REVIEW', 'APPROVED'):
        return []
    try:
        workbench = Workbench.reopen(run['run_id'], run['session_id'], root=_run_root(run['run_id']))
        workbench.review_candidates()  # verifies the sealed review inputs, including cases.jsonl
        return [json.loads(line) for line in (workbench.directory/'cases.jsonl').read_text(encoding='utf8').splitlines()]
    except (OSError, ValueError, KeyError, TypeError):
        st.warning('当前候选证据无法核验。')
        return []


def _topic_status(cases, dimension, run):
    selected = [case for case in cases if case.get('dimension') == dimension]
    if not selected:
        return '当前没有可汇总的测试运行。' if run is None else (
            '本轮没有生成该维度用例。' if run['status'] == 'COMPLETED' else
            '本轮没有可核验的该维度候选。')
    eligible = sum(row['validated'] for row in selected)
    executed = sum(row.get('executed', False) for row in selected)
    if executed:
        return f'本轮已执行 {executed} 条。'
    if eligible:
        return f'本轮有 {eligible} 条通过校验的候选，尚未执行。'
    return f'本轮生成了 {len(selected)} 条候选，均未通过校验。'


def _stage_text(run):
    return '\n'.join(['| 阶段 | 状态 | 耗时 | 证据 |', '| --- | --- | --- | --- |'] + [
        f"| {step['name']} | {_status(step['status'])} | {step['duration_ms'] if step['duration_ms'] is not None else '—'} ms | "
        f"{'、'.join(step['evidence']) or '—'} |" for step in run['stages']])


def _progress(container, run):
    with container.container():
        stages = run['stages']
        active = next((row for row in stages if row['status'] in ('RUNNING', 'FAILED')), None)
        st.progress(sum(row['status'] == 'COMPLETED' for row in stages) / len(stages),
                    text=f"{active['name']} · {_status(active['status'])}" if active else _status(run['status']))
        if active and active['error']:
            details = active.get('error_details') or {}
            category = details.get('category')
            descriptions = {
                'request_payload_limit':'评判证据超过本地请求大小限制',
                'authentication_failed':'模型服务未通过身份验证',
                'permission_denied':'模型服务拒绝访问',
                'insufficient_balance':'模型服务额度不足',
                'rate_limited':'模型服务暂时限流',
                'server_error':'模型服务暂时异常',
                'service_unavailable':'模型服务暂不可用',
                'timeout':'等待模型响应超时',
                'network_connection':'无法连接到模型服务',
                'empty_response':'模型返回空内容',
                'invalid_json':'模型未返回合法 JSON',
                'invalid_response':'模型返回内容无法读取',
                'invalid_judge_structure':'评判结果缺少必要字段或字段类型有误',
            }
            if category:
                status = details.get('http_status')
                code = f' · HTTP {status}' if type(status) is int else ''
                st.error(f"{active['name']}未完成 · {descriptions.get(category,'模型请求未能完成')}{code}")
                st.caption('错误类别：'+(category if category in descriptions else 'other')+'。未自动重试。')
            elif active['name'] == 'AI 评判' and active['error']=='DeepSeekError':
                st.error('AI 评判未完成 · 历史记录未保存具体错误类别。')
            elif active['error'] == 'C_WORKBENCH_NO_EXECUTABLE_CASES':
                st.error('生成的候选均未通过校验。展开「生成校验明细」可查看每条原因。')
            elif active['error'] == 'C_WORKBENCH_NO_SEMANTICALLY_ELIGIBLE_CASES':
                st.error('这是一条修复前的历史失败运行：当时语义评审只要把候选全部判为「需修改」，整轮就会停在这里。'
                         '当前版本已改为按确定性质量门保留候选并记下评审意见；点上方「开始本轮测试」新建一轮即可跑完。')
            elif active['error'] in ('C_WORKBENCH_GENERATION_INVALID_JSON','C_WORKBENCH_INVALID_GENERATION',
                                    'C_WORKBENCH_EMPTY_GENERATION','C_WORKBENCH_TRUNCATED_GENERATION'):
                st.error('模型返回的用例不完整或格式不正确，无法进入人工审核。')
            elif active['error'] == 'C_WORKBENCH_PROVIDER_NOT_CONFIGURED':
                st.error('所选模型未配置 API Key；请在项目 .env 设置 DEEPSEEK_API_KEY / DASHSCOPE_API_KEY，或改选已配置的模型。')
            elif active['error'] == 'C_WORKBENCH_OFFLINE_ONLY':
                st.error('当前是离线评审模式，不能调用在线模型；请改用 Mock，或用在线模式启动后再选 Live。')
            else:
                st.error(f"{active['name']}未完成（{active['error']}）。")
            completed = [step['name'] for step in stages if step['status']=='COMPLETED']
            if completed:
                st.caption('已完成并保留：'+'、'.join(completed)+'。')


def _evidence(summary, board, *, dimension=None):
    directory = run_directory(summary['run_id'], _run_root(summary['run_id']))
    cases = [row for row in summary['cases'] if dimension is None or row['dimension'] == dimension]
    if not cases:
        return
    table(scenario_inspection.case_rows_for(cases, directory),
          'c_case_table_' + board, search=False, chrome=False)
    workbench_explain.guide_note(
        '这张表一行就是一个 AI 从零设计的测试场景：为什么测、模拟了什么风险、'
        '喂给 Agent 的输入、期望达标信号、Agent 实际调用的工具、断言命中、'
        '订单写入、耗时、判定依据与结论。没跑过的行如实写「未执行」，不拿示例数据补空。',
        label='这张表怎么看')
    lookup = {case['case_id']: case for case in cases}
    selected = st.selectbox('查看用例证据', lookup,
                            format_func=lambda key: f"{key} · {lookup[key]['title']}", key=f'c_case_{board}')
    case = lookup[selected]
    try:
        execution, judge = case_evidence(directory, case)
        candidates = (directory / 'cases.jsonl').read_text(encoding='utf8').splitlines()
        source = next(row for row in map(json.loads, candidates) if row['case_id'] == selected)
        plan_path = directory / 'review-plans.json'
        plans = json.loads(plan_path.read_text(encoding='utf8')) if plan_path.is_file() else []
        plan = next((plan for candidate, plan in plans if candidate['case_id'] == selected), None)
    except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration):
        st.warning('无法读取与该用例匹配的证据。')
        return
    with st.expander('用例目标与预期'):
        render_plan(source, plan)
    with st.expander('客观断言、AI 判定与证据'):
        if case['objective_status'] == 'not_run':
            st.caption('本用例尚未执行。')
        else:
            st.text(f"客观断言 · {_status(case['objective_status'])}")
        render_execution(execution, judge, dimension=case['dimension'], status=_status, candidate=source)
        if execution:
            st.download_button('下载原始执行证据', (directory / case['execution_ref']).read_bytes(),
                               file_name=f'{selected}.json', mime='application/json', key=f'c_exec_file_{board}_{selected}')
    execution_id = (execution or {}).get('execution_id')
    if (isinstance(execution_id, str) and re.fullmatch(r'[0-9a-f]{32}', execution_id)
            and _run_root(summary['run_id']) != RUN_ROOT
            and st.checkbox('查看执行 Trace', key=f'abc_execution_trace_{board}_{selected}')):
        from web.evidence import read_audit_records
        from web.trace_view import show_record
        area = _run_root(summary['run_id']).parent
        audit_path = area/('agent-executions' if area == R2_ROOT else 'cases')/execution_id/'conversation/traces/audit_runs.jsonl'
        records, _ = read_audit_records(audit_path)
        wanted = {row['trace_id'] for row in execution['steps']}
        for audit in records:
            if audit.get('trace_id') in wanted and audit.get('public_trace', {}).get('session_id') == execution.get('subject_session_id'):
                show_record(audit, key='abc_'+board+'_'+audit['trace_id'])


def _auto_continue_run(session, run):
    """Demo mode: no human review UI; approve validated candidates and continue."""
    key = 'c_auto_approved_' + run['run_id']
    if st.session_state.get(key):
        return False
    try:
        workbench = Workbench.reopen(run['run_id'], session.sid, root=_run_root(run['run_id']))
        options = workbench.review_candidates()
        case_ids = [case['case_id'] for case, _ in options]
        if not case_ids:
            st.session_state[key] = True
            return False
        model, judge, runner = _run_models(run)
        if run['status'] == 'AWAITING_REVIEW':
            workbench.approve(case_ids, model, actor='human')
        workbench.submit_approved(judge or model, runner=runner)
        st.session_state[key] = True
        return True
    except (OSError, ValueError, TypeError, KeyError):
        st.session_state[key] = True
        return False


def competition_page(sessions):
    _show(TITLES[0], 'AI 直接生成针对 Agent 的测试场景、隔离执行并自动判定；不需要先跑一段对话。这一轮结果是后面四个板块的唯一来源。')
    workbench_explain.render(TITLES[0])
    # ① One single block: mode, start button, progress.  The old "选择来源对话"
    # picker is gone by design: the test probes the Agent, not a conversation.
    with st.container(border=True, key='workbench_source'):
        st.subheader('① 本轮测试')
        session = _user_session(sessions)
        from target.scenario_workbench_evidence import standalone_snapshot
        st.session_state['c_source_snapshot'] = standalone_snapshot(
            session.sid, getattr(session, 'engine', 'legacy'))
        st.session_state['c_source_has_trace'] = True
        run = _current(sessions, completed=False)
        offline = os.getenv('TICKET_WEB_OFFLINE_ONLY') == '1'
        model_box = st.container(border=True, key='workbench_pick_model')
        model_box.markdown('**② 生成与评估设置**')
        mode = model_box.radio('本轮生成与评估模式', ['Mock'] if offline else ['Mock', 'Live'], horizontal=True)
        names = {'deepseek': 'DeepSeek', 'bailian': 'Qwen（百炼）'}
        provider = judge = None
        if mode == 'Live':
            configured = [p for p in names if api_status(p).get('configured')]
            default_provider = configured[0] if configured else 'deepseek'
            provider = model_box.selectbox('候选生成模型', list(names), index=list(names).index(default_provider),
                                           format_func=lambda p: names[p] + ('（已配置）' if api_status(p).get('configured') else '（未配置）'),
                                           key='c_workbench_provider')
            judge_options = [p for p in names if p != provider] or [provider]
            configured_judges = [p for p in judge_options if api_status(p).get('configured')]
            default_judge = configured_judges[0] if configured_judges else judge_options[0]
            judge = model_box.selectbox('语义评分与执行评判模型', judge_options,
                                        index=judge_options.index(default_judge),
                                        format_func=lambda p: names[p] + ('（已配置）' if api_status(p).get('configured') else '（未配置）'),
                                        key='c_workbench_judge_'+provider)
            if not configured:
                model_box.warning('当前没有检测到已配置的模型 Key；Live 模式无法生成，请在项目 .env 配置后重启应用。')
        request_limit = STAGED_MAX_HTTP
        if mode == 'Live':
            request_limit = st.number_input('本轮最多发起多少次模型请求',
                                            min_value=1, max_value=300, value=40, step=1,
                                            key='c_workbench_request_limit',
                                            help='Live 一次生成约 14 条场景，再逐条复核与评判，'
                                                 '完整一轮约 30 次请求')
            model_box.caption('填写次数并点击开始，即授权本轮按此上限调用所选模型；用满即停，不会超支。'
                              'Live 一次生成约 14 条（七维度各 2 条），再逐条复核与评判，'
                              '约 30 次请求、3–5 分钟。')
        authorized = mode == 'Live'
        acceptance = bool(run and _run_root(run['run_id']) != RUN_ROOT)
        busy = bool(run and run['status'] in ('WAITING', 'RUNNING', 'AWAITING_REVIEW', 'APPROVED'))
        replace = False
        if busy and run['status'] in ('WAITING', 'RUNNING'):
            if Workbench.interrupted(run):
                st.warning('服务重启前的运行结果未知。请先核对原 Trace、回执和请求账本。')
                replace = st.checkbox('已核对原运行，另建新运行', key='c_replace_'+run['run_id'])
            else:
                st.info('此运行尚无终态。请刷新核对原运行，系统不会重发请求。')
        clicked = st.button('开始本轮测试', type='primary', key='c_workbench_start',
                            disabled=acceptance or (busy and not replace))
        progress = st.empty()
        if run:
            _progress(progress, run)
    if clicked:
        try:
            workbench = _new_source_run(session, replace_interrupted=replace)
        except ValueError:
            st.warning('此来源已有待处理的运行。请刷新页面让它自动续跑，或重新读取该运行。')
            return
        st.session_state[POINTER] = {'run_id': workbench.run_id, 'session_id': session.sid}
        # No session_id query parameter: the standalone run is located by the
        # pointer plus Workbench.latest(sid).  Setting a session_id here would
        # send _user_session back down the "resolve a real conversation" path.
        if mode == 'Live':
            model = LiveWorkbenchModel(provider, authorized=authorized, request_limit=request_limit)
            reviewer = LiveWorkbenchModel(judge, authorized=authorized, request_limit=request_limit)
        else:
            from target.scenario_workbench_fixture import MockWorkbenchModel
            model, reviewer = MockWorkbenchModel(), None
        # Demo period: no human review.  Mock finishes in one pass; Live is
        # required by the backend to keep an approval record, which the page
        # writes automatically below.
        workbench.submit(workbench.execute, session, model, reviewer=reviewer,
                         review_required=(mode == 'Live'),
                         source_workspace=_source_workspace(session),
                         source_turn_ids=st.session_state.get('c_turn_ids'))
        st.rerun()
    if run:
        @st.fragment(run_every=1 if run['status'] in ('WAITING', 'RUNNING', 'APPROVED') else None)
        def watch():
            current = read_manifest(run['run_id'], session.sid, root=_run_root(run['run_id']))
            if current != run:
                st.rerun()
        watch()
        if run['status'] in ('AWAITING_REVIEW', 'APPROVED') and run.get('model_source') != 'r2_live_model':
            if _auto_continue_run(session, run):
                st.rerun()
        if run['status']=='FAILED' and run['stages'][3]['status']=='FAILED' and not acceptance:
            workbench = Workbench.reopen(run['run_id'], session.sid, root=RUN_ROOT)
            if workbench.judge_recovery_available():
                st.info('可从已有结果恢复 AI 评判。仅向原模型发送尚未完成的评判请求，可能产生新费用。')
                consent = st.checkbox('授权本次恢复评判可能产生的模型费用', key='judge_recovery_consent_'+run['run_id'],
                                      disabled=offline)
                if st.button('仅恢复 AI 评判', key='judge_recovery_'+run['run_id'], disabled=offline or not consent):
                    try:
                        workbench.recover_judge(LiveWorkbenchModel(run.get('judge_provider') or run['provider'], authorized=consent,
                                                request_limit=run.get('request_limit', 8)),
                                                progress=lambda manifest: _progress(progress, manifest))
                    except (OSError, ValueError, KeyError, TypeError):
                        st.warning('无法恢复：请核对运行证据和剩余请求额度。未启动场景生成或执行。')
                    else:
                        st.rerun()
        if run['status'] == 'APPROVED' and run.get('model_source') == 'r2_live_model':
            from web.scenario_r2_desk import business_desk
            business_desk(session, run, progress, offline, _progress)
        if run['status'] == 'FAILED' and run.get('model_source') == 'r2_live_model':
            qa_path = run_directory(run['run_id'], _run_root(run['run_id']))/'cases.jsonl'
            if qa_path.is_file():
                with st.expander('QA-09 拒绝详情', expanded=True):
                    for line in qa_path.read_text(encoding='utf8').splitlines():
                        row = json.loads(line)
                        st.write(row['case_id'] + ' · ' + '、'.join(row['errors']))
        if run['status'] == 'COMPLETED':
            with st.expander('按覆盖缺口生成补充用例', expanded=False):
                _gap_generation(run, session)
    summary = _current(sessions)
    if not summary:
        return
    directory = run_directory(summary['run_id'], _run_root(summary['run_id']))
    snapshot = st.session_state.get('c_source_snapshot')

    # 点 1 · 本轮 AI 生成参数：先依据，再生成场景，再逐条可展开比对。
    st.subheader('② 本轮 AI 生成参数')
    workbench_explain.render_generation_basis(session, snapshot, summary)
    st.markdown('**本轮 AI 生成的测试场景**')
    scenario_inspection.render_scenario_table(snapshot, summary, directory, key='c_gen_scenarios')
    st.markdown('**逐条展开 · 期望 / 实际 / 判定依据**')
    scenario_inspection.render_scenario_cards(snapshot, summary, directory, key='c_gen_cards')

    # 点 2 · 本轮测试情况：关键数字 + 七维度覆盖矩阵 + 103 条基线用例。
    st.subheader('③ 本轮测试情况')
    workbench_explain.render_score_matrix(summary, directory)
    st.markdown('### 103 条基线用例 · 逐条结果（历史批次 2026-10-20）')
    from web.quality_board import render_baseline_cases
    render_baseline_cases()

    # 点 4 · 判断依据：核心展示卡 + 保留可展开的逐条判断依据。
    st.subheader('④ 判断依据')
    workbench_explain.render_judgement_guide(summary, directory)
    with st.expander('展开逐条判断依据', expanded=False):
        workbench_explain.render_verdict_table(summary)


def _source_evidence(run, session):
    directory = run_directory(run['run_id'], _run_root(run['run_id']))
    try:
        data = json.loads((directory / 'conversation.json').read_text(encoding='utf8'))
    except (OSError, ValueError):
        return
    if data.get('session_id') != session.sid:
        return
    if data.get('standalone'):
        with st.expander('本轮场景生成依据（独立场景测试 · 无来源对话）', expanded=False):
            st.caption('AI 从零设计测试场景，不读取任何用户对话。conversation.json 仅保留一个标注为 '
                       'standalone 的锚点轮次，用于满足 V3.10 场景契约，不是真实发生的对话。')
            prompt = directory / 'prompts/generate.json'
            if prompt.is_file():
                st.download_button('下载生成 Prompt',
                                   json.loads(prompt.read_text(encoding='utf8'))['prompt'],
                                   file_name='generation-prompt.txt',
                                   key='c_gen_prompt_standalone_' + run['run_id'])
        return
    turns = data['turns']
    with st.expander('本次对话来源与生成依据'):
        for turn in turns:
            st.text(f"{turn['turn_id']} · {turn.get('user') or '空输入'}")
            tools = list(dict.fromkeys(row['tool'] for row in turn.get('execution_events', [])
                                       if row.get('executed') is True and row.get('tool')))
            if tools:
                st.caption('已执行工具 · ' + '、'.join(tools))
            if turn.get('run_id'):
                st.caption('来源 Trace · ' + turn['run_id'])
        if (directory / 'prompts/generate.json').is_file():
            prompt = json.loads((directory / 'prompts/generate.json').read_text(encoding='utf8'))
            st.download_button('下载生成 Prompt', prompt['prompt'], file_name='generation-prompt.txt',
                               key='c_gen_prompt_'+run['run_id'])
        st.json(turns, expanded=False)
    owned_runs = {turn['run_id'] for turn in turns if turn.get('run_id')}
    records = [audit for audit in session.audits if audit.get('trace_id') in owned_runs
               and (audit.get('public_trace') or {}).get('session_id') == session.sid]
    if records and st.checkbox('查看来源 Trace', key=f"abc_source_trace_{run['run_id']}"):
        from web.trace_view import show_record
        for audit in records:
            show_record(audit, key='abc_source_'+audit['trace_id'])


def _generation_details(run):
    if run['stages'][1]['status'] not in ('COMPLETED','FAILED'):
        return
    directory = run_directory(run['run_id'], _run_root(run['run_id']))
    report = directory/'generation-diagnostics.json'
    candidates = directory/'cases.jsonl'
    if not report.is_file() and not candidates.is_file():
        return
    try:
        rows = [json.loads(line) for line in candidates.read_text(encoding='utf8').splitlines()] if candidates.is_file() else []
        data = json.loads(report.read_text(encoding='utf8')) if report.is_file() else {}
    except (OSError,ValueError):
        st.caption('生成校验明细暂不可读取。')
        return
    names = {'raw_candidates':'原始候选','parsed_candidates':'已解析','schema_valid':'结构校验通过',
             'executor_compatible':'执行器兼容','retained':'确定性质量门通过'}
    reasons = {'GAP_REFERENCE_NOT_SELECTED':'候选未关联到本次选择的缺口',
               'GAP_DIMENSION_MISMATCH':'候选维度与所选缺口不一致',
               'V310_EXPECT_MUST_BE_EMPTY_OBJECT':'断言写入了旧格式 expect，须写在步骤检查项中',
               'MUTATION_INVALID':'异常注入配置与测试维度不匹配',
               'AGENT_CHAT_REQUIRED_AND_NO_MODEL_CONFIRMATION':'缺少对话步骤，或包含不允许的操作',
               'TITLE_REQUIRED':'缺少用例名称','OBJECTIVE_REQUIRED':'缺少测试目标',
               'TOOL_STEP_INVALID':'工具名称或参数格式不合法'}
    with st.expander('生成校验明细', expanded=run['stages'][1]['status']=='FAILED'):
        counts = data.get('counts', {'raw_candidates':len(rows), 'retained':sum(bool(r.get('validated')) for r in rows)})
        st.write(' · '.join(f"{names[key]} {value if value is not None else '未知'}" for key,value in counts.items() if key in names))
        for row in rows:
            if not row['validated']:
                st.write(row['case_id'] + ' · ' + '；'.join(reasons.get(e.split(':',1)[0],e) for e in row['errors']))
        semantic = directory/'semantic-review.json'
        if semantic.is_file():
            try:
                scores = json.loads(semantic.read_text(encoding='utf8'))
            except (OSError, ValueError):
                st.caption('候选语义评分文件无法读取。')
            else:
                st.markdown('**候选语义评分**')
                st.caption(f"已完成 {sum(item['status']=='COMPLETE' for item in scores['results'])} 条 · "
                           f"建议接受 {sum(item.get('recommendation')=='accept' for item in scores['results'])} 条 · "
                           f"实际保留 {len(scores.get('retained_case_ids') or [])} 条")
                if scores.get('selection_policy') == 'no_accept_fallback_all_quality_gated':
                    st.caption('本轮评审未给出「建议接受」；按确定性质量门结果保留全部候选继续隔离执行。'
                               'AI 评分与修改建议原样留证，没有被改写或丢弃。')
                labels = {'accept': '建议接受', 'revise': '需修改', 'reject': '拒绝'}
                for item in scores['results']:
                    label = labels.get(item.get('recommendation'), '无法判定')
                    st.text(f"{item['case_id']} · {label} · {item['reason']}")
                st.json(scores, expanded=False)
        st.caption('人工审核：' + ('已有批准记录' if run.get('review_sha256') else '未批准'))
        st.caption('评判：' + LABEL.get(run['stages'][3]['status'], run['stages'][3]['status']))


def _run_models(run):
    if run['model_source'] == 'deterministic_model_fixture':
        from target.scenario_workbench_fixture import MockWorkbenchModel
        return MockWorkbenchModel(), None, _run_case
    if _run_root(run['run_id']) == RUN_ROOT:
        limit = run.get('request_limit', 8)
        model = LiveWorkbenchModel(run['provider'], authorized=True, request_limit=limit)
        judge = LiveWorkbenchModel(run.get('judge_provider') or run['provider'], authorized=True, request_limit=limit)
        return model, judge, _run_case
    from target.scenario_abc_live import PilotModel
    model = PilotModel(run['provider'])
    return model, None, model.runner


def _review_run(session, run, progress, offline):
    try:
        workbench = Workbench.reopen(run['run_id'], session.sid, root=_run_root(run['run_id']))
        options = workbench.review_candidates()
    except (OSError, ValueError, TypeError, KeyError):
        st.error('候选证据校验失败。')
        return
    st.subheader('审核候选')
    if run.get('gap_source'):
        st.caption(f"补充用例来源 · {run['gap_source']['run_id']} · 生成于 {run['started_at']}")
    st.caption('请检查测试目标、步骤和预期结果是否符合对话意图。批准所选用例后才会执行。')
    r2 = run['model_source'] == 'r2_live_model'
    if r2:
        receipts = [json.loads(path.read_text(encoding='utf8')) for path in (R2_ROOT/'qa09-results').glob(f"{run['provider']}*.json")]
        if not any(row.get('run_id') == run['run_id'] and row.get('quality') == 'PASS' and row.get('wire_prompt_verified') is True
                   for row in receipts):
            st.error('QA-09 或实际发送的 Prompt 证据未核验。')
            return
        st.caption('人工审核会记录候选哈希。后续 Agent 及交叉 Judge 将使用同一批次预算。')
    approved = []
    fixture = run['model_source'] == 'deterministic_model_fixture'
    if run['status'] == 'APPROVED':
        consent = fixture or st.checkbox('授权执行后的 AI 评判费用', disabled=offline,
                                         key='abc_resume_consent_'+run['run_id'])
        if st.button('执行已批准用例', key='abc_resume_'+run['run_id'], disabled=not consent or (offline and not fixture)):
            model, judge, runner = _run_models(run)
            try:
                workbench.submit_approved(judge or model, runner=runner)
            except (OSError, ValueError):
                st.error('已有执行记录或证据无法核验。请核对原运行，未重新执行。')
            else:
                st.rerun()
        return
    for case, plan in options:
        with st.expander(case['case_id'] + ' · ' + case['title'], expanded=True):
            st.caption(f"测试维度 · {case['dimension']}")
            if case.get('gap_reference'):
                st.caption(case['gap_reference']['gap_id'])
                st.caption('来源证据 · ' + '、'.join(case['gap_reference']['evidence_refs']))
            st.caption('测试目标、步骤与断言')
            render_plan(case, plan)
            if st.checkbox('批准此候选', key='abc_approve_'+run['run_id']+'_'+case['case_id']):
                approved.append(case['case_id'])
    if r2:
        actor = st.text_input('审核人（输入 test_user）', key='r2_review_actor_'+run['run_id'])
        delegation = R2_ROOT/'approval/delegation.json'
        delegated = False
        if delegation.is_file() and run['run_id'] in json.loads(delegation.read_text(encoding='utf8')).get('run_ids', []):
            delegated = st.checkbox('记录为用户授权代操作', key='r2_delegated_'+run['run_id'])
        if st.button('批准所选候选', disabled=not approved or actor != 'test_user', key='r2_approve_'+run['run_id']):
            from target.scenario_r2_live import R2Model
            try:
                receipt = workbench.approve(approved, R2Model(run['provider']), actor=actor,
                                             interaction='delegated_browser' if delegated else 'direct_browser')
                from target.scenario_live_agent import save
                save(R2_ROOT/'approval'/f"{run['run_id']}.json", receipt)
            except (OSError, ValueError):
                st.error('批准未写入，请重新校验候选。')
            else:
                st.rerun()
        return
    judge_authorized = True
    if not fixture and (run.get('gap_source') or run.get('source_workspace')):
        judge_limit = st.number_input('执行后最多发起多少次 AI 评判请求',
                                      min_value=1, max_value=200,
                                      value=max(1, len(approved)), step=1,
                                      key='c_gap_judge_limit_'+run['run_id']+'_'+','.join(approved))
        judge_authorized = not offline and bool(approved)
    if st.button('批准所选并执行', disabled=not approved or (offline and not fixture) or not judge_authorized,
                 key='abc_execute_'+run['run_id']):
        model, judge, runner = _run_models(run)
        try:
            if _run_root(run['run_id']) == RUN_ROOT:
                workbench.approve(approved, model, actor='human')
                workbench.submit_approved(judge or model, runner=runner)
            else:
                workbench.approve_and_execute(approved, model, actor='human', runner=runner,
                                              progress=lambda manifest: _progress(progress, manifest))
        except (OSError, ValueError):
            st.error('本轮已提交或无法校验，请重新读取运行状态。')
        st.rerun()


def quality_page(sessions=()):
    """Quality is the main board: one glance, two deep dives, then the rest."""
    from web.evidence import DIMENSIONS

    _show(TITLES[1], '一眼看清本轮 Agent 整体质量；功能准确性与工具调用单独展开原理、数据、结果。')
    workbench_explain.render(TITLES[1])
    run = _current(sessions, completed=False)
    summary = _current(sessions) if run and run['status'] == 'COMPLETED' else None
    if not summary:
        workbench_explain.guide_note(
            '本轮还没有完成的 AI 测试结果。先在「AI 场景总测试」跑完一轮，'
            '这里才会出现质量结论；不会用历史 Mock 快照冒充本轮成绩。',
            label='等待本轮测试')
        _guide_actions('quality_empty')
        return
    directory = run_directory(summary['run_id'], _run_root(summary['run_id']))
    from web.quality_board import render as render_quality_board
    render_quality_board(summary, directory)


def _quality_ai_summary(summary):
    """Show the real Judge output; never invent a new AI assessment."""
    directory = run_directory(summary['run_id'], _run_root(summary['run_id']))
    path = directory / 'judgements.jsonl'
    if not path.is_file():
        st.subheader('AI Judge 质量结论')
        st.caption('本轮没有可用的 AI Judge 记录；未用规则判断代替 AI 评判。')
        return
    rows = []
    for line in path.read_text(encoding='utf8').splitlines():
        try:
            row = json.loads(line)
        except (ValueError, TypeError):
            continue
        if row.get('status') not in ('passed', 'failed', 'indeterminate'):
            continue
        rows.append(row)
    st.subheader('AI Judge 质量结论')
    if not rows:
        st.caption('本轮没有完成的 AI Judge 记录；未用规则判断代替 AI 评判。')
        return
    table([{'用例': row.get('case_id'), '结论': _status(row.get('status')),
            '模型': row.get('judge_model') or '未记录',
            '评判依据': row.get('judge_reason') or '未记录',
            '证据': row.get('ref') or '未记录'} for row in rows], 'c_quality_judge', search=False, chrome=False)
    st.caption('上表直接来自本轮真实 AI Judge 记录，不新增模型请求，也不把规则结果伪装成 AI 结论。')


def _quality_distribution(normal):
    st.subheader('常规用例判定分布')
    statuses = ('passed', 'failed', 'indeterminate')
    series = (('objective', '客观断言'), ('judge', 'AI 评判'))
    scale = max(1, *(normal[key].get(status, 0) for key, _ in series for status in statuses))
    groups = []
    for status in statuses:
        rows = []
        for key, label in series:
            count = normal[key].get(status, 0)
            rows.append(
                f'<div class="ta-verdict-row"><span>{label}</span>'
                f'<span class="ta-verdict-track" aria-hidden="true"><i class="{key}" style="width:{count/scale:.3%}"></i></span>'
                f'<span>{count}</span></div>')
        groups.append(f'<div class="ta-verdict-group"><strong>{escape(_status(status))}</strong>{"".join(rows)}</div>')
    style = """<style>
.ta-verdict-distribution{background:var(--ta-panel);border:1px solid var(--ta-border);border-radius:.65rem;padding:.25rem .85rem;color:var(--ta-text)}
.ta-verdict-group{padding:.65rem 0}
.ta-verdict-group+.ta-verdict-group{border-top:1px solid var(--ta-border)}
.ta-verdict-row{display:grid;grid-template-columns:5rem minmax(0,1fr) 2.5rem;gap:.65rem;align-items:center;min-height:1.6rem;font-size:.88rem}
.ta-verdict-row span:last-child{text-align:right;font-variant-numeric:tabular-nums}
.ta-verdict-track{height:.45rem;border-radius:1rem;background:var(--ta-raised)}
.ta-verdict-track i{display:block;height:100%;border-radius:inherit;background:var(--ta-accent)}
.ta-verdict-track .judge{background:var(--ta-uncertain)}
</style>"""
    st.markdown(style + f'<div class="ta-verdict-distribution" role="group" aria-label="常规用例判定分布">{"".join(groups)}</div>',
                unsafe_allow_html=True)


def _gap_panel(summary, sessions):
    from target.scenario_workbench_gaps import inspect_run, quality_history

    run_id = summary['run_id']
    session = _user_session(sessions)
    root = _run_root(run_id)
    try:
        report = inspect_run(run_id, session.sid, root=root)
    except (OSError, ValueError, KeyError, TypeError):
        st.warning('缺口分析需要完整且归属当前会话的运行证据。')
        return
    gaps = report['gaps']
    focus = st.session_state.get('c_gap_focus')
    st.subheader('AI 测试缺口分析')
    st.write(f"缺口 {len(gaps)} 项 · P0/P1 {sum(row['risk'] in ('P0', 'P1') for row in gaps)} 项 · "
             f"未覆盖链路 {report['coverage']['uncovered']} 项 · 判定分歧 {report['disagreements']} 项")
    st.caption('系统根据断言、执行记录和覆盖矩阵计算缺口。生成补充用例时才会调用所选模型。')
    st.download_button('导出缺口分析', json.dumps(report, ensure_ascii=False, indent=2),
                       file_name=f'{run_id}-test-gaps.json', mime='application/json', key='c_gap_export_'+run_id)
    with st.expander('历史质量变化'):
        history = quality_history(session.sid, root=root, exclude=run_id)
        if history:
            table([{'运行': row['run_id'], '时间': row['created_at'], '已执行': row['executed'],
                    '覆盖': _rate(row['coverage']), '客观断言': _rate(row['objective']),
                    'AI 评判': _rate(row['judge'])} for row in history], 'c_gap_history', search=False, chrome=False)
        else:
            st.caption('当前会话没有其他已封存运行。')
    st.caption('在「AI 场景总测试」选择缺口并生成补充候选。')
    if gaps:
        st.button('制定补测计划', key='c_gap_open_plan', on_click=_open_gap_plan, args=(run_id,))
        if focus:
            relevant = [gap for gap in gaps if gap.get('dimension') == focus]
            with st.expander(f'{focus}缺口依据', expanded=True):
                if not relevant:
                    st.caption('本轮没有这一维度的补测缺口。')
                for gap in relevant:
                    st.text(f"{gap['risk']} · {gap['feature']} · {gap['reason']}")


def _open_gap_plan(run_id):
    _open_workbench(TITLES[0])
    st.session_state['c_gap_plan_'+run_id] = True


def _gap_generation(run, session):
    from target.scenario_workbench_gaps import inspect_run
    run_id = run['run_id']
    root = _run_root(run_id)
    try:
        gaps = inspect_run(run_id, session.sid, root=root)['gaps']
    except (OSError, ValueError, KeyError, TypeError):
        return
    if not gaps or not st.toggle('按本轮缺口生成补充候选', key='c_gap_plan_'+run_id):
        return
    st.markdown('#### 下一轮测试计划')
    st.caption('按风险及已确认失败排序。选择最多三项生成候选，候选随后进入人工审核。')
    dimensions = ['全部维度', *dict.fromkeys(row['dimension'] for row in gaps if row.get('dimension'))]
    focus = st.session_state.pop('c_gap_focus', None)
    filter_key = 'c_gap_dimension_'+run_id
    if focus in dimensions:
        st.session_state[filter_key] = focus
    dimension = st.selectbox('缺口维度', dimensions, key=filter_key)
    scoped = [row for row in gaps if dimension == '全部维度' or row.get('dimension') == dimension]
    choices = {row['gap_id']: row for row in scoped if not row.get('independent')}
    picked = st.multiselect('选择缺口', list(choices), max_selections=3, key=f'c_gap_selection_{run_id}_{dimension}',
                            format_func=lambda key: f"{choices[key]['risk']} · {choices[key]['feature']}")
    for gap in [choices[key] for key in picked] or scoped[:5]:
        with st.expander(f"{gap['risk']} · {gap['feature']} · {gap['status']}"):
            st.write(gap['reason'])
            st.markdown('\n'.join(f"{i}. {step}" for i, step in enumerate(gap['steps'], 1)))
            st.write('验收 · ' + gap['acceptance'])
            st.caption('前置条件 · ' + gap['prerequisites'])
            st.caption('场景复验需真实 API' if gap['requires_live'] else '场景复验可离线进行')
            st.caption('来源 · ' + '、'.join(gap['evidence_refs']))
            if gap.get('independent'):
                st.caption('此项需独立验收，无法用普通补充候选执行。')
    with st.expander('全部缺口'):
        table([{'缺口': row['gap_id'], '功能': row['feature'], '风险': row['risk'], '状态': row['status'],
                '发现依据': row['reason']} for row in gaps], 'c_gap_list', search=False, chrome=False)
    provider = st.selectbox('补充用例模型', ['deepseek', 'bailian'], key='c_gap_model_'+run_id,
                            format_func=lambda name: {'deepseek': 'DeepSeek', 'bailian': 'Qwen（百炼）'}[name])
    judge = 'bailian' if provider == 'deepseek' else 'deepseek'
    offline = os.getenv('TICKET_WEB_OFFLINE_ONLY') == '1'
    gap_limit = st.number_input('本轮最多发起多少次模型请求', min_value=1, max_value=200,
                                value=24, step=1, key='c_gap_limit_'+run_id)
    consent = not offline
    if offline:
        st.caption('当前为离线启动，可查看和导出计划。')
    if st.button('生成补充测试用例', disabled=offline or not picked or root != RUN_ROOT
                 or not st.session_state.get('c_source_has_trace'),
                 key='c_gap_generate_'+run_id):
        try:
            workbench = _new_source_run(session)
        except ValueError:
            st.warning('此来源已有待处理的运行。')
            return
        progress = st.empty()
        st.session_state[POINTER] = {'run_id': workbench.run_id, 'session_id': session.sid}
        st.query_params['abc_run'] = workbench.run_id
        try:
            workbench.submit(workbench.execute, session,
                             LiveWorkbenchModel(provider, authorized=consent, request_limit=gap_limit),
                             reviewer=LiveWorkbenchModel(judge, authorized=consent, request_limit=gap_limit),
                             source_workspace=_source_workspace(session),
                             source_turn_ids=st.session_state.get('c_turn_ids'), source_run_id=run_id,
                             gap_ids=picked, source_root=root, review_required=True)
        except (OSError, ValueError, KeyError, TypeError):
            st.warning('无法生成，请核对缺口归属和运行证据。')
            return
        st.rerun()


def _usage(run):
    if run.get('model_source') == 'deterministic_model_fixture':
        st.caption('真实 HTTP 0 · Token 0 · 模型费用 0')
        return
    from target.acceptance_budget import Batch
    path = run_directory(run['run_id'], _run_root(run['run_id']))/'model-budget.sqlite'
    if not path.is_file():
        st.caption('本轮尚未记录模型请求。')
        return
    try:
        usage = Batch(path, max_http=run['request_limit']).snapshot()
    except (OSError, ValueError, KeyError):
        st.caption('请求账本暂不可核验。')
        return
    request_rows = usage['requests']
    generation_count = sum(row.get('model_step') == 'generate' for row in request_rows)
    tokens = usage['observed_tokens'] if usage['observed_tokens'] is not None else 'UNKNOWN'
    st.caption(f"HTTP {usage['http_requests']}/{run['request_limit']} · 生成请求 {generation_count} · Token {tokens} · 费用 UNKNOWN")


def rag_page(sessions=()):
    _show(TITLES[2], '三个高风险能力分开看：RAG 怎么召回、多轮怎么继承、安全怎么拦住。')
    workbench_explain.render(TITLES[2])
    _snapshot, summary, directory = _inspection_context(sessions)
    # Three deliberately different boards: retrieval chain, cross-turn
    # inheritance, and attack surface.  No shared template.
    from web import topic_pages
    st.subheader('① RAG 检索质量')
    topic_pages.render_rag(summary, directory)
    st.subheader('② 多轮对话质量')
    topic_pages.render_multi_turn(summary, directory)
    st.subheader('③ 对抗性与安全测试')
    topic_pages.render_security(summary, directory)


def lab_page():
    _show(TITLES[3], '边界与异常一起看：总测试数据、设计口径，以及 M1–M8 缺陷注入矩阵。')
    workbench_explain.render(TITLES[3])
    snapshot, summary, directory = _inspection_context()
    dimensions = (summary or {}).get('by_dimension') or {}
    live = sum(int((dimensions.get(name) or {}).get('total_executed', 0) or 0)
               for name in ('边界', '安全'))

    # ① One merged data board.  No live boundary result yet?  Show the 103-case
    # baseline for these two dimensions instead of four meaningless zeros.
    st.subheader('① 边界 / 异常总测试数据')
    if summary and live:
        scenario_inspection.render_boundary_test_data(
            snapshot, summary, directory, key='c_lab_data')
    else:
        from web.quality_board import render_baseline_cases
        render_baseline_cases(dimensions=('边界', '安全'), key='c_lab_baseline', preview=8)

    # ② A readable design card: how our boundary tests are built and judged.
    st.subheader('② 边界怎么设计、怎么判')
    workbench_explain.render_boundary_design(summary if live else None,
                                             directory if live else None)

    # ③ Injector: the matrix first, then the always-open experiment runner
    # where you tick which faults to inject and run a detection pass.
    st.subheader('③ 异常注入器')
    from web.quality import render_injection_compact
    render_injection_compact()
    st.markdown('### 自己选注入哪些异常，跑一轮检测')
    from web.laboratory import render_experiment
    render_experiment()


def _boundary_rows(cases):
    from collections import Counter

    rows = []
    for category in BOUNDARY_EXAMPLES:
        scoped = [row for row in cases if row.get('validated') and row.get('boundary') == category
                  and row.get('dimension') in ('边界', '性能')]
        labels = []
        injected = detected = executed = 0
        for case in scoped:
            status = case.get('mutation_status')
            if not case.get('executed'):
                label = '已计划但未执行'
            else:
                executed += 1
                injected += status in ('detected', 'missed', 'indeterminate')
                detected += status == 'detected'
                label = {'detected': '已执行且已检出', 'missed': '已执行但未检出',
                         'indeterminate': '已注入，检出无法判定', 'not_triggered': '已执行，未触发注入'}.get(status)
                if label is None:
                    label = '已执行，注入证据缺失' if case.get('mutation') else '已执行，无注入计划'
            labels.append(label)
        states = Counter(labels)
        rows.append({'边界类型': category, '状态': '；'.join(f'{label} {count} 条' for label, count in states.items()) or '未计划',
                     '合格候选': len(scoped), '已执行': executed, '已注入': injected, '已检出': detected,
                     '检出率': f'{detected/injected:.1%} · {detected}/{injected}' if injected else '暂无注入样本',
                     '关联用例': '、'.join(row['case_id'] for row in scoped) or '—'})
    return rows


def trace_page(trace_dirs):
    """Performance = 反应速度 + 资源消耗, both measured on AI-generated scenarios."""
    _ = trace_dirs  # kept for the historical positional call contract
    _show(TITLES[4], '只讲两件事：Agent 多快给出结果（反应速度），这一轮用了多少资源（消耗）。数值只取本轮真实 Trace。')
    workbench_explain.render(TITLES[4])
    snapshot, summary, directory = _inspection_context()
    if not summary:
        workbench_explain.guide_note(
            '本轮还没有完成的 AI 场景总测试。下方先列出 AI 已经设计好的测试场景（待执行），'
            '耗时与消耗保持「未取得样本」，不借用历史 Mock 分位数。', label='等待本轮测试')
        _guide_actions('performance_empty', '性能', has_summary=False)
    scenario_inspection.render_performance_board(summary, directory)
    perf = (summary or {}).get('performance') or {}
    with st.expander('原始 Trace 样本（讲解用）', expanded=False):
        values = perf.get('case_wall_ms') or []
        tools = perf.get('tool_times') or []
        samples = perf.get('concurrency') or []
        if values:
            st.markdown('**用例实测耗时**')
            table([{'样本': i, '耗时（ms）': value} for i, value in enumerate(values, 1)],
                  'c_case_times', search=False)
        if tools:
            st.markdown('**单次工具耗时**')
            table([{'工具': row.get('tool'), '耗时（ms）': row.get('duration_ms'), '证据': row.get('ref')}
                   for row in tools], 'c_tool_times', search=False)
        if samples:
            st.markdown('**并发探针记录**')
            table([{'并发数': row.get('workers'), '范围': row.get('scope'),
                    'CPU（进程秒）': row.get('cpu_process_seconds'), '内存观测': row.get('memory'),
                    '请求/秒': row.get('qps'), '错误率': row.get('error_rate'),
                    '证据': row.get('evidence_ref')} for row in samples], 'c_concurrency', search=False)
        if not (values or tools or samples):
            st.caption('本轮没有留下用例级计时或并发资源采样记录；逐场景耗时见上方明细表。')
