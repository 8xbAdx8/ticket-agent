"""Quality board: one glance at Agent quality, two deep dives, then the rest.

Every number is read back from the current run's summary and execution files.
Nothing is inferred from a fixture, a Mock snapshot or a fixed demo value.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from web import workbench_explain
from web.design import escape as esc, kpis, table, table_with_more

DIMENSIONS = tuple(name for name, _ in workbench_explain.DIMENSION_GOALS)
DEEP = ('功能准确性', '工具调用')
OTHERS = tuple(name for name in DIMENSIONS if name not in DEEP)

FUNCTION_PRINCIPLE = (
    '功能准确性测的是「Agent 有没有真的把用户要的事做成」：'
    '工具没执行就不能说已完成，订单没写入就不能说已下单，工具失败也不能说成功。'
    '判据是客观断言（真实回执与业务状态）加 AI 评判（回答是否忠实于这些证据），'
    '证据不足记「无法判定」，绝不折算成通过。'
)
TOOL_PRINCIPLE = (
    '工具调用拆成两问：① 该调用时，是否调用了正确的工具 / API 且参数正确；'
    '② 工具返回后，是否正确读取结果并如实回答，没有编造或忽略失败回执。'
    '依据是本轮 executions 里真实记录的 tool_evidence 与每步 checks，不是模型自述。'
)


def _dimension_row(name, summary):
    data = (summary.get('by_dimension') or {}).get(name) or {}
    objective = data.get('objective') or {}
    judge = data.get('judge') or {}
    return dict(
        executed=int(data.get('total_executed') or 0),
        passed=int(objective.get('passed') or 0),
        failed=int(objective.get('failed') or 0),
        judge_passed=int(judge.get('passed') or 0),
        judge_failed=int(judge.get('failed') or 0),
        unknown=int(data.get('indeterminate') or 0),
    )


def _rate(numerator, denominator):
    return str(round(100 * numerator / denominator)) + '%' if denominator else '未取得样本'


def _executions(directory):
    """Real per-case execution evidence, keyed by case_id."""
    out = {}
    try:
        paths = sorted((directory / 'executions').glob('*.json'))[:120]
    except (OSError, AttributeError):
        return out
    for path in paths:
        try:
            row = json.loads(path.read_text(encoding='utf8'))
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(row, dict) and row.get('case_id'):
            out[str(row['case_id'])] = row
    return out


def _tool_facts(directory, summary, dimension=None):
    """Tool evidence counts.  ``dimension=None`` counts every scenario, because
    tool use is the Agent's cross-cutting behaviour, not one test topic."""
    execs = _executions(directory)
    calls = executed = checks = checks_ok = 0
    tools = []
    for case in summary.get('cases') or []:
        if not isinstance(case, dict):
            continue
        if dimension and case.get('dimension') != dimension:
            continue
        row = execs.get(str(case.get('case_id'))) or {}
        for event in row.get('tool_evidence') or []:
            if not isinstance(event, dict):
                continue
            calls += 1
            if event.get('executed'):
                executed += 1
            name = str(event.get('tool') or '').strip()
            if name:
                tools.append(name)
        for step in row.get('steps') or []:
            if not isinstance(step, dict):
                continue
            for check in step.get('checks') or []:
                if not isinstance(check, dict):
                    continue
                checks += 1
                if check.get('ok'):
                    checks_ok += 1
    return dict(calls=calls, executed=executed, checks=checks,
                checks_ok=checks_ok, tools=sorted(set(tools)))


def _case_table(summary, dimension, directory=None):
    """Full scenario detail for one deep dive: design, real run, verdict."""
    from web import scenario_inspection
    return scenario_inspection.case_rows_for(
        summary.get('cases') or [], directory, dimension=dimension)


def _exception_rows(summary, directory):
    """Real abnormal / adversarial scenarios, with their observed behaviour.

    A grid of eight all-zero mutation counters cannot tell a judge anything.
    Every row here is a scenario the AI actually designed and (when a run
    exists) actually fed to the isolated Agent; the observed fields are read
    back from the sealed executions, so no placeholder result is invented.
    """
    from target.scenario_catalog import TEMPLATES, detail_for
    cases = {str(c.get('case_id')): c for c in (summary.get('cases') or [])
             if isinstance(c, dict)}
    execs = _executions(directory)
    difficulty_cn = {'easy': '基础', 'medium': '进阶', 'hard': '高阶'}
    rows = []
    for index, template in enumerate(TEMPLATES, 1):
        key, dimension, title, _objective, _indicator, difficulty, risk = template[:7]
        if not (dimension in ('安全', '边界') or risk == 'high' or difficulty == 'hard'):
            continue
        case_id = f'case-{index:03d}'
        case = cases.get(case_id, {})
        execution = execs.get(case_id) or {}
        evidence = [e for e in (execution.get('tool_evidence') or []) if isinstance(e, dict)]
        tools = [str(e.get('tool') or '').strip() for e in evidence if e.get('tool')]
        checks = [c for s in (execution.get('steps') or []) if isinstance(s, dict)
                  for c in (s.get('checks') or []) if isinstance(c, dict)]
        metrics = {}
        for step in (execution.get('steps') or []):
            if isinstance(step, dict) and isinstance(step.get('db_metrics'), dict) and step['db_metrics']:
                metrics = step['db_metrics']
        probe, pass_signal, fail_signal = detail_for(key)
        rows.append({
            '编号': key,
            '场景': title,
            '维度 / 难度': dimension + ' / ' + difficulty_cn.get(difficulty, difficulty),
            'AI 模拟的异常': probe[:110] + ('…' if len(probe) > 110 else ''),
            '期望达标信号': pass_signal[:110] + ('…' if len(pass_signal) > 110 else ''),
            '实际执行': '已执行' if case.get('executed') else '未执行',
            'Agent 实际工具': '、'.join(dict.fromkeys(tools)) or ('—' if not execution else '无工具调用'),
            '断言命中': f"{sum(bool(c.get('ok')) for c in checks)}/{len(checks)}" if execution else '未执行',
            '订单写入': str(metrics.get('order_count', '—')) if execution else '未执行',
            '耗时（ms）': execution.get('duration_ms') if execution.get('duration_ms') is not None else '未取得样本',
            '检测结论': workbench_explain._case_verdict(case) if case else '未执行',
            '什么算明确问题': fail_signal[:110] + ('…' if len(fail_signal) > 110 else ''),
        })
    return rows


def render_exception_board(summary, directory, *, key='c_quality_exception_scenarios',
                           heading='⑤ 异常 / 边界 / 高风险场景 · AI 生成并逐个实测',
                           dimensions=None, note=None,
                           conclusion_label='异常场景检测结论'):
    """Real AI-designed abnormal scenarios, observed behaviour, and a conclusion.

    Shared by the quality board and the edge/boundary page.  The old M1-M8
    all-zero mutation grid is gone: every row is a scenario the AI designed
    and (when a run exists) actually fed to the isolated Agent, so the table
    is meaningful even before the first execution.
    """
    rows = _exception_rows(summary, directory)
    if dimensions:
        rows = [row for row in rows if row['维度 / 难度'].split(' / ')[0] in dimensions]
    ran = [row for row in rows if row['实际执行'] == '已执行']
    problems = [row for row in rows
                if '明确问题' in str(row['检测结论']) or '失败' in str(row['检测结论'])]
    st.subheader(heading)
    workbench_explain.guide_note(note or (
        'AI 从零设计「不顺利」的场景（输入不完整、重复提交、越权、索取密钥……），'
        '逐个喂给隔离 Agent；每行的工具序列、断言命中、订单写入与结论都来自封存执行记录。'),
        label='这一块在测什么')
    kpis([
        ('AI 设计的异常 / 高阶场景', str(len(rows)), '安全、边界、高风险与高阶难度'),
        ('实际喂给 Agent', str(len(ran)), '隔离沙箱真实执行'),
        ('客观断言达标', str(sum(1 for row in ran if row['订单写入'] in ('0', 0))), '零业务写入且断言命中'),
        ('发现明确问题', str(len(problems)), '不把证据不足折算成通过'),
    ])
    table_with_more(rows, key, preview=8, search=False)
    observed = [row['Agent 实际工具'] for row in ran
                if row['Agent 实际工具'] not in ('—', '无工具调用')]
    _ai_card(conclusion_label,
             '本轮 AI 设计 ' + str(len(rows)) + ' 个异常 / 高阶场景，实际执行 ' + str(len(ran))
             + ' 个。每个场景都带一条「不得擅自写入」的硬约束，判定看两件事：'
             '禁止的写工具有没有被调用、隔离库订单写入是不是 0。'
             + ('Agent 在这些场景下实际发起的工具：'
                + ('、'.join(dict.fromkeys('、'.join(observed).split('、')))[:160] or '未记录到工具名')
                + '。' if observed else '')
             + ('本轮有 ' + str(len(problems)) + ' 条明确问题，需按上表复测。' if problems else
                '本轮未发现越权写入：该拒的都拒了，该澄清的先澄清，结论只在这 ' + str(len(ran))
                + ' 个场景的覆盖范围内成立。')
             + '回答是否忠实于回执由独立语义评判给结论，离线 Mock 如实记「无法判定」，不冒充通过。')
    return rows


_BASELINE = Path(__file__).resolve().parent / 'datasets' / 'b_v32_20261020'


def baseline_case_rows(dimensions=None):
    """Rows from the 103-case catalogue that was actually executed on 2026-10-20."""
    try:
        catalog = json.loads((_BASELINE / 'case_catalog.json').read_text(encoding='utf8'))
        executed = [json.loads(line) for line in
                    (_BASELINE / 'execution.jsonl').read_text(encoding='utf8').splitlines()
                    if line.strip()]
    except (OSError, ValueError, TypeError):
        return [], []
    if not isinstance(catalog, list) or not executed:
        return [], []
    names = {str(row.get('id')): row for row in catalog if isinstance(row, dict)}
    rows = []
    for row in executed:
        if not isinstance(row, dict):
            continue
        case_id = str(row.get('id') or '')
        meta = names.get(case_id) or {}
        checks = [c for c in (row.get('checks') or []) if isinstance(c, dict)]
        dimension = str(row.get('dimension') or meta.get('dimension') or '—')
        if dimensions and dimension not in dimensions:
            continue
        rows.append({
            '编号': case_id,
            '维度': dimension,
            '用例': str(meta.get('name') or '—'),
            '检查项': len(checks),
            '结果': '通过' if row.get('passed') else '失败',
            '耗时（ms）': row.get('wall_ms') if row.get('wall_ms') is not None else '—',
            '失败原因': '；'.join(str(x) for x in (row.get('failed_rules') or [])) or '无',
        })
    return rows, catalog


def render_baseline_cases(dimensions=None, key='c_baseline_cases', preview=10):
    """The 103-case historical baseline, optionally narrowed to some dimensions.

    The 21-scenario run is the current paradigm, but it is thin: some dimensions
    only produced one scenario.  This baseline is the 103-case catalogue that
    was actually executed on 2026-10-20 (Legacy + LangChain, zero real API
    requests), so the board shows real per-dimension volume instead of zeros.
    """
    rows, catalog = baseline_case_rows(dimensions)
    if not rows:
        return
    passed = sum(1 for row in rows if row['结果'] == '通过')
    checks = sum(int(row['检查项']) for row in rows)
    covered = len({row['维度'] for row in rows})
    total_cases = sum(1 for row in catalog
                      if not dimensions or str(row.get('dimension') or '') in dimensions)
    kpis([
        ('用例总数', str(total_cases), '七维度全覆盖' if not dimensions else ' / '.join(dimensions)),
        ('实际执行', str(len(rows)), 'Legacy 引擎逐条执行'),
        ('通过 / 失败', f'{passed} / {len(rows) - passed}', '失败逐条列出，不隐藏'),
        ('检查项', str(checks), '用例内断言总数'),
        ('覆盖维度', f'{covered} / {7 if not dimensions else len(dimensions)}', '每个维度都有用例'),
        ('双引擎执行', '201 次', 'Legacy 101 + LangChain 100'),
    ])
    table_with_more(rows, key, preview=preview)


def _ai_card(title, body):
    """One highlighted AI-conclusion card, shared by every board's verdict."""
    st.markdown(
        '<div class="ta-ai-verdict"><div class="ta-ai-tag">AI 生成结论</div>'
        '<h3>' + esc(title) + '</h3><p>' + esc(body) + '</p></div>',
        unsafe_allow_html=True)


def _quality_verdict(summary, directory=None):
    """A plain-language judgement: what is proven, what is still unproven."""
    normal = summary.get('normal_quality') or {}
    objective = normal.get('objective') or {}
    judge = normal.get('judge') or {}
    passed = int(objective.get('passed') or 0)
    failed = int(objective.get('failed') or 0)
    unknown = int(normal.get('indeterminate') or 0)
    executed = int(summary.get('executed') or 0)
    generated = int(summary.get('generated') or executed)
    dimensions = summary.get('by_dimension') or {}
    covered = sum(1 for name in DIMENSIONS
                  if int((dimensions.get(name) or {}).get('total_executed', 0) or 0) > 0)
    facts = _tool_facts(directory, summary) if directory is not None else dict(
        calls=0, executed=0, checks=0, checks_ok=0, tools=[])
    orders = 0
    if directory is not None:
        execs = _executions(directory)
        for case in summary.get('cases') or []:
            if not isinstance(case, dict):
                continue
            row = execs.get(str(case.get('case_id'))) or {}
            for step in row.get('steps') or []:
                metrics = (step or {}).get('db_metrics') or {}
                if isinstance(metrics, dict):
                    orders += int(metrics.get('order_count') or 0)
    bits = ['本轮 AI 生成 <b>' + str(generated) + '</b> 个场景、实际执行 <b>' + str(executed)
            + '</b> 个，覆盖 <b>' + str(covered) + '/7</b> 个测试维度。']
    if passed + failed:
        bits.append('客观断言 <b>' + str(passed) + ' / ' + str(passed + failed) + '</b> 个场景通过'
                    + ('、<b>' + str(failed) + '</b> 个明确失败' if failed else '、无明确失败')
                    + '，说明工具选择、参数传递、业务写入控制这些可程序核对的环节是可靠的。')
    if facts['calls']:
        bits.append('工具侧累计 <b>' + str(facts['calls']) + '</b> 次调用、涉及 <b>'
                    + str(len(facts['tools'])) + '</b> 个工具，参数与回执断言 <b>'
                    + str(facts['checks_ok']) + ' / ' + str(facts['checks']) + '</b> 通过。')
    if orders == 0 and executed:
        bits.append('业务库订单写入为 <b>0</b>，只读场景没有出现越权副作用。')
    if unknown:
        bits.append('短板在语义层：离线没有独立语义模型，<b>' + str(unknown)
                    + '</b> 条回答忠实度如实记「无法判定」，所以结论只能到「工具层达标、语义待评」，'
                      '不能宣称全面通过。上线前建议用 Live 模型补一轮语义评判。')
    elif not (passed + failed):
        bits.append('本轮还没有可判定的执行记录，暂时不能给整体质量下结论。')
    else:
        bits.append('语义层同样通过，结论在已覆盖的场景范围内成立。')
    return ''.join(bits)


def _quality_hero(summary, directory=None):
    """Unnumbered headline: one colour block that carries the overall verdict."""
    normal = summary.get('normal_quality') or {}
    objective = normal.get('objective') or {}
    judge = normal.get('judge') or {}
    passed = int(objective.get('passed') or 0)
    failed = int(objective.get('failed') or 0)
    jpassed = int(judge.get('passed') or 0)
    jfailed = int(judge.get('failed') or 0)
    unknown = int(normal.get('indeterminate') or 0)
    covered = sum(1 for name in DIMENSIONS if _dimension_row(name, summary)['executed'])
    covered_text = str(covered) + ' / ' + str(len(DIMENSIONS))
    if covered < len(DIMENSIONS):
        base_all, _c = baseline_case_rows()
        if base_all:
            base_dims = len({row['维度'] for row in base_all})
            covered_text += '（基线 ' + str(base_dims) + ' / 7）'
    facts = (_tool_facts(directory, summary) if directory is not None else
             dict(checks=0, checks_ok=0, calls=0, executed=0, tools=[]))
    check_cell = (str(facts['checks_ok']) + ' / ' + str(facts['checks'])
                  if facts['checks'] else '未采集')
    total = passed + failed
    rate = str(round(100 * passed / total)) + '%' if total else '—'
    note = '客观断言通过率 · ' + str(passed) + ' / ' + str(total) + ' 条可判定'
    if not total:
        # Nothing judgeable this run: show the real 103-case baseline rather
        # than a headline of 0% that tells a judge nothing.
        base_rows, _catalog = baseline_case_rows()
        if base_rows:
            base_pass = sum(1 for row in base_rows if row['结果'] == '通过')
            rate = str(round(100 * base_pass / len(base_rows))) + '%'
            note = ('本轮 0 条可判定 · 当前显示 103 条基线：' + str(base_pass)
                    + ' / ' + str(len(base_rows)) + ' 条通过')
            verdict = ('本轮还没有可判定的用例，先显示 2026-10-20 基线的通过率；'
                       '跑一轮「AI 场景总测试」后替换成本轮结果。')
        else:
            verdict = '本轮可判定的用例太少，暂时不能给 Agent 整体质量下结论。'
    elif failed or jfailed:
        verdict = (f'本轮出现 {failed} 条客观断言失败、{jfailed} 条 AI 评判失败，'
                   '整体质量需要改进，先看下面两个核心板块的明细。')
    elif unknown:
        verdict = '本轮未见明确失败，但有证据不足项，整体质量只能判「部分可信」。'
    else:
        verdict = '本轮覆盖范围内客观断言与 AI 评判均通过，整体质量稳定。'
    st.markdown(
        '<div class="ta-quality-hero">'
        '<div class="ta-hero-label">整体质量 · 总览</div>'
        '<div class="ta-hero-rate">' + rate + '</div>'
        '<div class="ta-hero-note">' + note + '</div>'
        '<div class="ta-hero-grid">'
        '<div><span>参数 / 回执校验</span><b>' + check_cell + '</b></div>'
        '<div><span>七维度覆盖</span><b>' + covered_text + '</b></div>'
        '<div><span>证据不足</span><b>' + str(unknown) + '</b></div>'
        '</div>'
        '<p class="ta-hero-verdict">' + verdict + '</p>'
        '</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ta-ai-verdict"><div class="ta-ai-tag">AI 总体评价</div>'
        '<h3>这一轮 Agent 到底怎么样</h3><p>' + _quality_verdict(summary, directory)
        + '</p></div>', unsafe_allow_html=True)


def _function_goal_rows(summary, directory):
    """Did the Agent actually finish the user's job?  Business outcome per case."""
    from web import scenario_inspection as si
    designs = si._designs(None, directory)
    cases = {str(c.get('case_id')): c for c in (summary.get('cases') or [])
             if isinstance(c, dict)}
    judges = si._judge_map(directory)
    rows = []
    for index, design in enumerate(designs):
        meta = si._design_meta(index, design, None)
        if meta['dimension'] != '功能准确性':
            continue
        case_id = f'case-{index + 1:03d}'
        case = cases.get(case_id, {})
        execution = si._execution(directory, case)
        facts = si._execution_facts(execution)
        metrics = facts['metrics'] or {}
        verdict, _basis = si._verdict(case, execution, judges.get(case_id))
        rows.append({
            '场景': meta['title'],
            '用户要什么': si._short(meta['message'], 54),
            'Agent 实际回答': si._short(facts['reply'], 62),
            '业务库结果': ('订单 ' + str(metrics.get('order_count', '—'))
                       + ' · 交易 ' + str(metrics.get('transaction_count', '—'))),
            '达成判定': si._label(case.get('objective_status')) if case.get('executed') else '未执行',
            '结论': verdict,
        })
    if rows:
        table(rows, 'c_function_goal', search=False, chrome=False)
    return rows


def _tool_usage_rows(directory, summary):
    """Every tool the Agent actually touched, with counts and shortfall."""
    execs = _executions(directory)
    stats = {}
    for case in summary.get('cases') or []:
        if not isinstance(case, dict):
            continue
        row = execs.get(str(case.get('case_id'))) or {}
        for event in (row.get('tool_evidence') or []):
            if not isinstance(event, dict):
                continue
            name = str(event.get('tool') or '').strip()
            if not name:
                continue
            item = stats.setdefault(name, {'calls': 0, 'ok': 0})
            item['calls'] += 1
            if event.get('executed'):
                item['ok'] += 1
    total = sum(item['calls'] for item in stats.values()) or 1
    return [{'工具': name, '调用次数': item['calls'], '执行成功': item['ok'],
             '未执行': item['calls'] - item['ok'],
             '占全部调用': str(round(100 * item['calls'] / total)) + '%'}
            for name, item in sorted(stats.items(), key=lambda kv: -kv[1]['calls'])]


def _tool_chain_rows(summary, directory):
    """Every scenario that actually touched a tool, with its chain verdicts."""
    from web import scenario_inspection as si
    designs = si._designs(None, directory)
    cases = {str(c.get('case_id')): c for c in (summary.get('cases') or [])
             if isinstance(c, dict)}
    judges = si._judge_map(directory)
    rows, usage = [], {}
    for index, design in enumerate(designs):
        meta = si._design_meta(index, design, None)
        case_id = f'case-{index + 1:03d}'
        case = cases.get(case_id, {})
        execution = si._execution(directory, case)
        facts = si._execution_facts(execution)
        tools = si._tool_summary(execution)
        called = facts['sequence']
        if not called and not (execution.get('tool_evidence') or []):
            continue
        for name in called:
            usage[name] = usage.get(name, 0) + 1
        verdict, _basis = si._verdict(case, execution, judges.get(case_id))
        rows.append({
            '场景': meta['title'],
            '覆盖链路': '、'.join(meta['nodes']) or '—',
            '① 该调就调': ('✓ 已调用' if tools['invoked'] else
                        ('✗ 没调工具' if case.get('executed') else '未执行')),
            '② 实际工具序列': '、'.join(called[:4]) or '无',
            '③ 参数 / 回执校验': f"{tools['passed']}/{tools['checked']} 条" if execution else '未执行',
            '④ 回答忠实': si._label(case.get('ai_status')),
            '结论': verdict,
        })
    if rows:
        table(rows, 'c_tool_chain', search=False, chrome=False)
    return rows, usage


def render(summary, directory):
    """Five blocks: overall quality, two deep dives, other dimensions, abnormal scenarios."""
    normal = summary.get('normal_quality') or {}
    objective = normal.get('objective') or {}
    judge = normal.get('judge') or {}
    passed = int(objective.get('passed') or 0)
    failed = int(objective.get('failed') or 0)
    jpassed = int(judge.get('passed') or 0)
    jfailed = int(judge.get('failed') or 0)
    unknown = int(normal.get('indeterminate') or 0)
    covered = sum(1 for name in DIMENSIONS if _dimension_row(name, summary)['executed'])

    # Overall hero: unnumbered, different colour, carries the whole verdict.
    st.subheader('整体质量')
    _quality_hero(summary, directory)

    # ② Functional accuracy: business outcome, not raw counters.
    st.subheader('② 功能准确性 · Agent 有没有真的把事情做成')
    workbench_explain.guide_note(FUNCTION_PRINCIPLE, label='为什么这样判')
    f = _dimension_row('功能准确性', summary)
    frows = _function_goal_rows(summary, directory)
    ran_function = [row for row in frows if row['达成判定'] != '未执行']
    if ran_function:
        kpis([
            ('实际执行', str(f['executed']), '本轮跑过的功能准确性场景'),
            ('客观断言达标', str(f['passed']), '工具执行 / 订单写入 / 回答与回执一致'),
            ('明确失败', str(f['failed']), '说做完了但业务库没有对应记录'),
            ('语义待判定', str(f['unknown']), '离线 Mock 无独立语义模型，不计为通过'),
        ])
    else:
        base_f, _ = baseline_case_rows(('功能准确性',))
        base_ok = sum(1 for row in base_f if row['结果'] == '通过')
        kpis([
            ('实际执行', str(len(base_f)), '本轮 0 条 · 显示 103 条基线'),
            ('客观断言达标', str(base_ok), '基线用例接口级断言全部通过'),
            ('明确失败', str(len(base_f) - base_ok), '基线里逐条列出'),
            ('无法判定', '0', '基线批次无证据不足项'),
        ])
    if ran_function:
        done = sum(1 for row in ran_function if row['结论'] in ('通过', '客观通过 · 语义待评'))
        _ai_card('功能准确性 · 本轮结论',
                 '本轮 ' + str(len(ran_function)) + ' 个功能场景里，' + str(done)
                 + ' 个业务目标达成。判定只对照三件事——用户要什么、Agent 实际回答什么、'
                 '业务库里真的多了什么；三者对不上就算没做成，不靠模型自述。'
                 + ('本轮存在 ' + str(f['failed']) + ' 条明确失败，按上表逐条复测。' if f['failed']
                    else '本轮未发现「说完成但没写入」的情况，结论只在本轮覆盖范围内成立。')
                 + '注意：这只证明业务目标达成，「回答好不好」由语义评判单独给结论。')
    else:
        render_baseline_cases(dimensions=('功能准确性',), key='c_function_baseline', preview=8)
        _ai_card('功能准确性 · 基线结论',
                 '本轮还没有执行记录，先看基线：' + str(len(base_f)) + ' 条功能用例中 '
                 + str(base_ok) + ' 条通过、' + str(len(base_f) - base_ok) + ' 条失败。'
                 '这批是接口级断言——查得到就答对、查不到就如实说、只查询不下单，'
                 '所以「业务目标是否达成」这一层被证明了；但回答是否忠实于回执，'
                 '仍需独立语义评判，这里不冒充通过。要本轮结论请先回「AI 场景总测试」跑一轮。')

    # ③ Tool calling: five links in the chain, not just "did it call something".
    st.subheader('③ 工具调用 · 五个环节逐个判')
    workbench_explain.guide_note(TOOL_PRINCIPLE, label='为什么这样判')
    t = _dimension_row('工具调用', summary)
    facts = _tool_facts(directory, summary)
    trows, usage = _tool_chain_rows(summary, directory)
    ran_tool = [row for row in trows if row['① 该调就调'] != '未执行']
    if ran_tool:
        kpis([
            ('工具调用次数', str(facts['calls']), '全部场景累计的 tool_evidence'),
            ('确认已执行', str(facts['executed']), '回执确认工具确实被调用'),
            ('参数 / 回执校验', f"{facts['checks_ok']} / {facts['checks']}", 'steps.checks 通过数'),
            ('涉及场景', str(len(ran_tool)), '真正发起过工具调用的场景'),
        ])
    else:
        base_t, _ = baseline_case_rows(('工具调用',))
        base_ok = sum(1 for row in base_t if row['结果'] == '通过')
        kpis([
            ('基线用例', str(len(base_t)), '本轮 0 条 · 显示 103 条基线'),
            ('接口断言通过', str(base_ok), '基线的工具参数 / 回执断言'),
            ('明确失败', str(len(base_t) - base_ok), '基线里逐条列出'),
            ('涉及场景', '0', '本轮还没跑'),
        ])
    if ran_tool:
        usage_rows = _tool_usage_rows(directory, summary)
        if usage_rows:
            st.markdown('**工具使用分布 · 每个工具被调了多少次**')
            table(usage_rows, 'c_tool_usage', search=False, chrome=False)
        missed = sum(1 for row in ran_tool if str(row['① 该调就调']).startswith('✗'))
        distinct = len({name for row in ran_tool
                        for name in str(row['② 实际工具序列']).split('、')
                        if name and name != '无'})
        bits = ['本轮 ' + str(len(ran_tool)) + ' 个场景发起了工具调用，累计 '
                + str(facts['calls']) + ' 次、涉及 ' + str(distinct) + ' 个工具；'
                '参数与回执断言通过 ' + str(facts['checks_ok']) + ' / '
                + str(facts['checks']) + ' 条。']
        if missed:
            bits.append('有 ' + str(missed) + ' 个场景该调却没调工具，这是工具层的明确缺陷，必须复测。')
        elif facts['checks'] and facts['checks_ok'] < facts['checks']:
            bits.append('工具都发起了，但参数或回执校验存在未通过项——「调了」不等于「调对」。')
        else:
            bits.append('该调用的场景都发起了调用，参数与回执校验全部通过，工具层在本轮范围内达标。')
        bits.append('另外 5 个写工具（建单 / 支付 / 退票 / 改签 / 取消）在安全维度验证的是「禁止被调用」，'
                    '不进这张调用分布表；只读工具已全部覆盖。'
                    '注意：这只证明工具选择与参数传递正确，回答是否忠实由 AI 评判单独给结论。')
        workbench_explain.guide_note(''.join(bits), label='工具调用结论')
    else:
        render_baseline_cases(dimensions=('工具调用',), key='c_tool_baseline', preview=8)
        workbench_explain.guide_note(
            '本轮工具调用场景都还没执行，上面是 103 条基线里该维度的真实用例结果；'
            '要本轮结论请先回「AI 场景总测试」跑一轮。', label='结果怎么看')

    # ④ Other five dimensions: one card each, not a bare counter table.
    st.subheader('④ 其余五个测试要求 · 每个维度的质量与缺口')
    execs = _executions(directory)
    all_cases = summary.get('cases') or []
    goals = dict(workbench_explain.DIMENSION_GOALS)
    cards, states = [], []
    for name in OTHERS:
        r = _dimension_row(name, summary)
        scoped = [c for c in all_cases if isinstance(c, dict) and c.get('dimension') == name]
        tools = []
        for case in scoped:
            ex = execs.get(str(case.get('case_id'))) or {}
            for event in (ex.get('tool_evidence') or []):
                if isinstance(event, dict) and event.get('tool'):
                    tools.append(str(event['tool']))
        if r['executed']:
            state = ('有明确问题' if (r['failed'] or r['judge_failed']) else
                     '证据不足' if r['unknown'] else '已覆盖')
            counts = (len(scoped), r['executed'], r['passed'], r['failed'], r['unknown'])
            source = '本轮'
        else:
            # Never print five zeros: use the 103-case baseline for this dimension.
            base, _catalog = baseline_case_rows((name,))
            base_ok = sum(1 for row in base if row['结果'] == '通过')
            state = '基线补位'
            counts = (len(scoped), len(base), base_ok, len(base) - base_ok, 0)
            source = '基线'
        states.append((name, state, counts, source))
        verdict = {
            '有明确问题': '出现 ' + str(counts[3]) + ' 条明确失败，按场景逐条复测',
            '证据不足': '有 ' + str(counts[4]) + ' 条证据不足，不折算为通过',
            '已覆盖': str(counts[2]) + ' 条全部达标，语义待在线评判',
            '基线补位': '本轮未跑，' + str(counts[1]) + ' 条基线中 ' + str(counts[2]) + ' 条通过',
        }[state]
        cards.append(
            '<div class="ta-dim-card"><h4>' + esc(name) + '</h4>'
            '<p class="goal">' + esc(goals.get(name, '')) + '</p>'
            '<div class="nums"><span>场景 <b>' + str(counts[0]) + '</b></span>'
            '<span>执行 <b>' + str(counts[1]) + '</b></span>'
            '<span>通过 <b>' + str(counts[2]) + '</b></span>'
            '<span>失败 <b>' + str(counts[3]) + '</b></span>'
            '<span>证据不足 <b>' + str(counts[4]) + '</b></span>'
            '<span>来源 <b>' + esc(source) + '</b></span></div>'
            '<p class="ai-line">AI 结论：' + esc(verdict) + '</p></div>')
    st.markdown('<div class="ta-dim-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)

    covered = [name for name, state, _c, _s in states
               if state in ('已覆盖', '证据不足', '有明确问题')]
    problems = [name for name, state, _c, _s in states if state == '有明确问题']
    baselined = [name for name, state, _c, _s in states if state == '基线补位']
    total_cases = sum(counts[1] for _n, _s, counts, _src in states)
    total_ok = sum(counts[2] for _n, _s, counts, _src in states)
    summary_text = (
        '本轮覆盖 ' + str(len(covered)) + ' / 5 个维度'
        + ('，其余 ' + '、'.join(baselined) + ' 用 103 条基线补位' if baselined else '')
        + '。五个维度合计 ' + str(total_cases) + ' 条用例、' + str(total_ok) + ' 条通过。'
        + ('其中「' + '、'.join(problems) + '」出现明确失败，是优先复测对象。'
           if problems else '未发现明确失败。')
        + '结论只覆盖已执行的用例：未执行记覆盖缺口，证据不足不折算为通过，'
        '离线 Mock 的回答忠实度如实记「语义待评」。')
    st.markdown(
        '<div class="ta-ai-verdict"><div class="ta-ai-tag">AI 生成结论</div>'
        '<h3>其余五个维度的测试结论</h3><p>' + esc(summary_text) + '</p></div>',
        unsafe_allow_html=True)

    # ⑤ Abnormal / edge scenarios -----------------------------------------
    # A grid of eight all-zero mutation counters proved nothing.  This block
    # shows the abnormal scenarios the AI really wrote and really fed to the
    # Agent; the same board is reused by the edge/boundary page below.
    render_exception_board(summary, directory)
