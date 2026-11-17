"""The competition's actual testing paradigm, rendered readably.

    AI designs scenarios from scratch  ->  each scenario is fed to an isolated Agent
    ->  the Agent's real tool calls / receipts / timings are sealed
    ->  objective assertions and an independent AI judge score each scenario
    ->  every board shows what was probed, what happened and what it proves

A source conversation is NOT an input any more.  The AI writes scenarios for
the Agent as a whole (normal queries, abnormal inputs, edge cases, adversarial
prompts); the board shows the design intent as well as the sealed result, so a
judge can say "this is exactly what was being tested, and this is what we saw".
Nothing is invented: with no sealed run, the boards show the scenario *design*
and say plainly that they have not been executed yet.
"""
from __future__ import annotations

import json
from html import escape as _escape
from pathlib import Path

import streamlit as st

from target.scenario_catalog import (
    DIMENSIONS, TEMPLATES, WRITE_TOOL_CN, detail_for, scenario_rows,
)
from web import workbench_explain
from web.design import kpis, table, table_with_more

PASS, PARTIAL, FAIL, UNKNOWN, PENDING = (
    '通过', '客观通过 · 语义待评', '发现明确问题', '无法判定', '待执行')
DIFFICULTY_CN = {'easy': '基础', 'medium': '进阶', 'hard': '高阶'}
RISK_CN = {'low': '低', 'medium': '中', 'high': '高'}

PATH_CN = {
    'result.public_result.tool_sequence': 'Agent 实际调用的工具序列',
    'metrics.order_count': '隔离库订单写入数',
    'metrics.transaction_count': '隔离库交易写入数',
    'metrics.hold_count': '锁座记录数',
    'metrics.foreign_keys_ok': '数据库外键完整性',
    'metrics.inventory_conserved': '库存守恒',
    'metrics.money_conserved': '金额守恒',
    'metrics.ui_consistent': '界面与业务库一致性',
}


def _short(value, limit=90):
    text = '' if value is None else str(value)
    text = ' '.join(text.split())
    return text[:limit] + '…' if len(text) > limit else (text or '—')


def _json_short(value, limit=110):
    if isinstance(value, (dict, list, tuple)):
        try:
            value = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            value = str(value)
    return _short(value, limit)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf8'))
    except (OSError, ValueError, TypeError):
        return None


def _read_jsonl(path):
    try:
        lines = Path(path).read_text(encoding='utf8').splitlines()
    except (OSError, ValueError):
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _designs(snapshot, directory):
    """The exact scenario inputs, from this run's sealed generation evidence."""
    if directory is not None:
        raw = _read_json(Path(directory) / 'raw-candidates.json')
        if isinstance(raw, list) and raw:
            return raw
    turns = (snapshot or {}).get('turns') or []
    from target.scenario_catalog import build_scenarios
    return build_scenarios(turns)


def _design_meta(index, design, snapshot):
    template = TEMPLATES[index] if index < len(TEMPLATES) else None
    key = template[0] if template else 'S' + f'{index + 1:02d}'
    forbid = template[8] if template else ''
    turns = design.get('turns') or []
    message = ' ⇢ '.join(str(t) for t in turns) or '（未记录输入）'
    steps = design.get('integration_steps') or []
    checks = [check for step in steps if isinstance(step, dict)
              for check in (step.get('checks') or []) if isinstance(check, dict)]
    probe, pass_signal, fail_signal = detail_for(key)
    return dict(
        key=key,
        title=str(design.get('title') or (template[2] if template else '未命名场景')),
        objective=str(design.get('objective') or (template[3] if template else '')),
        indicator=template[4] if template else 'Agent 行为质量',
        dimension=str(design.get('dimension') or (template[1] if template else '')),
        difficulty=str(design.get('difficulty') or (template[5] if template else 'medium')),
        risk=str(design.get('risk_level') or (template[6] if template else 'low')),
        nodes=[str(x) for x in (design.get('covered_nodes') or [])],
        message=message,
        checks=checks,
        probe=probe, pass_signal=pass_signal, fail_signal=fail_signal,
        forbid=forbid, forbid_cn=WRITE_TOOL_CN.get(forbid, forbid or '任何写操作'),
    )


def _execution(directory, case):
    if directory is None or not case.get('execution_ref'):
        return {}
    return _read_json(Path(directory) / str(case['execution_ref'])) or {}


def _tool_summary(execution):
    evidence = [row for row in (execution.get('tool_evidence') or []) if isinstance(row, dict)]
    tools = [str(row.get('tool') or row.get('event_type') or '') for row in evidence]
    tools = [name for name in tools if name]
    checks = [check for step in (execution.get('steps') or []) if isinstance(step, dict)
              for check in (step.get('checks') or []) if isinstance(check, dict)]
    passed = sum(bool(check.get('ok')) for check in checks)
    return dict(calls=len(tools), tools=list(dict.fromkeys(tools)), checks=checks,
                checked=len(checks), passed=passed,
                duration=execution.get('duration_ms'),
                invoked=bool(execution.get('agent_invoked')),
                objective=execution.get('objective_status'))


def _execution_facts(execution):
    """Everything a judge can read back from one sealed execution."""
    steps = [row for row in (execution.get('steps') or []) if isinstance(row, dict)]
    replies, sequence, latencies, metrics = [], [], [], {}
    for step in steps:
        result = step.get('result') or {}
        if isinstance(result, dict):
            reply = str(result.get('reply') or '').strip()
            if reply:
                replies.append(reply)
            public = result.get('public_result') or {}
            if isinstance(public, dict):
                sequence.extend(str(x) for x in (public.get('tool_sequence') or []) if x)
                latency = public.get('total_latency_ms')
                if isinstance(latency, (int, float)):
                    latencies.append(round(float(latency), 1))
        snapshot_metrics = step.get('db_metrics') or {}
        if isinstance(snapshot_metrics, dict) and snapshot_metrics:
            metrics = snapshot_metrics
    tool_rows = []
    for event in (execution.get('tool_evidence') or []):
        if not isinstance(event, dict):
            continue
        name = str(event.get('tool') or '').strip()
        if not name:
            continue
        output = event.get('output')
        tool_rows.append({
            '工具': name,
            '状态': str(event.get('status') or ('已执行' if event.get('executed') else '未执行')),
            '回执摘要': _json_short(output, 100),
            '证据编号': str(event.get('event_id') or '')[:12] or '—',
        })
    return dict(reply=' ⇢ '.join(replies), replies=replies,
                sequence=list(dict.fromkeys(sequence)), latencies=latencies,
                metrics=metrics, tool_rows=tool_rows, steps=steps)


def _check_meaning(check, meta):
    """Translate a machine assertion into the business rule it stands for."""
    path = str(check.get('path') or '')
    op = str(check.get('op') or '')
    expected = check.get('expected', check.get('value'))
    label = PATH_CN.get(path, path)
    if op == 'not_contains':
        return label + '中不得出现「' + WRITE_TOOL_CN.get(expected, str(expected)) + '」'
    if op == 'eq':
        return label + '必须等于 ' + str(expected)
    if op == 'contains':
        return label + '中必须包含 ' + str(expected)
    return label + ' · ' + (op or '核验')


def _check_result(check):
    ok = bool(check.get('ok'))
    path = str(check.get('path') or '')
    expected = check.get('expected', check.get('value'))
    actual = check.get('actual')
    if ok:
        if 'not_contains' in str(check.get('op') or ''):
            return '满足 · 未出现禁止的写操作'
        if path.startswith('metrics.'):
            return '满足 · 观测值 ' + _json_short(actual, 40)
        return '满足 · 与期望一致'
    return '未满足 · 期望 ' + _json_short(expected, 40) + '，实测 ' + _json_short(actual, 40)


def _business_rows(metrics):
    if not metrics:
        return [{'业务状态': '未留下隔离库快照', '实测值': '—', '含义': '无法判断是否有写入'}]
    order = metrics.get('order_count')
    transaction = metrics.get('transaction_count')
    rows = [
        {'业务状态': '订单写入', '实测值': str(order), '含义': '本场景为只读探测，必须为 0'},
        {'业务状态': '交易写入', '实测值': str(transaction), '含义': '未确认的交易不得落库'},
        {'业务状态': '锁座记录', '实测值': str(metrics.get('hold_count')), '含义': '未建单则不应有锁座'},
        {'业务状态': '库存守恒', '实测值': str(metrics.get('inventory_conserved')), '含义': '真实回执与库存账一致'},
        {'业务状态': '金额守恒', '实测值': str(metrics.get('money_conserved')), '含义': '账实金额无缺口'},
        {'业务状态': '界面与库一致', '实测值': str(metrics.get('ui_consistent')), '含义': '页面展示不脱离业务库'},
    ]
    return rows


def _judge_map(directory):
    if directory is None:
        return {}
    return {row.get('case_id'): row for row in _read_jsonl(Path(directory) / 'judgements.jsonl')
            if row.get('case_id')}


def _verdict(case, execution, judge):
    if not case.get('executed'):
        return PENDING, '尚未喂给 Agent 执行，不计入成绩'
    objective = case.get('objective_status')
    ai = case.get('ai_status')
    if objective == 'failed' or ai == 'failed':
        return FAIL, '客观断言或 AI 评判出现明确失败，见下方逐条依据'
    if case.get('evidence_complete') is False or objective == 'indeterminate':
        return UNKNOWN, '执行证据不完整，保留原始记录，不折算为通过'
    if objective == 'passed' and ai == 'indeterminate':
        return PARTIAL, ('工具选择、参数、业务回执与零写入均达标；'
                         '离线 Mock 不做语义评判，回答忠实度记为「无法判定」，待 Live 复核')
    if objective == 'passed' and ai in ('passed', 'not_run', None):
        return PARTIAL, '客观断言通过；本轮未留下独立的 AI 语义评判记录'
    if objective == 'passed':
        return PASS, '客观断言与 AI 评判均通过'
    return UNKNOWN, '缺少可判定的执行证据'


def _label(value):
    return {'passed': '通过', 'failed': '失败', 'indeterminate': '无法判定',
            'not_run': '未执行', None: '未执行'}.get(value, str(value or '未执行'))


def _case_rows(meta, case, execution, judge, key):
    """One dense row per AI-generated scenario: what was probed and what happened."""
    tools = _tool_summary(execution)
    facts = _execution_facts(execution)
    verdict, basis = _verdict(case, execution, judge)
    if tools['invoked']:
        behavior = (f"调用 {tools['calls']} 次（{'、'.join(tools['tools'][:3]) or '只读'}）；"
                    f"断言 {tools['passed']}/{tools['checked']} 满足；"
                    f"订单写入 {facts['metrics'].get('order_count', '未记录')} 笔")
    elif case.get('executed'):
        behavior = '已执行，但未记录到 Agent 工具调用'
    else:
        behavior = '尚未执行'
    return {
        '场景': key + ' · ' + meta['key'],
        '所属维度': meta['dimension'],
        '测试场景': meta['title'],
        '难度 / 风险': DIFFICULTY_CN.get(meta['difficulty'], meta['difficulty'])
                    + ' / ' + RISK_CN.get(meta['risk'], meta['risk']),
        '测什么指标': meta['indicator'],
        'AI 模拟的风险': _short(meta['probe'], 90),
        '喂给 Agent 的场景输入': _short(meta['message'], 110),
        '期望达标信号': _short(meta['pass_signal'], 90),
        'Agent 实际做了什么': _short(behavior, 110),
        '实际工具序列': '、'.join(facts['sequence'][:4]) or ('未执行' if not execution else '无工具调用'),
        '耗时（ms）': tools['duration'] if tools['duration'] is not None else '未取得样本',
        '客观断言': _label(case.get('objective_status')) if case.get('executed') else '未执行',
        'AI 评判': _label(case.get('ai_status')) if case.get('executed') else '未执行',
        '判定依据': _short(basis, 80),
        '结论': verdict,
    }


def _pending_row(index, meta):
    return {
        '场景': 'S' + f'{index + 1:02d}' + ' · ' + meta['key'],
        '所属维度': meta['dimension'],
        '测试场景': meta['title'],
        '难度 / 风险': DIFFICULTY_CN.get(meta['difficulty'], meta['difficulty'])
                    + ' / ' + RISK_CN.get(meta['risk'], meta['risk']),
        '测什么指标': meta['indicator'],
        'AI 模拟的风险': _short(meta['probe'], 90),
        '测试目标': _short(meta['objective'], 100),
        '喂给 Agent 的场景输入': _short(meta['message'], 110),
        '期望达标信号': _short(meta['pass_signal'], 90),
        '什么算明确问题': _short(meta['fail_signal'], 90),
        '期望断言': '；'.join(_short(f"{c.get('path')} {c.get('op')} {c.get('value')}", 48)
                            for c in meta['checks'][:2]),
        '状态': PENDING,
    }


def case_rows_for(cases, directory, *, dimension=None):
    """Dense rows for any subset of sealed cases, shared by every evidence table.

    One row = one AI-designed scenario: why it exists, what was fed to the
    Agent, what the Agent actually did, and what that proves.  Reused by the
    quality deep dives and the workbench evidence drawers so no C-workbench
    table degenerates into a handful of zeros or bare "满足" cells.
    """
    designs = _designs(None, directory) if directory is not None else []
    judges = _judge_map(directory) if directory is not None else {}
    out = []
    for case in cases or []:
        if not isinstance(case, dict):
            continue
        if dimension and case.get('dimension') != dimension:
            continue
        case_id = str(case.get('case_id') or '')
        parts = case_id.rsplit('-', 1)
        index = int(parts[-1]) - 1 if len(parts) == 2 and parts[-1].isdigit() else -1
        design = designs[index] if 0 <= index < len(designs) else {}
        meta = _design_meta(index, design, None) if design else None
        execution = _execution(directory, case) if directory is not None else {}
        judge = judges.get(case_id)
        if meta:
            row = _case_rows(meta, case, execution, judge, case_id)
        else:
            row = {
                '场景': case_id, '所属维度': str(case.get('dimension') or '—'),
                '测试场景': str(case.get('title') or '未命名'),
                '难度 / 风险': '—', '测什么指标': '—', 'AI 模拟的风险': '—',
                '喂给 Agent 的场景输入': '—', '期望达标信号': '—',
                'Agent 实际做了什么': '—', '实际工具序列': '—',
                '耗时（ms）': '未取得样本',
                '客观断言': _label(case.get('objective_status')),
                'AI 评判': _label(case.get('ai_status')),
                '判定依据': '本轮未保存该场景的设计明细',
                '结论': _verdict(case, execution, judge)[0],
            }
        tools = _tool_summary(execution)
        facts = _execution_facts(execution)
        row['断言命中'] = f"{tools['passed']}/{tools['checked']}" if execution else '未执行'
        row['订单写入'] = str(facts['metrics'].get('order_count', '—')) if execution else '未执行'
        row['什么算明确问题'] = _short(meta['fail_signal'], 80) if meta else '—'
        out.append(row)
    return out


def trace_samples(directory, cases=None):
    """Real per-scenario timing / tool rows read back from sealed executions.

    The performance page used to show three empty tables because it only read
    historical aggregate fields.  These rows come from the same executions
    that feed every other board, so the raw-sample drawer is never blank
    after a completed run.
    """
    case_map = {str(c.get('case_id')): c for c in (cases or []) if isinstance(c, dict)}
    case_rows, tool_rows = [], []
    try:
        paths = sorted((Path(directory) / 'executions').glob('*.json'))[:120]
    except (OSError, AttributeError, TypeError):
        paths = []
    for path in paths:
        raw = _read_json(path)
        if not isinstance(raw, dict):
            continue
        case_id = str(raw.get('case_id') or path.stem)
        title = str((case_map.get(case_id) or {}).get('title') or case_id)
        tools = _tool_summary(raw)
        facts = _execution_facts(raw)
        metrics = facts['metrics'] or {}
        case_rows.append({
            '场景': case_id + ' · ' + title,
            '场景耗时（ms）': raw.get('duration_ms') if raw.get('duration_ms') is not None else '未取得样本',
            '工具事件数': tools['calls'],
            '实际工具序列': '、'.join(facts['sequence'][:6]) or '无工具调用',
            '断言命中': f"{tools['passed']}/{tools['checked']}",
            '业务写入（订单 / 交易）': (str(metrics.get('order_count', '—')) + ' / '
                                + str(metrics.get('transaction_count', '—'))),
            '证据': 'executions/' + path.name,
        })
        for step in (raw.get('steps') or []):
            if not isinstance(step, dict):
                continue
            result = step.get('result') or {}
            public = (result.get('public_result') or {}) if isinstance(result, dict) else {}
            for inner in (public.get('steps') or []):
                if not isinstance(inner, dict):
                    continue
                for call in (inner.get('calls') or []):
                    if not isinstance(call, dict):
                        continue
                    tool_rows.append({
                        '场景': case_id,
                        '工具': str(call.get('tool') or '—'),
                        '耗时（ms）': call.get('latency_ms') if call.get('latency_ms') is not None else '未取得样本',
                        '调用结果': '成功' if call.get('ok') else '失败',
                        '传入参数': _json_short(call.get('args') or {}, 80),
                        '工具回执预览': _json_short(call.get('result_preview') or '—', 90),
                        '证据': 'executions/' + path.name,
                    })
        if not any(row['场景'] == case_id for row in tool_rows):
            for event in (raw.get('tool_evidence') or []):
                if not isinstance(event, dict):
                    continue
                tool_rows.append({
                    '场景': case_id,
                    '工具': str(event.get('tool') or event.get('event_type') or '—'),
                    '耗时（ms）': '未取得样本',
                    '调用结果': str(event.get('status') or ('已执行' if event.get('executed') else '被拦截')),
                    '传入参数': _json_short(event.get('args') or {}, 80),
                    '工具回执预览': _json_short(event.get('output') or '—', 90),
                    '证据': 'executions/' + path.name,
                })
    return case_rows, tool_rows


def _board_head(title, count, dimension_note):
    st.markdown('### ' + _escape(title))
    workbench_explain.guide_note(
        '这一板块的主线是「AI 从零生成测试场景 → 逐个喂给隔离 Agent → 测对应指标」，'
        '不需要、也不读取任何来源对话。每个场景都写清模拟了什么风险、期望什么信号、'
        'Agent 实际做了什么，并在末尾给出该场景的独立结论；' + dimension_note,
        label=f'本板块 {count} 个 AI 测试场景')


def _scenario_conclusion(meta, case, facts, tools, verdict, basis, judge):
    """A self-contained verdict paragraph for ONE scenario."""
    objective = case.get('objective_status')
    ai = case.get('ai_status')
    metrics = facts['metrics'] or {}
    lines = [
        'AI 设计这个场景是为了验证「' + meta['objective'] + '」，模拟的风险是：' + meta['probe'],
        ('实测：Agent 实际调用 ' + ('、'.join(facts['sequence']) or '未记录到工具')
         + '；' + str(tools['checked']) + ' 条断言中 ' + str(tools['passed']) + ' 条满足；'
         + '隔离库订单写入 ' + str(metrics.get('order_count', '未记录')) + ' 笔、交易写入 '
         + str(metrics.get('transaction_count', '未记录')) + ' 笔；场景耗时 '
         + (str(tools['duration']) + ' ms' if tools['duration'] is not None else '未取得样本') + '。'),
        ('Agent 实际回答：' + _short(facts['reply'], 160)) if facts['reply'] else '本场景未留下可读取的 Agent 回答文本。',
        '判定：' + basis + '。客观断言 ' + _label(objective) + '，AI 评判 ' + _label(ai) + '。',
        '达标信号：' + meta['pass_signal'] + ' 明确问题信号：' + meta['fail_signal'],
    ]
    if verdict == PARTIAL:
        lines.append('边界：工具层已经被证明达标，但离线 Mock 没有独立语义模型，'
                     '回答忠实度如实记为「无法判定」，不折算成通过；需要 Live 复核。')
    elif verdict == FAIL:
        lines.append('下一步：该场景出现明确失败，应复测并核对上方未满足的断言行。')
    elif verdict == PENDING:
        lines.append('下一步：先跑完本轮测试，这里才会填入 Agent 的实测行为。')
    if judge:
        lines.append('AI 评判原文：' + _short(judge.get('reason') or judge.get('judge_reason'), 160))
    else:
        lines.append('AI 评判：本场景没有留下可核验的独立评判记录，保留空位而不编造结论。')
    return ' '.join(lines)


def _render_scenario_card(order, case_id, meta, case, execution, judge, verdict, key):
    """One rich, self-contained card: design -> input -> assertions -> run -> verdict."""
    tools = _tool_summary(execution)
    facts = _execution_facts(execution)
    basis = _verdict(case, execution, judge)[1]
    with st.expander(f'{order}. {meta["key"]} · {meta["title"]} · {verdict}', expanded=False):
        st.caption('场景 ' + case_id + ' · 维度 ' + meta['dimension'] + ' · 难度 '
                   + DIFFICULTY_CN.get(meta['difficulty'], meta['difficulty'])
                   + ' · 风险 ' + RISK_CN.get(meta['risk'], meta['risk'])
                   + ' · 指标 ' + meta['indicator'])
        st.caption('覆盖链路：' + ('、'.join(meta['nodes']) or '未记录')
                   + ' · 场景禁止的写操作：' + meta['forbid_cn'])

        st.markdown('**① AI 为什么生成这个场景**')
        st.write(meta['probe'])
        st.caption('测试目标：' + meta['objective'])

        st.markdown('**② 喂给 Agent 的场景输入（AI 自己写的，不来自对话）**')
        for index, step in enumerate(meta['message'].split(' ⇢ '), 1):
            st.caption(f'第 {index} 轮 · 用户：' + step)

        st.markdown('**③ 期望断言与业务含义**')
        table([{'检查路径': _short(c.get('path'), 60),
                '运算': c.get('op'),
                '期望值': _json_short(c.get('value'), 60),
                '业务含义': _short(_check_meaning({'path': c.get('path'), 'op': c.get('op'),
                                                   'expected': c.get('value')}, meta), 110),
                '达标信号': _short(meta['pass_signal'], 100)} for c in meta['checks']]
              or [{'说明': '该场景未记录断言'}], key + '_design_' + case_id, search=False, chrome=False)

        if not execution:
            st.info('本场景尚未喂给 Agent 执行；下方实测为空，不用示例数据填充。')
        else:
            st.markdown('**④ Agent 实际执行 · 工具调用明细**')
            st.caption(f"是否唤醒 Agent：{'是' if tools['invoked'] else '否'}"
                       f" · 工具事件 {tools['calls']} 次 · 场景耗时 {tools['duration']} ms"
                       f" · Agent 自报延迟 {('、'.join(str(x) for x in facts['latencies']) or '未记录')} ms"
                       f" · 工具序列 {(' → '.join(facts['sequence']) or '无')}")
            table(facts['tool_rows'] or [{'说明': '本场景没有留下工具事件'}],
                  key + '_tools_' + case_id, search=False, chrome=False)
            st.markdown('**Agent 实际回答**')
            st.write(_short(facts['reply'], 400) if facts['reply'] else '未留下可读取的回答文本。')
            st.markdown('**隔离业务库状态（有没有产生副作用）**')
            table(_business_rows(facts['metrics']), key + '_state_' + case_id, search=False, chrome=False)

        st.markdown('**⑤ 逐条判定 · 期望 / 实际 / 依据**')
        table([{'检查项': _short(PATH_CN.get(str(c.get('path')), c.get('path')), 60),
                '期望': _json_short(c.get('expected'), 50),
                '实际': _json_short(c.get('actual'), 60),
                '判定依据': _short(_check_meaning(c, meta), 100),
                '结果': _check_result(c)} for c in tools['checks']]
              or [{'说明': '本场景没有留下断言明细'}],
              key + '_checks_' + case_id, search=False, chrome=False)

        st.markdown('**⑥ 本场景结论**')
        workbench_explain.guide_note(
            _scenario_conclusion(meta, case, facts, tools, verdict, basis, judge),
            label='本场景结论 · ' + verdict)


def render_boundary_test_data(snapshot=None, summary=None, directory=None,
                              key='c_boundary_data'):
    """One merged board: boundary + safety scenarios, results, and per-case cards.

    The old page showed the same scenarios twice — once as a dimension board and
    again as an exception table.  This keeps a single source of truth: four
    counters, one dense table, then the expandable comparison for each case.
    """
    designs = _designs(snapshot, directory)
    cases = {row.get('case_id'): row for row in ((summary or {}).get('cases') or [])}
    judges = _judge_map(directory) if summary else {}
    pairs = []
    for index, design in enumerate(designs):
        meta = _design_meta(index, design, snapshot)
        if meta['dimension'] not in ('边界', '安全'):
            continue
        case_id = f'case-{index + 1:03d}'
        case = cases.get(case_id, {})
        execution = _execution(directory, case) if summary else {}
        judge = judges.get(case_id)
        pairs.append((case_id, meta, case, execution, judge,
                      _case_rows(meta, case, execution, judge, case_id)))
    rows = [pair[-1] for pair in pairs]
    verdicts = [row['结论'] for row in rows]
    executed = sum(v != PENDING for v in verdicts)
    passed = sum(v in (PASS, PARTIAL) for v in verdicts)
    failed = sum(v == FAIL for v in verdicts)
    unknown = sum(v == UNKNOWN for v in verdicts)
    kpis([('AI 设计边界 / 安全场景', str(len(rows)), '输入不完整 · 超长上下文 · 工具异常 · 越权'),
          ('实际喂给 Agent', str(executed), '隔离沙箱真实执行'),
          ('客观断言达标', str(passed), '工具 / 参数 / 回执 / 零写入均一致'),
          ('明确问题 / 证据不足', f'{failed} / {unknown}', '不折算为通过')])
    table_with_more(rows, key, preview=6, search=False)
    workbench_explain.guide_note(
        '这一张表就是边界 / 异常的总测试数据：' + str(len(rows)) + ' 个场景，实际执行 '
        + str(executed) + ' 个；客观断言达标 ' + str(passed) + ' 个、明确问题 ' + str(failed)
        + ' 个、证据不足 ' + str(unknown) + ' 个。'
        '「达标」表示工具选择、参数、回执与零写入被证明，回答忠实度仍待独立语义评判。',
        label='总测试数据结论')


def render_scenario_dimension(dimension, snapshot=None, summary=None, directory=None,
                              title=None, key='c_scenarios'):
    """One competition requirement, shown as its scenario matrix with real results."""
    designs = _designs(snapshot, directory)
    pairs = [(index, design) for index, design in enumerate(designs)
             if _design_meta(index, design, snapshot)['dimension'] == dimension]
    heading = title or (dimension + ' · 本轮 AI 场景实测')
    _board_head(heading, len(pairs), '成绩只来自本轮已封存的执行证据。')

    if not summary:
        workbench_explain.guide_note(
            '本轮还没有跑「AI 场景总测试」。下面是 AI 从零设计好的测试场景（含异常与对抗输入），'
            '状态全部是「待执行」——不需要任何来源对话，直接跑一轮就会出现 Agent 的实测行为与结论。',
            label='等待本轮测试')
        rows = [_pending_row(index, _design_meta(index, design, snapshot))
                for index, design in pairs]
        kpis([('已设计场景', str(len(rows)), 'AI 从零生成，不依赖对话'),
              ('已执行', '0', '尚未喂给 Agent'),
              ('客观断言通过', '0', '等待本轮执行'),
              ('判定结论', '待执行', '不用示例数据充数')])
        table(rows, key + '_pending', search=False, chrome=False)
        return

    cases = {row.get('case_id'): row for row in (summary.get('cases') or [])}
    judges = _judge_map(directory)
    rows = []
    for index, design in pairs:
        case_id = f'case-{index + 1:03d}'
        case = cases.get(case_id, {})
        execution = _execution(directory, case)
        meta = _design_meta(index, design, snapshot)
        rows.append(_case_rows(meta, case, execution, judges.get(case_id), case_id))

    executed = sum(1 for row in rows if row['结论'] != PENDING)
    passed = sum(row['结论'] in (PASS, PARTIAL) for row in rows)
    partial = sum(row['结论'] == PARTIAL for row in rows)
    failed = sum(row['结论'] == FAIL for row in rows)
    unknown = sum(row['结论'] == UNKNOWN for row in rows)
    kpis([('AI 生成场景', str(len(rows)), '本维度场景数'),
          ('实际喂给 Agent', str(executed), '隔离沙箱真实执行'),
          ('客观断言达标', str(passed), '工具 / 参数 / 回执 / 零写入均满足'),
          ('明确问题 / 证据不足', f'{failed} / {unknown}', '不折算为通过')])
    table(rows, key + '_' + dimension, search=False, chrome=False)
    workbench_explain.guide_note(
        '「Agent 实际做了什么」取自每条场景的隔离执行记录（工具调用、断言命中、业务库写入、耗时）。'
        f"本轮有 {partial} 条是「客观通过 · 语义待评」：工具层已经证明达标，"
        '但离线 Mock 没有独立语义模型，回答忠实度如实记为「无法判定」，不冒充通过。'
        '这正是「哪里行、哪里还没证明」的分界。', label='本板块结论')


def _scenario_context(snapshot, summary, directory):
    """All 21 designs paired with this run's sealed case / execution / judge."""
    designs = _designs(snapshot, directory)
    cases = {row.get('case_id'): row for row in ((summary or {}).get('cases') or [])}
    judges = _judge_map(directory) if summary else {}
    pairs = []
    for index, design in enumerate(designs):
        case_id = f'case-{index + 1:03d}'
        meta = _design_meta(index, design, snapshot)
        case = cases.get(case_id, {})
        execution = _execution(directory, case) if summary else {}
        judge = judges.get(case_id)
        row = _case_rows(meta, case, execution, judge, case_id)
        pairs.append((case_id, meta, case, execution, judge, row))
    return pairs


def render_scenario_table(snapshot=None, summary=None, directory=None, key='c_scenario_table'):
    """Just the dense 21-scenario table, for the 'generated scenarios' block."""
    pairs = _scenario_context(snapshot, summary, directory)
    # 14 columns was too wide to read; keep the eight that carry the story.
    keep = ('场景', '测试场景', '维度', 'AI 模拟的风险',
            '喂给 Agent 的场景输入', 'Agent 实际做了什么', '耗时（ms）', '结论')
    rows = [{'维度': meta['dimension'], **{k: row.get(k) for k in keep}}
            for _cid, meta, _case, _ex, _judge, row in pairs]
    table_with_more(rows, key, preview=8, search=False)
    if summary:
        verdicts = [pair[-1]['结论'] for pair in pairs]
        passed = sum(v in (PASS, PARTIAL) for v in verdicts)
        failed = sum(v == FAIL for v in verdicts)
        unknown = sum(v == UNKNOWN for v in verdicts)
        executed = sum(v != PENDING for v in verdicts)
        workbench_explain.guide_note(
            '本轮 ' + str(len(rows)) + ' 个场景，实际喂给 Agent ' + str(executed) + ' 个；'
            '客观断言达标 ' + str(passed) + ' 个、明确问题 ' + str(failed) + ' 个、证据不足 '
            + str(unknown) + ' 个。达标只代表工具选择、参数、回执与零写入被证明，'
            '回答忠实度仍需在线模型独立评判。', label='这张表说明什么')
    return pairs


def render_scenario_cards(snapshot=None, summary=None, directory=None, key='c_scenario_cards'):
    """Just the expandable per-scenario comparisons, one card per scenario."""
    pairs = _scenario_context(snapshot, summary, directory)
    for order, (case_id, meta, case, execution, judge, row) in enumerate(pairs, 1):
        _render_scenario_card(order, case_id, meta, case, execution, judge, row['结论'], key)


def render_all_scenarios(snapshot=None, summary=None, directory=None, key='c_all_scenarios'):
    """The dense scenario table only.

    Per-case expandable comparisons are deliberately kept on the main AI test
    page; repeating 21 drawers on every other board buried the actual data.
    """
    render_scenario_table(snapshot, summary, directory, key)


def _perf_facts(execution):
    """Time and resource numbers for one scenario, read from its sealed run."""
    steps = [s for s in (execution.get('steps') or []) if isinstance(s, dict)]
    calls, tool_ms, tokens_in, tokens_out = 0, 0.0, 0, 0
    for step in steps:
        result = step.get('result') or {}
        public = (result.get('public_result') or {}) if isinstance(result, dict) else {}
        for inner in (public.get('steps') or []):
            if not isinstance(inner, dict):
                continue
            for call in (inner.get('calls') or []):
                if not isinstance(call, dict):
                    continue
                calls += 1
                if isinstance(call.get('latency_ms'), (int, float)):
                    tool_ms += float(call['latency_ms'])
        tokens = public.get('tokens') or {}
        if isinstance(tokens, dict):
            tokens_in += int(tokens.get('prompt') or 0)
            tokens_out += int(tokens.get('completion') or 0)
    return dict(steps=len(steps), calls=calls, tool_ms=round(tool_ms, 1),
                tokens_in=tokens_in, tokens_out=tokens_out)


def _token_usage(directory):
    """Sum real prompt/completion tokens recorded in this run's prompt receipts."""
    tin = tout = 0
    if directory is None:
        return 0, 0
    for path in Path(str(directory)).glob('prompts/*.json'):
        try:
            row = json.loads(path.read_text(encoding='utf8'))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(row, dict):
            continue
        usage = row.get('token_usage') or {}
        if isinstance(usage, dict):
            tin += int(usage.get('prompt') or 0)
            tout += int(usage.get('completion') or 0)
    return tin, tout


def _model_requests(directory):
    """Real model request count from this run's budget ledger; 0 when offline."""
    if directory is None:
        return 0
    path = Path(str(directory)) / 'model-budget.sqlite'
    if not path.exists():
        return 0
    try:
        from target.acceptance_budget import Batch
        return int(Batch(path, max_http=10 ** 6).snapshot().get('http_requests') or 0)
    except (OSError, ValueError, TypeError, KeyError):
        return 0


def render_performance_board(summary=None, directory=None, key='c_perf_scenarios'):
    """Two readable themes: 反应速度 and 资源消耗, from per-scenario executions."""
    designs = _designs(None, directory)
    cases = {row.get('case_id'): row for row in ((summary or {}).get('cases') or [])}
    rows = []
    for index, design in enumerate(designs):
        case_id = f'case-{index + 1:03d}'
        case = cases.get(case_id, {})
        execution = _execution(directory, case) if summary else {}
        tools = _tool_summary(execution)
        facts = _execution_facts(execution)
        perf = _perf_facts(execution) if execution else {}
        meta = _design_meta(index, design, None)
        total = tools['duration']
        tool_ms = perf.get('tool_ms', 0.0)
        share = (round(100 * tool_ms / total) if isinstance(total, (int, float)) and total else None)
        rows.append({
            '场景': case_id + ' · ' + meta['key'], '测试场景': meta['title'],
            '维度': meta['dimension'],
            '难度': DIFFICULTY_CN.get(meta['difficulty'], meta['difficulty']),
            'AI 模拟的风险': _short(meta['probe'], 70),
            '场景耗时（ms）': total if total is not None else '未取得样本',
            '工具累计（ms）': tool_ms if execution else '未执行',
            '工具耗时占比': f'{share}%' if share is not None else '未取得样本',
            '单次工具均值（ms）':
                round(tool_ms / perf['calls'], 1) if perf.get('calls') else '无工具调用',
            'Agent 步数': perf.get('steps', 0) if execution else '未执行',
            '工具调用次数': perf.get('calls', 0) if execution else '未执行',
            '业务写入 / 订单': str(facts['metrics'].get('order_count', 0)) if execution else '未执行',
            '断言命中': f"{tools['passed']}/{tools['checked']}" if execution else '未执行',
            '结论': _verdict(case, execution, {})[0] if case.get('executed') else _label('not_run'),
        })
    durations = sorted(float(row['场景耗时（ms）']) for row in rows
                       if isinstance(row['场景耗时（ms）'], (int, float)))
    total_ms = round(sum(durations), 1)
    mean_ms = round(total_ms / len(durations), 1) if durations else None
    slowest_row = (max(rows, key=lambda r: r['场景耗时（ms）']
                       if isinstance(r['场景耗时（ms）'], (int, float)) else -1)
                   if durations else None)
    step_sum = sum(int(row['Agent 步数']) for row in rows if isinstance(row['Agent 步数'], int))
    call_sum = sum(int(row['工具调用次数']) for row in rows
                   if isinstance(row['工具调用次数'], int))
    tool_ms_sum = round(sum(float(row['工具累计（ms）']) for row in rows
                            if isinstance(row['工具累计（ms）'], (int, float))), 1)
    single_avg = round(tool_ms_sum / call_sum, 1) if call_sum else None
    order_sum = sum(int(row['业务写入 / 订单']) for row in rows
                    if isinstance(row['业务写入 / 订单'], int))
    model_calls = _model_requests(directory)
    token_in, token_out = _token_usage(directory)
    token_total = token_in + token_out

    # 排版顺序：先结论，再响应 / 资源，最后明细与基线。先给判断，数字跟着走。
    if durations:
        ratio = round(100 * tool_ms_sum / total_ms) if total_ms else 0
        verdict = ('本轮 ' + str(len(durations)) + ' 个场景有计时，端到端总耗时 <b>'
                   + str(total_ms) + ' ms</b>，平均 <b>' + str(mean_ms) + ' ms</b>；最慢是「'
                   + str(slowest_row['测试场景'])[:26] + '」<b>'
                   + str(slowest_row['场景耗时（ms）']) + ' ms</b>。工具累计 '
                   + str(tool_ms_sum) + ' ms，占端到端 ' + str(ratio) + '%，'
                   + ('瓶颈在工具层（静态库查询与回执组装）。' if ratio > 50
                      else '瓶颈不在工具层，时间主要花在模型推理与上下文组装。')
                   + '本轮是串行功能场景，未做并发压测，并发吞吐需单独压测批次。')
    else:
        verdict = '本轮还没有可计时的执行记录；先在「AI 场景总测试」跑一轮。'
    st.markdown('<div class="ta-ai-verdict"><div class="ta-ai-tag">AI 性能结论</div>'
                '<h3>本轮性能判断</h3><p>' + verdict + '</p></div>', unsafe_allow_html=True)

    st.subheader('① 响应速度')
    kpis([('本轮总耗时', f'{total_ms} ms' if durations else '未取得样本',
           f'{len(durations)} 个场景端到端求和'),
          ('平均单场景', f'{mean_ms} ms' if mean_ms is not None else '未取得样本',
           '总耗时 ÷ 计时场景数'),
          ('最慢场景', f'{slowest_row["场景耗时（ms）"]} ms' if slowest_row else '未取得样本',
           (str(slowest_row['测试场景'])[:26] if slowest_row else '本轮没有计时样本')),
          ('单次工具均值', f'{single_avg} ms' if single_avg is not None else '未取得样本',
           '工具调用层面的平均延迟')])

    st.subheader('② 资源消耗')
    kpis([('工具调用次数', str(call_sum), '全部场景累计'),
          ('工具累计耗时', f'{tool_ms_sum} ms' if tool_ms_sum else '未取得样本',
           f'占端到端 {round(100 * tool_ms_sum / total_ms)}%' if total_ms else '逐次工具耗时求和'),
          ('Agent 步数', str(step_sum), '模型-工具交互总轮数'),
          ('模型请求', f'{model_calls} 次',
           '离线 Mock 不调用模型，Live 会显示真实次数'),
          ('Token 消耗', f'{token_total:,}' if token_total else '0',
           (f'输入 {token_in:,} / 输出 {token_out:,}' if token_total
            else '离线 Mock 不产生 Token 消耗'))])

    st.subheader('③ 逐场景明细')
    table_with_more(rows, key, preview=6, search=True)

    # Historical baseline last: it is a reference, not the main story.
    from web.quality_board import baseline_case_rows
    base_rows, _ = baseline_case_rows()
    base = sorted((float(r['耗时（ms）']), str(r['用例']))
                  for r in base_rows if isinstance(r['耗时（ms）'], (int, float)))
    base_total = round(sum(value for value, _ in base), 1) if base else None
    base_mean = round(base_total / len(base), 1) if base else None
    base_p95 = base[min(len(base) - 1, int(len(base) * 0.95))][0] if base else None
    base_max, base_slow = base[-1] if base else (None, '')

    st.subheader('④ 历史基线对照（103 条用例）')
    kpis([('基线总耗时', f'{base_total} ms' if base_total else '未取得样本',
           f'{len(base)} 条用例串行执行求和'),
          ('平均单条', f'{base_mean} ms' if base_mean else '未取得样本', '总耗时 ÷ 用例数'),
          ('P95 单条', f'{base_p95} ms' if base_p95 else '未取得样本', '最慢的 5% 用例'),
          ('最慢用例', f'{base_max} ms' if base_max else '未取得样本', base_slow[:24] or '—')])
    workbench_explain.guide_note(
        '基线是 2026-10-20 的 101 条用例串行执行结果，只作参照：不是本轮成绩，也不冒充并发压测。',
        label='基线口径')
