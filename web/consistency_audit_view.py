"""C workbench page entry points. The application owns their navigation."""
import json
import os
import re

import streamlit as st

from target.scenario_workbench import (
    LiveWorkbenchModel, MAX_CASES, RUN_ROOT, Workbench, _run_case, export_bundle, load_run_results, read_manifest, run_directory,
)
from target.scenario_abc_budget import BATCH_ROOT, R2_ROOT
from web.design import empty, escape, header, kpis, table
from web.workbench_config import WORKBENCH_PAGES

POINTER = 'c_workbench_pointer'
WAITING = '请先在「AI 场景总测试」完成一次 AI 测试。'
TITLES = WORKBENCH_PAGES
LABEL = {'passed': '通过', 'failed': '失败', 'indeterminate': '无法判定', 'not_run': '未执行',
         'WAITING': '等待', 'RUNNING': '进行中', 'COMPLETED': '已完成', 'FAILED': '失败',
         'AWAITING_REVIEW': '待人工审核', 'APPROVED': '已人工批准'}
TOPICS = {
    'RAG': ('RAG 检索质量', '用例要求检索政策、核对条款或验证引用时，这里会汇总该类执行。',
            '查询超过 48 小时退票手续费，并引用条款编号。'),
    '多轮': ('多轮对话质量', '用例需要连续对话，并检查后续步骤是否沿用已知条件。',
            '先查上海到杭州的车次，再看下一页并比较两班车。'),
    '安全': ('对抗性与安全测试', '用例需要验证越权请求、未确认交易或异常诱导能否被拦截。',
            '未确认就要求直接支付，核对是否有订单或交易写入。'),
}
BOUNDARY_EXAMPLES = {
    '输入不完整': '缺少日期或站点时，检查是否先澄清。',
    '超长上下文': '对话很长时，检查已确认的查询条件是否仍被保留。',
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


def _user_session(sessions=()):
    sessions = st.session_state.get('user_sessions', sessions)
    index = st.session_state.get('user_active_session_index', 0)
    if type(index) is int and 0 <= index < len(sessions):
        session = sessions[index]
        if getattr(session, 'mode', None) == 'user':
            return session
    source = _accepted_source()
    if source is not None:
        return source
    if not sessions and st.query_params.get('abc_run') and st.query_params.get('session_id'):
        try:
            from web.session_store import restore_by_sid
            return restore_by_sid(st.query_params['session_id'])
        except (OSError, ValueError, KeyError, TypeError):
            return None
    return None


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
    if session is None or pointer.get('session_id') != session.sid:
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


def _show(title, note):
    header(title, note, badge='测试控制台')


def _rate(stat):
    return '未取得样本' if stat['value'] is None else f"{stat['value']:.1%} · {stat['numerator']}/{stat['denominator']}"


def _status(value):
    return LABEL.get(value, value)


def _numbers(summary):
    normal = summary['normal_quality']
    kpis([('客观断言', _rate(normal['objective_rate']), '通过 / 已执行常规用例'),
          ('AI 评判', _rate(normal['judge_rate']), '通过 / 可判定常规用例'),
          ('链路覆盖', _rate(summary['coverage_rate']), '已覆盖 / 42 个单元'),
          ('证据完整', _rate(summary['evidence_rate']), '完整 / 全部生成用例')])


def _open_workbench(page, dimension=None, lab_section=None):
    st.session_state['workspace_page'] = page
    if dimension is not None:
        st.session_state['c_gap_focus'] = dimension
        pointer = st.session_state.get(POINTER, {})
        st.session_state['c_gap_plan_active'] = pointer.get('run_id')
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
            elif active['error'] in ('C_WORKBENCH_GENERATION_INVALID_JSON','C_WORKBENCH_INVALID_GENERATION',
                                    'C_WORKBENCH_EMPTY_GENERATION','C_WORKBENCH_TRUNCATED_GENERATION'):
                st.error('模型返回的用例不完整或格式不正确，无法进入人工审核。')
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
    lookup = {case['case_id']: case for case in cases}
    selected = st.selectbox('查看用例证据', lookup,
                            format_func=lambda key: f"{key} · {lookup[key]['title']}", key=f'c_case_{board}')
    case = lookup[selected]
    execution = None
    with st.expander('客观断言、AI 判定与证据'):
        if not case['validated']:
            candidates = (directory / 'cases.jsonl').read_text(encoding='utf8').splitlines()
            source = next((row for row in map(json.loads, candidates) if row['case_id'] == selected), {})
            reasons = {'requested train query is missing or unverified': '指定车次缺少可核验的静态查询证据。'}
            for reason in source.get('errors', []):
                st.caption(reasons.get(reason, reason))
        st.write(f"客观断言 · {_status(case['objective_status'])}")
        if case['execution_ref']:
            execution = json.loads((directory / case['execution_ref']).read_text(encoding='utf8'))
            st.json({'assertions': [row['checks'] for row in execution['steps']],
                     'agent_trace_refs': execution['agent_trace_refs']}, expanded=False)
        st.write(f"AI 评判 · {_status(case['ai_status'])}")
        if case['judge_ref']:
            filename, line = case['judge_ref'].split('#line=', 1)
            if filename not in ('judgements.jsonl','judgements-revision-2.jsonl'):
                raise ValueError('C_WORKBENCH_JUDGEMENT_REF_INVALID')
            rows = (directory / filename).read_text(encoding='utf8').splitlines()
            index = int(line) - 1
            st.code(rows[index], language='json', wrap_lines=True)
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


def competition_page(sessions):
    _show(TITLES[0], '读取当前用户对话，生成可执行用例。五个板块共享本轮结果。')
    st.markdown('AI 会根据当前对话内容，动态分析业务场景，生成不同的测试目标、执行步骤和预期结果。'
                '不同的对话会产生与其业务内容相匹配的测试用例，而不是简单地从固定题库中选取测试题。'
                '生成后由你审核批准，再进入测试执行。')
    st.caption('读取对话 → AI 分析场景 → 生成测试用例 → 自动校验 → 人工审核 → 批准后执行')
    with st.expander('哪些用例会进入其他板块'):
        st.write('系统优先覆盖当前对话。政策检索、连续追问、写权限、输入边界和可计时的查询，会在相关时生成对应维度的候选。')
        st.write('候选卡片标出测试维度。通过校验并获批执行后，各页按本轮实际证据汇总。缺少覆盖时，可在质量分析选择缺口补测。')
    session = _user_session(sessions)
    if session is None or not session.history:
        empty('暂无可测试的对话', '在用户工作空间完成一轮对话后，再回到此处。')
        return
    run = _current(sessions, completed=False)
    provider = st.selectbox('生成与评判模型', ['deepseek', 'bailian'],
                            format_func=lambda name: {'deepseek': 'DeepSeek', 'bailian': 'Qwen（百炼）'}[name],
                            key='c_workbench_provider')
    offline = os.getenv('TICKET_WEB_OFFLINE_ONLY') == '1'
    authorized = st.checkbox(f'授权本轮最多 {MAX_CASES + 1} 次模型请求，用于生成与评判',
                             key='c_workbench_consent', disabled=offline)
    st.caption('被测 Agent 在隔离的离线环境中执行。模型费用按实际记录，未知费用保留未知。')
    st.caption('开始后会将脱敏的对话摘要和隔离执行证据发送给所选模型。')
    if offline:
        st.info('当前为离线启动，模型请求不可用。')
    acceptance = bool(run and _run_root(run['run_id']) != RUN_ROOT)
    clicked = st.button('开始本轮测试', type='primary', key='c_workbench_start', disabled=offline or not authorized or acceptance)
    progress = st.empty()
    if clicked:
        workbench = Workbench(session.sid)
        st.session_state[POINTER] = {'run_id': workbench.run_id, 'session_id': session.sid}
        st.query_params['abc_run'] = workbench.run_id
        run = workbench.execute(session, LiveWorkbenchModel(provider, authorized=authorized),
                                progress=lambda manifest: _progress(progress, manifest), review_required=True)
    if run:
        _progress(progress, run)
        st.caption(f"运行 ID · {run['run_id']}")
        with st.expander('五阶段执行记录'):
            st.code(_stage_text(run), language='markdown')
        _generation_details(run)
        if run['status'] == 'AWAITING_REVIEW':
            _review_run(session, run, progress, offline)
        if run['status']=='FAILED' and run['stages'][3]['status']=='FAILED' and not acceptance:
            workbench = Workbench.reopen(run['run_id'], session.sid, root=RUN_ROOT)
            if workbench.judge_recovery_available():
                st.info('可从已有结果恢复 AI 评判。仅向原模型发送尚未完成的评判请求，可能产生新费用。')
                consent = st.checkbox('授权本次恢复评判可能产生的模型费用', key='judge_recovery_consent_'+run['run_id'],
                                      disabled=offline)
                if st.button('仅恢复 AI 评判', key='judge_recovery_'+run['run_id'], disabled=offline or not consent):
                    try:
                        workbench.recover_judge(LiveWorkbenchModel(run['provider'], authorized=consent),
                                                progress=lambda manifest: _progress(progress, manifest))
                    except (OSError, ValueError, KeyError, TypeError):
                        st.warning('无法恢复：请核对运行证据和剩余请求额度。未启动场景生成或执行。')
                    else:
                        st.rerun()
            else:
                st.caption('本轮无法再次从页面恢复评判，已完成的证据仍保留。')
        if run['model_source'] == 'r2_live_model' and run['status'] == 'APPROVED':
            from web.scenario_r2_desk import business_desk
            business_desk(session, run, progress, offline, _progress)
        if run['model_source'] == 'r2_live_model' and run['status'] == 'FAILED':
            qa_path = run_directory(run['run_id'], _run_root(run['run_id']))/'cases.jsonl'
            if qa_path.is_file():
                with st.expander('QA-09 拒绝详情', expanded=True):
                    for line in qa_path.read_text(encoding='utf8').splitlines():
                        row = json.loads(line)
                        st.write(row['case_id'] + ' · ' + '、'.join(row['errors']))
    summary = _current(sessions)
    if not summary:
        return
    _numbers(summary)
    st.subheader('用例与执行结果')
    st.caption(f"对话 {summary['source_turn_count']} 轮 · {summary['generation_model']} · "
               f"{summary['generation_prompt_version']} · {summary['model_source']}")
    st.write(f"生成 {summary['generated']} 条 → 校验通过 {summary['validated']} 条 → 实际执行 {summary['executed']} 条")
    table([{'用例': row['case_id'], '名称': row['title'], '维度': row['dimension'],
            '客观断言': _status(row['objective_status']), 'AI 评判': _status(row['ai_status'])}
           for row in summary['cases']], 'c_cases', search=False)
    with st.expander('链路覆盖矩阵'):
        table([{'维度': name, **{cell['node']: cell['executed'] for cell in summary['coverage_matrix']
                                if cell['dimension'] == name}} for name in summary['by_dimension']],
              'c_matrix', search=False)
    directory = run_directory(summary['run_id'], _run_root(summary['run_id']))
    turns = json.loads((directory / 'conversation.json').read_text(encoding='utf8'))['turns']
    with st.expander('对话快照和生成 Prompt'):
        st.json(turns, expanded=False)
        prompt = json.loads((directory / 'prompts/generate.json').read_text(encoding='utf8'))
        st.code(prompt['prompt'], wrap_lines=True)
    owned_runs = {turn['run_id'] for turn in turns if turn.get('run_id')}
    records = [audit for audit in session.audits if audit.get('trace_id') in owned_runs
               and (audit.get('public_trace') or {}).get('session_id') == session.sid]
    if records and st.checkbox('查看来源 Trace', key=f"abc_source_trace_{summary['run_id']}"):
        from web.trace_view import show_record
        for audit in records:
            show_record(audit, key='abc_source_'+audit['trace_id'])
    _evidence(summary, 'overview')
    st.download_button('导出本轮材料', export_bundle(summary['run_id'], summary['session_id'], root=_run_root(summary['run_id'])),
                       file_name=f"ticket-agent-c-{summary['run_id']}.zip", mime='application/zip', key='c_export')


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
             'executor_compatible':'执行器兼容','retained':'进入人工审核'}
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
    for case, plan in options:
        with st.expander(case['case_id'] + ' · ' + case['title'], expanded=True):
            st.caption(f"测试维度 · {case['dimension']}")
            if case.get('gap_reference'):
                st.caption(case['gap_reference']['gap_id'])
                st.caption('来源证据 · ' + '、'.join(case['gap_reference']['evidence_refs']))
            st.write('测试目标 · '+case['objective'])
            st.markdown('**执行步骤与预期结果**')
            for index, step in enumerate(plan['integration_steps'],1):
                st.write(f"{index}. {step.get('message') or step.get('tool') or step['kind']}")
                for check in step.get('checks',[]):
                    operators = {'eq':'等于','ne':'不等于','ge':'至少','len':'数量为','contains':'包含','not_contains':'不包含'}
                    st.caption(f"{check['path']} {operators.get(check['op'],check['op'])} {check['value']}")
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
    if run.get('gap_source'):
        judge_authorized = st.checkbox(f'授权执行后最多 {len(approved)} 次 AI 评判请求',
                                       disabled=offline or not approved,
                                       key='c_gap_judge_consent_'+run['run_id']+'_'+','.join(approved))
        st.caption('候选使用隔离离线 Agent 执行。AI 评判会另计模型费用。')
    if st.button('批准所选并执行', disabled=not approved or offline or not judge_authorized,
                 key='abc_execute_'+run['run_id']):
        if _run_root(run['run_id']) == RUN_ROOT:
            model = LiveWorkbenchModel(run['provider'], authorized=True)
            runner = _run_case
        else:
            from target.scenario_abc_live import PilotModel
            model = PilotModel(run['provider'])
            runner = model.runner
        try:
            workbench.approve_and_execute(approved, model, actor='human', runner=runner,
                                           progress=lambda manifest: _progress(progress, manifest))
        except (OSError, ValueError):
            st.error('本轮已提交或无法校验，请重新读取运行状态。')
        st.rerun()


def _result(title, note, sessions=()):
    _show(title, note)
    summary = _current(sessions)
    if not summary:
        st.info(WAITING)
    else:
        st.caption(f"运行 ID · {summary['run_id']} · {summary['model_source']}")
    return summary


def quality_page(sessions=()):
    summary = _result(TITLES[1], '分开查看确定性断言和语义评判，再下钻到执行证据。', sessions)
    if not summary:
        return
    _numbers(summary)
    normal = summary['normal_quality']
    if normal['executed']:
        _quality_distribution(normal)
    _gap_panel(summary, sessions)
    st.subheader('功能与工具调用')
    table([{'维度': name, '执行': data.get('total_executed', data['executed']),
            '有实测值的断言': data.get('effective_checks'), '未覆盖节点': data.get('uncovered_nodes'),
            '常规通过': data['objective'].get('passed', 0), '常规失败': data['objective'].get('failed', 0),
            'AI 无法判定': data['indeterminate'], 'AI 评判': _rate(data['judge_rate']),
            '执行证据': data.get('evidence', [])} for name, data in summary['by_dimension'].items()], 'c_dimensions')
    st.subheader('四层状态一致性')
    if not summary['consistency']:
        st.caption('当前对话没有可关联的订单操作回执。')
    for row in summary['consistency']:
        with st.expander(f"{row['identity']['operation_id']} · {_status(row['status'])}"):
            if row['missing_layers']:
                st.caption('缺少证据 · ' + '、'.join(row['missing_layers']))
            st.json(row['layers'], expanded=False)
    with st.expander('M1–M8 异常注入'):
        table([{'变异': item['code'], '注入': item['injected'], '检出': item['detected'],
                '未触发': item['not_triggered'], '无法判定': item['indeterminate'],
                '检出率': _rate(item['rate']), '证据': item['evidence']} for item in summary['mutations']], 'c_mutations')
    _evidence(summary, 'quality')


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
                    'AI 评判': _rate(row['judge'])} for row in history], 'c_gap_history', search=False)
        else:
            st.caption('当前会话没有其他已封存运行。')
    if st.button('生成下一轮测试计划', key='c_gap_plan_'+run_id):
        st.session_state['c_gap_plan_active'] = run_id
    if st.session_state.get('c_gap_plan_active') != run_id:
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
                '发现依据': row['reason']} for row in gaps], 'c_gap_list', search=False)
    provider = st.selectbox('补充用例模型', ['deepseek', 'bailian'], key='c_gap_model_'+run_id,
                            format_func=lambda name: {'deepseek': 'DeepSeek', 'bailian': 'Qwen（百炼）'}[name])
    offline = os.getenv('TICKET_WEB_OFFLINE_ONLY') == '1'
    consent = st.checkbox('授权生成一次模型请求，费用按实际记录', disabled=offline,
                          key='c_gap_consent_'+run_id)
    if offline:
        st.caption('当前为离线启动，可查看和导出计划。')
    if st.button('生成补充测试用例', disabled=offline or not consent or not picked or root != RUN_ROOT,
                 key='c_gap_generate_'+run_id):
        workbench = Workbench(session.sid)
        progress = st.empty()
        try:
            run = workbench.execute(session, LiveWorkbenchModel(provider, authorized=consent),
                                    source_run_id=run_id, gap_ids=picked, source_root=root,
                                    review_required=True,
                                    progress=lambda manifest: _progress(progress, manifest))
        except (OSError, ValueError, KeyError, TypeError):
            st.warning('无法生成，请核对缺口归属和运行证据。')
            return
        st.session_state[POINTER] = {'run_id': run['run_id'], 'session_id': session.sid}
        st.query_params['abc_run'] = run['run_id']
        st.query_params['session_id'] = session.sid
        _generation_details(run)
        if run['status'] == 'AWAITING_REVIEW':
            st.success('补充用例已生成。可在下方审核，或在「AI 场景总测试」恢复本轮。')
            _review_run(session, run, progress, offline)
        else:
            _progress(progress, run)


def rag_page(sessions=()):
    _show(TITLES[2], '查看政策检索、连续对话和交易防护的实际证据。')
    run = _current(sessions, completed=False)
    summary = _current(sessions) if run and run['status'] == 'COMPLETED' else None
    cases = summary['cases'] if summary else _review_cases(run)
    if run:
        st.caption(f"运行 ID · {run['run_id']} · {run['model_source']}")
    st.subheader('如何触发')
    st.write('在 AI 场景总测试生成候选，审核通过并执行后，这里会按用例维度汇总。质量分析也可以按缺口补测。')
    _guide_actions('topic_guide', has_summary=bool(summary))
    for dimension, (title, trigger, example) in TOPICS.items():
        st.subheader(title)
        st.write(_topic_status(cases, dimension, run))
        st.caption(trigger)
        st.caption('示例 · ' + example)
        if not summary:
            continue
        data = summary['by_dimension'][dimension]
        if not data.get('total_executed', data['executed']):
            _evidence(summary, f'topic_{dimension}', dimension=dimension)
            continue
        st.write(f"客观断言 {_rate(data['objective_rate'])}")
        for label, metric in summary['special_metrics'][dimension].items():
            st.caption(f'{label} · {_rate(metric)}')
        _evidence(summary, f'topic_{dimension}', dimension=dimension)


def lab_page():
    from web.laboratory import render_experiment
    from web.quality import concurrency_topic, mutation_matrix
    from web.trace_view import lab_replay

    _show(TITLES[3], '运行隔离的异常注入实验，查看实际检出和原始证据。')
    run = _current(completed=False)
    summary = _current() if run and run['status'] == 'COMPLETED' else None
    cases = summary['cases'] if summary else _review_cases(run)
    if run:
        st.caption(f"运行 ID · {run['run_id']} · {run['model_source']}")
    st.subheader('本轮覆盖了哪些边界')
    st.write('下表汇总 AI 场景总测试中通过校验的边界候选。只有实际注入的样本才计算检出率。'
             '「未计划」表示本轮没有这类合格候选。')
    with st.expander('建议覆盖的边界'):
        for name, example in BOUNDARY_EXAMPLES.items():
            st.markdown(f'**{name}**　{example}')
        _guide_actions('boundary_guide', '边界', has_summary=bool(summary))
    with st.container(key='workbench_boundary_results'):
        st.markdown('<style>.st-key-workbench_boundary_results .ta-table-wrap table{min-width:49rem}'
                    '.st-key-workbench_boundary_results .ta-table-wrap th{white-space:nowrap}'
                    '.st-key-workbench_boundary_results .ta-table-wrap td:nth-child(2){min-width:10rem}</style>',
                    unsafe_allow_html=True)
        table(_boundary_rows(cases), 'c_boundaries', search=False)
    if summary:
        _evidence(summary, 'boundary', dimension='边界')

    st.subheader('独立异常实验')
    st.caption('选择下方「运行实验」可直接配置并执行 M1–M8。实验的 Trace 和回放独立保存。')
    section = st.radio('异常注入', ['运行实验', '历史回放', 'M1–M8 缺陷统计', 'M8 并发证据'],
                       horizontal=True, key='c_lab_section')
    if section == '运行实验':
        render_experiment()
    elif section == '历史回放':
        lab_replay(getattr(st.session_state.get('lab_session'), 'sid', ''))
    elif section == 'M1–M8 缺陷统计':
        def open_m8():
            st.session_state['c_lab_section'] = 'M8 并发证据'
        mutation_matrix(on_m8=open_m8)
    else:
        concurrency_topic()


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
    _ = trace_dirs  # kept for the historical positional call contract; the run owns this view
    _show(TITLES[4], '查看本轮用例总耗时、单次工具耗时及并发证据。')
    run = _current(completed=False)
    summary = _current() if run and run['status'] == 'COMPLETED' else None
    cases = summary['cases'] if summary else _review_cases(run)
    if run:
        st.caption(f"运行 ID · {run['run_id']} · {run['model_source']}")
    st.subheader('如何触发')
    st.write('用当前对话生成「性能」候选，例如连续执行三轮车次查询与比较。审核后执行，有计时样本时会显示用例总耗时与延迟分布。')
    st.write('普通功能测试的工具耗时来自 Trace。M8 是两路重复建单探针，可在边界页直接运行。'
             '10 个客户端并发查车、同锁建单吞吐量等需要独立并发压测。')
    _guide_actions('performance_guide', '性能', has_summary=bool(summary))
    st.button('查看独立 M8 并发证据', key='performance_m8', on_click=_open_workbench,
              args=(TITLES[3], None, 'M8 并发证据'))
    st.subheader('本轮采样')
    st.write(_topic_status(cases, '性能', run))
    if not summary:
        st.caption('待用例获批执行并采集计时后，可在此查看证据。')
        return
    perf = summary['performance']
    if perf['case_wall_ms']:
        kpis([('P50', f"{perf['p50']} ms", '隔离执行用例耗时'), ('P95', f"{perf['p95']} ms", '隔离执行用例耗时')])
        st.bar_chart([{'样本': str(i), '耗时（ms）': value} for i, value in enumerate(perf['case_wall_ms'], 1)],
                     x='样本', y='耗时（ms）', height=230)
        st.caption('耗时为本轮隔离用例实测。常规业务吞吐量仍待独立压测。')
    else:
        st.caption('本轮没有性能类用例总耗时。单次工具耗时会在下方单列。')
    if not perf['concurrency']:
        st.caption('本轮没有实际并发探针或压测证据。')
    else:
        rows = []
        for sample in perf['concurrency']:
            row = {'并发数': sample['workers'], '范围': sample['scope'], '证据': sample['evidence_ref']}
            if sample.get('measurement_kind') == 'load_test':
                for key, label in (('p50_ms','P50（ms）'), ('p95_ms','P95（ms）'), ('p99_ms','P99（ms）'),
                                   ('qps','请求／秒'), ('error_rate','错误率'), ('timeout_rate','超时率')):
                    row[label] = sample.get(key)
            rows.append(row)
        table(rows, 'c_concurrency')
    if perf['tool_times']:
        st.subheader('单次工具耗时')
        table([{'工具': row['tool'], '耗时（ms）': row['duration_ms'], '证据': row['ref']}
               for row in perf['tool_times']], 'c_tool_times')
    if not any(row.get('memory') or row.get('cpu_process_seconds') is not None for row in perf['concurrency']):
        st.caption('本轮未采集 CPU 或内存使用量。')
    _evidence(summary, 'performance', dimension='性能')
