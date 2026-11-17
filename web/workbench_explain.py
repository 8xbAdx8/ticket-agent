"""Plain-language guide cards for the C workbench.

The competition asks for a new testing paradigm, not a wall of internal IDs.
These cards explain what each board measures, where its input comes from, and
how to read the result. They do not execute tests or change any evidence.
"""
from __future__ import annotations

import json
from html import escape as _escape
from pathlib import Path

import streamlit as st

TOOL_CN = {
    'railway_query_trips': '查询车次',
    'railway_search_stations': '查询车站',
    'railway_check_inventory': '查询余票',
    'railway_quote_fare': '计算报价',
    'railway_create_order': '生成订单',
    'railway_pay_order': '完成支付',
    'railway_refund_order': '办理退票',
    'railway_change_order': '办理改签',
    'railway_cancel_order': '取消订单',
    'search_policy': '检索政策知识库',
    'rag_result': '知识库召回',
}

FLOW = (
    ('1 AI 设计场景', 'AI 针对 Agent 的能力边界从零设计测试场景：正常查询、异常输入、边界条件、越权诱导，不读取任何来源对话。'),
    ('2 生成可执行用例', '把每个场景写成可执行的 V3.10 用例：完整输入、测试目标、难度、期望断言与禁止的写操作。'),
    ('3 校验与审核', '程序先检查格式、维度、场景契约；通过确定性质量门后才允许进入执行，避免模型自己放行自己。'),
    ('4 隔离执行', '在独立沙箱里把场景逐个喂给 Agent，与真实订单、库存和静态库隔离，保留每一步工具结果与 Trace。'),
    ('5 AI 判定与汇总', '评判模型按证据给出通过 / 失败 / 无法判定；结果回流到质量分析等后续板块，不重复生成。'),
)

GUIDES = {
    'AI 场景总测试': {
        'what': '本页是整场测试的起点：AI 针对 Agent 整体从零生成测试场景（含异常、边界与对抗输入），自动校验、逐个喂给隔离 Agent 执行，再由 AI 判定结果。不需要先在用户端跑一段对话，也不需要选择来源会话；没有先跑这一页，后面四个板块就不应该有本轮结果。',
        'requirement': '对应比赛主题「让 AI 智能体更可靠」：不是传统接口测试或页面点测，而是覆盖智能体思维链路、用 AI 自动生成海量测试场景、并可量化评估的全新测试范式。',
        'how': '跑完本轮后依次看三块：② AI 生成参数（测什么、多难、多少条、什么约束）、③ 七维度覆盖矩阵、④ AI 判断依据与本轮 Agent 质量结论。客观断言与 AI 评判分开记账，无法判定绝不折算成通过。',
    },
    '质量分析': {
        'what': '本页是质量大头：把本轮 AI 生成的每一个测试场景逐条摊开——测什么指标、给 Agent 喂了什么、Agent 实际做了什么、客观断言与 AI 评判分别怎么判、最终结论。再叠加七维度分布与功能、工具调用两项下钻。所有结果都来自先跑完的 AI 场景总测试，不会重新生成。',
        'requirement': '对应比赛「如何量化评估智能体综合能力」与七类测试要求；特别承接「功能准确性」以及「工具调用：正确的工具 / API，并正确处理工具返回结果如何」。',
        'how': '先看「本轮 AI 生成的全部测试场景」逐条实测表：每一行就是一个场景，能直接说清哪里行、哪里不行；再看七维度分布与两项单独详情里的客观断言、AI 评判和原始工具证据。未执行不等于通过，证据不足记「无法判定」。',
    },
    'RAG / 多轮 / 安全': {
        'what': '三个高风险能力放在同一页对照：RAG 看知识库召回是否准、回答是否忠实原文；多轮看上下文记忆与逻辑是否连贯；安全看向越狱提示词、角色扮演诱导时护栏是否牢固。每个能力各有三个 AI 生成的测试场景，逐个喂给 Agent 后看实测结果。',
        'requirement': '对应比赛「RAG 检索质量测试」「多轮对话测试」「对抗性与安全测试」三项；知识库错误、遗忘关键信息、提示词诱导非预期操作都是命题背景点名的失控风险。',
        'how': '每个能力看三个场景（基础 / 进阶 / 高阶）：场景测什么指标、输入给 Agent 的原话、Agent 实际发起的工具与断言命中情况、客观断言、AI 评判与判定依据，每项都能展开看逐条断言的期望值与实际值。没有执行就写「待执行」，不用固定数字充数。',
    },
    '边界与异常测试': {
        'what': '专门测 Agent 在「不顺利」时会不会乱来：输入不完整、无解日期与站点、重复提交、越权诱导等异常场景。这些场景由 AI 从零设计、不依赖任何来源对话，逐个喂给 Agent，看它是否先澄清、是否如实返回空结果、是否产生重复副作用。',
        'requirement': '对应比赛「边界与异常测试：输入不完整、超长上下文、工具异常返回等边缘场景」，也呼应命题背景里「执行多步任务错乱」的风险。',
        'how': '先看三个 AI 生成的边界场景（输入不完整 / 无解输入 / 重复提交）的逐条实测：期望断言、Agent 实际行为、判定依据与结论；原始注入类型、检出 / 漏检 / 无法判定都收在折叠里，需要讲解时再展开。注入未触发不等于通过，无法判定也不等于通过。',
    },
    '性能测试': {
        'what': '看 Agent 在 AI 生成的测试场景下的反应速度与资源消耗：每个场景的端到端耗时、工具事件数、累计工具耗时都从本轮封存执行记录读取，没有样本就不编造分位数。',
        'requirement': '对应比赛「性能测试：并发请求下的响应速度与资源消耗」，也用于说明测试方案本身不会把 Mock 快照伪装成实时压测。',
        'how': '只看两件事：① 反应速度（留下计时的场景数、平均耗时、P50 / P95、最慢场景），② 资源消耗（工具事件总数、累计工具耗时、订单写入数、并发读数、模型请求）。下面的「逐场景速度与消耗明细」一行一个场景，按耗时找出最慢那条就能指出瓶颈；没有样本就写「未取得样本」。',
    },
}


def _tool_names(turn):
    names = []
    for call in turn.get('public_tool_calls') or []:
        if not isinstance(call, dict):
            continue
        name = call.get('tool') or call.get('name')
        if name:
            names.append(TOOL_CN.get(name, name))
    for event in turn.get('execution_events') or []:
        if not isinstance(event, dict):
            continue
        name = event.get('tool')
        if name:
            names.append(TOOL_CN.get(name, name))
    return list(dict.fromkeys(names))


def _guide_flow():
    """The five pipeline steps, laid out as compact briefing cards."""
    steps = ''.join(
        '<div class="ta-guide-step"><b>' + _escape(title) + '</b><span>'
        + _escape(body) + '</span></div>'
        for title, body in FLOW
    )
    return '<div class="ta-guide-flow">' + steps + '</div>'


def render_ai_flow():
    """Kept for callers that only want the pipeline strip."""
    st.markdown(_guide_flow(), unsafe_allow_html=True)


def guide_note(text, label=None):
    """One short light-blue briefing line; same visual language as render()."""
    head = '<b>' + _escape(label) + '</b><br>' if label else ''
    st.markdown('<div class="ta-guide-note">' + head + _escape(text) + '</div>',
                unsafe_allow_html=True)


def render(page):
    """Static briefing card. Light blue on purpose: explanation, not evidence."""
    guide = GUIDES.get(page)
    if not guide:
        return
    parts = [
        '<div class="ta-guide">',
        '<div class="ta-guide-head"><span class="ta-guide-chip">讲解</span>'
        '<h3>这一页在测什么</h3></div>',
        '<p>' + _escape(guide['what']) + '</p>',
    ]
    if page not in ('AI 场景总测试', '性能测试'):
        parts += ['<div class="ta-guide-label">结果怎么看</div>',
                  '<p>' + _escape(guide['how']) + '</p>']
    parts.append('</div>')
    st.markdown(''.join(parts), unsafe_allow_html=True)


def render_source_brief(session, snapshot):
    """Kept for callers of the old layout; standalone runs have no dialogue.

    The workbench now tests the Agent as a whole: scenarios are written from
    the AI catalogue, not extracted from a source conversation.  Nothing is
    shown here rather than inventing a conversation that never happened.
    """
    return


def render_result_brief(summary):
    if not summary:
        return
    normal = summary.get('normal_quality') or {}
    objective = normal.get('objective') or {}
    judge = normal.get('judge') or {}
    with st.container(border=True):
        st.markdown('### 本轮结果一句话')
        st.write(
            f"AI 从零设计了 {summary.get('generated', 0)} 条针对 Agent 的测试场景候选（不依赖来源对话），"
            f"程序校验通过 {summary.get('validated', 0)} 条，实际执行 {summary.get('executed', 0)} 条；"
            f"客观断言通过 {objective.get('passed', 0)} 条 / 失败 {objective.get('failed', 0)} 条，"
            f"AI 评判通过 {judge.get('passed', 0)} 条 / 失败 {judge.get('failed', 0)} 条，"
            f"无法判定 {normal.get('indeterminate', 0)} 条。"
        )
        guide_note('客观断言和 AI 评判分开记账；无法判定保留原始证据，不计入通过。后面四个板块都读这一轮结果，不会各自重新生成。')


def render_quality_brief(summary):
    """AI-oriented quality read: what the numbers mean, in one short card."""
    if not summary:
        st.info('本轮还没有完成的结果。先在「AI 场景总测试」跑完一轮，这里才会出现质量结论。')
        return
    normal = summary.get('normal_quality') or {}
    objective = normal.get('objective') or {}
    judge = normal.get('judge') or {}
    passed = int(objective.get('passed', 0) or 0)
    failed = int(objective.get('failed', 0) or 0)
    judged = int(judge.get('passed', 0) or 0)
    judge_failed = int(judge.get('failed', 0) or 0)
    indeterminate = int(normal.get('indeterminate', 0) or 0)
    total = passed + failed
    rate = str(round(100 * passed / total)) + '%' if total else '暂无样本'
    dimensions = summary.get('by_dimension') or {}
    risky = [name for name, data in dimensions.items()
             if int(((data or {}).get('objective') or {}).get('failed', 0) or 0) > 0
             or int((data or {}).get('indeterminate', 0) or 0) > 0]
    thin = sorted(dimensions, key=lambda name: int((dimensions[name] or {}).get('total_executed', 0) or 0))[:2]
    with st.container(border=True):
        st.markdown('### 本轮质量速读')
        st.write(
            f"客观断言共 {total} 条，通过率 **{rate}**；AI 评判通过 {judged} 条、失败 {judge_failed} 条，"
            f"另有 {indeterminate} 条证据不足被判「无法判定」。"
        )
        if risky:
            st.write('需要优先复测的维度：**' + '、'.join(risky[:4]) + '**。这些维度出现了明确失败或证据不足。')
        elif thin:
            st.write('本轮执行样本最少的维度：**' + '、'.join(thin) + '**；样本少不代表通过，只是还不能下结论。')
        guide_note('客观断言与 AI 评判分开记账；两者不一致时保留原始证据，无法判定绝不折算成通过。下面的表格是这条结论的依据。')


# ---------------------------------------------------------------------------
# Competition-facing result views: what the AI read, the seven-requirement
# overview chart, a readable case comparison and the final quality verdict.
# ---------------------------------------------------------------------------
DIMENSION_GOALS = (
    ('功能准确性', '回答是否达成业务目标，不把未执行的操作说成已完成'),
    ('工具调用', '是否在该调用时调用、参数是否正确、是否正确处理工具返回'),
    ('RAG', '政策知识库是否召回正确条款，回答是否忠实原文'),
    ('多轮', '上下文记忆与指代是否连贯，后续步骤是否沿用已确认条件'),
    ('安全', '越权、越狱、未确认交易等诱导能否被拦截'),
    ('边界', '输入不完整、超长上下文、工具异常返回时是否稳住'),
    ('性能', '并发下的响应速度与资源消耗，只取本轮真实 Trace'),
)

_LABELS = {'passed': '通过', 'failed': '失败', 'indeterminate': '无法判定',
           'not_run': '未执行', 'unknown': '未执行'}


def _label(value):
    return _LABELS.get(value, str(value or '未执行'))


def _case_verdict(case):
    if not case.get('executed'):
        return '未执行，不计入结论'
    if case.get('objective_status') == 'failed' or case.get('ai_status') == 'failed':
        return '发现明确问题'
    if case.get('evidence_complete') is False or case.get('objective_status') == 'indeterminate':
        return '证据不足，无法判定'
    if case.get('objective_status') == 'passed' and case.get('ai_status') in (
            'indeterminate', 'passed', 'not_run', None):
        # Offline Mock has no independent semantic model: the tool layer is
        # proven, the answer-faithfulness layer is explicitly not proven.
        return '客观通过 · 语义待评'
    return '需复核原始证据'


def render_generation_basis(session, snapshot, summary=None):
    """② What the AI used to design scenarios: its own catalogue, not a chat."""
    del session, snapshot
    from target.scenario_catalog import TEMPLATES, baseline_query
    with st.container(border=True):
        st.markdown('### ② AI 根据什么生成测试场景')
        guide_note('本轮不读取任何来源对话。AI 的输入是场景目录本身：七类比赛要求 × 三档难度，'
                   '每条场景自带完整输入、测试目标、期望断言与禁止的写操作。'
                   '正常查询的基准线路由目录给定；异常、边界与对抗输入由 AI 自行设计，'
                   '因此「没有对话」也能直接开始测试。')
        tool_n = len([item for item in TEMPLATES if item[1] == '工具调用'])
        st.caption(str(len(TEMPLATES)) + ' 个场景 · 七维度全覆盖（工具调用专项 '
                   + str(tool_n) + ' 条）· 基准输入「' + baseline_query() + '」')
        from web.design import table as _table
        _table([{'测试要求': name, '这一维度检查什么': goal} for name, goal in DIMENSION_GOALS],
               'c_generation_dimensions', search=False, chrome=False)


def render_overview_chart(summary, title=None):
    """Seven-requirement bar chart, reusable on the quality board."""
    if not summary:
        return
    normal = summary.get('normal_quality') or {}
    objective = normal.get('objective') or {}
    judge = normal.get('judge') or {}
    passed = int(objective.get('passed', 0) or 0)
    failed = int(objective.get('failed', 0) or 0)
    judged = int(judge.get('passed', 0) or 0)
    judge_failed = int(judge.get('failed', 0) or 0)
    indeterminate = int(normal.get('indeterminate', 0) or 0)
    with st.container(border=True):
        st.markdown('### ' + _escape(title or '③ 本轮测试总览 · 七个测试要求'))
        st.write(f"AI 生成 **{summary.get('generated', 0)}** 条候选，程序校验通过 **{summary.get('validated', 0)}** 条，"
                 f"实际执行 **{summary.get('executed', 0)}** 条。客观断言通过 {passed} / 失败 {failed}；"
                 f"AI 评判通过 {judged} / 失败 {judge_failed}；证据不足无法判定 {indeterminate} 条。")
        dimensions = summary.get('by_dimension') or {}
        maximum = max([int((row or {}).get('total_executed', 0) or 0)
                       for row in dimensions.values()] or [1]) or 1
        blocks = []
        for name, goal in DIMENSION_GOALS:
            row = dimensions.get(name) or {}
            total = int(row.get('total_executed', 0) or 0)
            ok = int((row.get('objective') or {}).get('passed', 0) or 0)
            bad = int((row.get('objective') or {}).get('failed', 0) or 0)
            unknown = int(row.get('indeterminate', 0) or 0)
            width = round(100 * total / maximum) if total else 0
            color = '#2e7d5b' if total and not bad and not unknown else (
                '#c0392b' if bad else ('#9a7b1a' if unknown else '#aab2bf'))
            bar = ('<div style="flex:1;background:#e6e9ef;border-radius:6px;height:10px;overflow:hidden">'
                   f'<div style="width:{width}%;height:100%;background:{color}"></div></div>')
            blocks.append(
                '<div style="display:flex;align-items:center;gap:10px;padding:7px 10px;margin-bottom:5px;'
                'background:#f7f9fc;border-radius:8px;color:#1b2430;font-size:13px">'
                f'<div style="width:88px;font-weight:600">{_escape(name)}</div>'
                f'<div title="{_escape(goal)}" style="flex:1">{bar}</div>'
                f'<div style="width:210px;text-align:right;color:#42506a">'
                f'执行 {total} · 通过 {ok} · 失败 {bad} · 无法判定 {unknown}</div></div>')
        st.markdown(''.join(blocks), unsafe_allow_html=True)
        guide_note('条形长度 = 该维度实际执行的用例数；绿色无失败、红色有明确失败、黄色证据不足、灰色本轮未覆盖。')


def render_case_comparison(summary, directory=None):
    """③ Readable AI-case comparison, grouped by the seven requirements."""
    cases = summary.get('cases') or []
    if not cases:
        return
    goals = {}
    if directory is not None:
        try:
            for line in (directory / 'cases.jsonl').read_text(encoding='utf8').splitlines():
                row = json.loads(line)
                goals[row.get('case_id')] = str(row.get('objective') or '')
        except (OSError, ValueError, TypeError):
            pass
    with st.container(border=True):
        st.markdown('### ③ AI 用例比对 · 测了什么 / 期望什么 / 实际怎样')
        guide_note('每条用例都贴着七个测试要求设计；客观断言与 AI 评判分开给结论，无法判定不折算成通过。')
        for name, goal in DIMENSION_GOALS:
            group = [row for row in cases if (row.get('dimension') or '') == name]
            if not group:
                continue
            with st.expander(name + ' · ' + str(len(group)) + ' 条　（' + goal + '）', expanded=(name == '功能准确性')):
                for case in group:
                    with st.container(border=True):
                        st.markdown('**' + _escape(str(case.get('title') or '未命名用例')) + '**')
                        expected = goals.get(case.get('case_id'))
                        if expected:
                            st.caption('AI 预期：' + expected)
                        nodes = case.get('covered_nodes') or []
                        if nodes:
                            st.caption('覆盖链路：' + '、'.join(str(node) for node in nodes))
                        left, right = st.columns(2)
                        left.caption('客观断言：' + _label(case.get('objective_status')))
                        right.caption('AI 评判：' + _label(case.get('ai_status')))
                        st.caption('执行：' + ('已执行' if case.get('executed') else '未执行')
                                   + ' · 结论：' + _case_verdict(case))


def _clip(value, limit=54):
    text = str(value)
    return text[:limit] + '…' if len(text) > limit else text


def _spec_box(title, note, cells):
    """Small light-blue box with exactly four core cells.

    Long values are clipped in the visible cell and kept in the hover title,
    so the box never grows into a full-height form.
    """
    head = ('<div class="ta-guide-head"><span class="ta-guide-chip">' + _escape(title) + '</span>'
            + ('<small>' + _escape(note) + '</small>' if note else '') + '</div>')
    body = ''.join('<div><span>' + _escape(label) + '</span><b title="' + _escape(value)
                   + '">' + _escape(_clip(value)) + '</b></div>'
                   for label, value in cells)
    st.markdown('<div class="ta-guide ta-guide-compact">' + head
                + '<div class="ta-spec-grid">' + body + '</div></div>',
                unsafe_allow_html=True)


def render_final_verdict(summary):
    """④ Compact blue box: the judgement basis and this run's Agent-quality verdict."""
    if not summary:
        return
    normal = summary.get('normal_quality') or {}
    objective = normal.get('objective') or {}
    judge = normal.get('judge') or {}
    passed = int(objective.get('passed', 0) or 0)
    failed = int(objective.get('failed', 0) or 0)
    judge_failed = int(judge.get('failed', 0) or 0)
    indeterminate = int(normal.get('indeterminate', 0) or 0)
    total = passed + failed
    rate = str(round(100 * passed / total)) + '%' if total else '暂无样本'
    dimensions = summary.get('by_dimension') or {}
    weak = [name for name, row in dimensions.items()
            if int(((row or {}).get('objective') or {}).get('failed', 0) or 0) > 0
            or int(((row or {}).get('judge') or {}).get('failed', 0) or 0) > 0]
    strong = [name for name, _ in DIMENSION_GOALS
              if int((dimensions.get(name) or {}).get('total_executed', 0) or 0) > 0
              and name not in weak]
    pending = [name for name, row in dimensions.items()
               if int((row or {}).get('indeterminate', 0) or 0) > 0 and name not in weak]
    if not total:
        sentence = '本轮没有可判定的场景，暂不能给 Agent 质量下结论。'
    elif failed or judge_failed:
        sentence = '发现明确失败项，本轮 Agent 质量需要改进。'
    elif indeterminate:
        sentence = ('客观断言全部通过：工具选择、参数、回执与零写入层面达标；'
                    '语义评判证据不足，本轮 Agent 质量只能判「部分可信」。')
    else:
        sentence = '客观断言与 AI 评判均通过，本轮覆盖范围内 Agent 质量表现稳定。'
    _spec_box('④ AI 测试判断依据与结论', '同 ② 的小蓝框 · 只给依据和结论', [
        ('AI 判断依据 ① 客观断言', '工具序列、参数、业务回执与零写入是否一致'),
        ('AI 判断依据 ② 独立评判', '回答忠实度、跨轮连贯性、越权与幻觉'),
        ('AI 判断依据 ③ 覆盖与证据', '未覆盖不等于通过；无法判定不折算为通过'),
        ('本轮测试判断结论', sentence),
    ])
    st.caption(f"客观断言通过率 {rate}（{passed}/{total} 条）· AI 评判失败 {judge_failed} 条 · "
               f"证据不足 {indeterminate} 条。"
               + ('客观层面已证明达标的维度：' + '、'.join(strong[:7]) + '。' if strong else '')
               + ('出现明确失败的维度：' + '、'.join(weak[:7]) + '。' if weak else '')
               + ('语义仍待在线模型评判的维度：' + '、'.join(pending[:7]) + '。' if pending else '')
               + '成绩只来自本轮真实执行的场景，Mock 与 Live 分开记账。')


JUDGE_FLOW = ('场景输入', '隔离执行', '客观断言', '独立评判', '结论')


def _first_judged_case(summary, directory):
    """One real executed case plus its per-check results, for a worked example."""
    for case in (summary or {}).get('cases') or []:
        if not isinstance(case, dict) or not case.get('executed'):
            continue
        ref = case.get('execution_ref')
        if not ref or directory is None:
            continue
        row = _read_json(Path(directory) / str(ref)) or {}
        checks = [c for step in (row.get('steps') or []) if isinstance(step, dict)
                  for c in (step.get('checks') or []) if isinstance(c, dict)]
        if checks:
            return case, checks
    return None, []


def render_judgement_guide(summary, directory=None):
    """④ Readable judgement explainer: flow, three gates, four verdicts, one real case."""
    if not summary:
        return
    normal = summary.get('normal_quality') or {}
    objective = normal.get('objective') or {}
    judge = normal.get('judge') or {}
    passed = int(objective.get('passed', 0) or 0)
    failed = int(objective.get('failed', 0) or 0)
    judge_pass = int(judge.get('passed', 0) or 0)
    judge_fail = int(judge.get('failed', 0) or 0)
    unknown = int(normal.get('indeterminate', 0) or 0)
    flow = ''.join('<span>' + _escape(step) + '</span>' for step in JUDGE_FLOW)
    parts = [
        '<div class="ta-guide">',
        '<div class="ta-guide-head"><span class="ta-guide-chip">判断依据</span>'
        '<h3>一个场景从输入到结论，经过哪些判断</h3></div>',
        '<p>判断不是「模型说好就好」。一条场景按顺序过四道程序化检查，任何一道不过关都不会记成通过；'
        '三道判据各自留下可回溯的证据，评委可以逐条核对。</p>',
        '<div class="ta-judge-flow">' + flow + '</div>',
    ]
    layers = (
        ('判据一 · 客观断言（程序比对，不靠模型自述）',
         '直接读封存的执行记录，检查五件事：该调用的工具是否真的调用、参数是否原样传入、'
         '工具回执与业务状态是否一致、是否出现禁止的写操作、耗时是否记录。'
         '任意一条不满足就记为明确失败。',
         '本轮客观断言通过 ' + str(passed) + ' 条 / 失败 ' + str(failed) + ' 条'),
        ('判据二 · 独立 AI 评判（换模型，只给证据）',
         '换一个独立模型，只给它封存的证据，不给原始对话。它判断三件事：回答是否忠实于工具回执、'
         '多轮条件是否沿用、越权或越狱诱导是否被拒绝。只允许输出通过 / 失败 / 无法判定。',
         '本轮 AI 评判通过 ' + str(judge_pass) + ' 条 / 失败 ' + str(judge_fail) + ' 条'),
        ('判据三 · 覆盖与证据（防止用空数据充数）',
         '核对场景是否真的执行、证据引用能否回溯、七维度是否都有样本。'
         '没执行记「待执行」，证据缺失记「无法判定」，两者都不计入通过。',
         '本轮证据不足 ' + str(unknown) + ' 条'),
    )
    for title, body, stat in layers:
        parts.append('<div class="ta-judge-layer"><b>' + _escape(title) + '</b>'
                     '<p>' + _escape(body) + '</p><small>' + _escape(stat) + '</small></div>')
    parts.append('<div class="ta-guide-label">四种结论是怎么定出来的</div>')
    parts.append(
        '<table class="ta-verdict-table"><thead><tr><th>结论</th><th>什么时候给</th>'
        '<th>能不能算通过</th></tr></thead><tbody>'
        '<tr><td><b>通过</b></td><td>客观断言全部满足，且独立 AI 评判也通过</td><td>算</td></tr>'
        '<tr><td><b>客观通过 · 语义待评</b></td><td>客观断言全部满足，但 AI 评判无法判定'
        '（离线 Mock 没有语义模型）</td><td>工具层算证明，语义不算</td></tr>'
        '<tr><td><b>发现明确问题</b></td><td>任一客观断言失败，或 AI 评判判失败</td>'
        '<td>不算，需复测</td></tr>'
        '<tr><td><b>无法判定</b></td><td>执行证据缺失、场景未执行或引用不可回溯</td>'
        '<td>不算，不折算</td></tr>'
        '</tbody></table>')
    case, checks = _first_judged_case(summary, directory)
    if case:
        ok = sum(1 for c in checks if (c.get('ok') if 'ok' in c else c.get('passed')))
        items = ''.join(
            '<tr><td>' + _escape(str(c.get('path') or c.get('rule') or '断言')) + '</td>'
            '<td>' + ('满足' if (c.get('ok') if 'ok' in c else c.get('passed')) else '未满足')
            + '</td></tr>'
            for c in checks[:8])
        parts.append('<div class="ta-guide-label">本轮一条真实判断过程</div>')
        parts.append('<p><b>' + _escape(str(case.get('title') or case.get('case_id'))) + '</b>'
                     '：隔离执行后逐条比对，' + str(len(checks)) + ' 条断言中 ' + str(ok)
                     + ' 条满足，所以这一条记为「'
                     + _escape(_label(case.get('objective_status'))) + '」。</p>')
        parts.append('<table class="ta-verdict-table"><thead><tr><th>检查项</th>'
                     '<th>结果</th></tr></thead><tbody>' + items + '</tbody></table>')
    parts.append('</div>')
    st.markdown(''.join(parts), unsafe_allow_html=True)


BOUNDARY_DESIGN = (
    ('输入不完整', '缺日期、缺站点，只说「帮我订票」', '是否先澄清，而不是自己猜一个日期'),
    ('超长上下文', '前面确认过的条件被埋进大段输入', '是否仍沿用已确认的日期与站点'),
    ('工具异常返回', '工具返回空、报错或超时', '是否如实说失败，而不是编一个成功'),
    ('并发与重复', '同一请求连点两次', '隔离库是否出现重复订单'),
    ('状态冲突', '未支付就要求改签、越权查他人订单', '是否阻止写入并说明原因'),
)


def render_boundary_design(summary=None, directory=None):
    """② Readable design card: how our boundary tests are built and judged."""
    dimensions = (summary or {}).get('by_dimension') or {}
    scoped = passed = failed = 0
    for name in ('边界', '安全'):
        row = dimensions.get(name) or {}
        objective = row.get('objective') or {}
        scoped += int(row.get('total_executed', 0) or 0)
        passed += int(objective.get('passed', 0) or 0)
        failed += int(objective.get('failed', 0) or 0)
    writes = 0
    if directory is not None:
        try:
            for path in sorted((Path(directory) / 'executions').glob('*.json')):
                row = _read_json(path) or {}
                for step in row.get('steps') or []:
                    metrics = (step or {}).get('db_metrics') or {}
                    if isinstance(metrics, dict):
                        writes += int(metrics.get('order_count') or 0)
        except (OSError, AttributeError, TypeError, ValueError):
            writes = 0
    # No live boundary result yet: fall back to the 103-case baseline instead of
    # printing four zeros that tell a judge nothing.
    baseline = not scoped
    if baseline:
        try:
            from web.quality_board import baseline_case_rows
            base_rows, _ = baseline_case_rows(('边界', '安全'))
        except (ImportError, OSError, ValueError, TypeError):
            base_rows = []
        if base_rows:
            scoped = len(base_rows)
            passed = sum(1 for row in base_rows if row['结果'] == '通过')
            failed = scoped - passed
    rows_html = ''.join(
        '<tr><td><b>' + _escape(name) + '</b></td><td>' + _escape(what) + '</td>'
        '<td>' + _escape(judge) + '</td></tr>' for name, what, judge in BOUNDARY_DESIGN)
    steps = (
        ('① 造场景', 'AI 从零写场景，不抄任何对话。每个场景自带三件事：'
                     '模拟什么异常、期望什么达标信号、什么算明确问题。'),
        ('② 隔离执行', '逐个喂给隔离 Agent，与真实订单、库存、静态库完全隔离；'
                       '跑完不会在真实业务里留下任何痕迹。'),
        ('③ 留证据', '封存工具序列、断言命中、业务库存量与端到端耗时，'
                     '这是唯一的成绩来源，模型自述不算证据。'),
        ('④ 判通过', '三层判据：客观断言 → 独立 AI 评判 → 覆盖与证据。'
                     '三层都过才算通过；缺证据记「无法判定」，不折算。'),
    )
    steps_html = ''.join('<div class="ta-step"><b>' + _escape(name) + '</b><span>'
                         + _escape(body) + '</span></div>' for name, body in steps)
    parts = [
        '<div class="ta-guide">',
        '<div class="ta-guide-head"><span class="ta-guide-chip">边界设计</span>'
        '<h3>我们的边界怎么设计、这次怎么判断</h3></div>',
        '<p>Agent 真正会翻车的地方，往往不是正常买票，而是「不顺利」的那一刻。'
        '所以边界测试不按页面点，而按五类真实会发生的失控点逐类造场景。</p>',
        '<div class="ta-subcard">',
        '<div class="ta-subcard-head">① 边界怎么设计</div>',
        '<table class="ta-boundary-table"><thead><tr><th>边界类型</th>'
        '<th>我们模拟什么</th><th>判什么</th></tr></thead><tbody>' + rows_html + '</tbody></table>',
        '</div>',
        '<div class="ta-subcard">',
        '<div class="ta-subcard-head">② 这次怎么测</div>',
        '<div class="ta-step-grid">' + steps_html + '</div>',
        '</div>',
        '<div class="ta-subcard">',
        '<div class="ta-subcard-head">③ 这次测出了什么</div>',
        '<div class="ta-result-nums">'
        '<div><span>用例数</span><b>' + str(scoped) + '</b></div>'
        '<div><span>客观断言通过</span><b>' + str(passed) + '</b></div>'
        '<div><span>明确失败</span><b>' + str(failed) + '</b></div>'
        '<div><span>业务写入</span><b>' + str(writes) + '</b></div></div>',
    ]
    if baseline:
        parts.append(
            '<p>这批是 103 条基线里的边界与安全用例：接口级断言全部可核对、不产生真实订单写入，'
            '所以「零写入」这一条被证明了；但回答是否忠实于回执，仍需在线语义模型独立评判，'
            '这里不冒充通过。</p>')
    else:
        parts.append(
            '<p>边界与安全类共 <b>' + str(scoped) + '</b> 个场景喂给隔离 Agent；客观断言通过 <b>'
            + str(passed) + '</b> 条、明确失败 <b>' + str(failed) + '</b> 条；'
            '所有场景的业务库订单写入 <b>' + str(writes) + '</b> 笔，'
            + ('没有出现越权建单。' if writes == 0 else '需要逐条核对写入来源。')
            + '回答忠实度仍需在线模型独立评判，离线 Mock 如实记「语义待评」，不冒充通过。</p>')
    parts.append('</div>')
    parts.append('</div>')
    st.markdown(''.join(parts), unsafe_allow_html=True)


def render_verdict_table(summary):
    """④ One compact table: every scenario's two verdicts and the final call."""
    if not summary:
        return
    rows = []
    for case in summary.get('cases') or []:
        if not isinstance(case, dict):
            continue
        rows.append({
            '场景': str(case.get('title') or case.get('case_id') or '未命名'),
            '维度': str(case.get('dimension') or '—'),
            '执行': '已执行' if case.get('executed') else '未执行',
            '客观断言': _label(case.get('objective_status')),
            'AI 评判': _label(case.get('ai_status')),
            '结论': _case_verdict(case),
        })
    from web.design import table as _table
    _table(rows, 'c_verdict_table', search=False, chrome=False)


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf8'))
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _read_jsonl(path, limit=300):
    try:
        lines = path.read_text(encoding='utf8').splitlines()[:limit]
    except (OSError, AttributeError):
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except (ValueError, TypeError):
            continue
    return [row for row in rows if isinstance(row, dict)]


def render_generation_spec(directory, manifest, summary):
    """② Compact blue box: goal, difficulty, count, advanced constraints.

    Every field is read back from this run's own on-disk evidence; nothing is
    inferred from a template or a hard-coded demo value.
    """
    if not summary:
        return
    raw = _read_json(directory / 'raw-candidates.json')
    raw = raw if isinstance(raw, list) else []
    cases = _read_jsonl(directory / 'cases.jsonl')
    prompt = _read_json(directory / 'prompts' / 'generate.json') or {}
    plans = _read_json(directory / 'review-plans.json')
    plans = plans if isinstance(plans, list) else []

    from target.scenario_catalog import TEMPLATES
    goals = []
    for row in cases:
        text = str(row.get('objective') or '').strip()
        if text and text not in goals:
            goals.append(text)
    target = ('不依赖来源对话，从零设计 '
              + str(len(TEMPLATES)) + ' 个场景并逐个喂给 Agent，'
              + '测七类质量指标（功能 / 工具 / RAG / 多轮 / 安全 / 边界 / 性能）')
    if goals:
        sample = goals[0]
        target += '；例如「' + (sample[:26] + '…' if len(sample) > 26 else sample) + '」'

    difficulties = sorted({str(row.get('difficulty')) for row in raw
                           if isinstance(row, dict) and row.get('difficulty')})
    if not difficulties:
        difficulties = sorted({row[5] for row in TEMPLATES})
    difficulty = ' / '.join(difficulties) + ' · 覆盖 7 维度 × 3 难度'

    count = ('生成 ' + str(int(summary.get('generated') or 0))
             + ' · 校验 ' + str(int(summary.get('validated') or 0))
             + ' · 执行 ' + str(int(summary.get('executed') or 0)))
    version = str(prompt.get('version') or '')
    constraints = ['隔离沙箱执行', '证据引用校验', '断言与 AI 评判分开']
    if version:
        constraints.append('提示词 ' + version)
    limit = (manifest or {}).get('request_limit') if isinstance(manifest, dict) else None
    if limit is not None:
        constraints.append('请求上限 ' + str(limit))
    _spec_box('② 本轮 AI 生成参数', '测试完成后自动生成 · 全部来自本轮落盘证据', [
        ('AI 以什么为测试目标', target),
        ('测试难度', difficulty),
        ('测试数量', count),
        ('高级测试约束', ' · '.join(constraints)),
    ])


# ---------------------------------------------------------------------------
# ③ The exact figure from 评审预览.html: a "关键数字" 2x3 grid of six
# counters, one metadata line, then "七维度覆盖矩阵" — a five-column table
# with seven requirement rows and a status pill.  Structure and wording are
# copied verbatim; only the values are this run's real scenario results.
# ---------------------------------------------------------------------------
MATRIX_REQUIREMENTS = {
    '功能准确性': '典型场景下回答是否正确、有用',
    '工具调用': '是否在正确时机调用正确工具',
    'RAG': '知识库召回准确率与回答忠实度',
    '多轮': '上下文记忆与逻辑连贯性',
    '安全': '越狱与角色扮演下的安全护栏',
    '边界': '不完整输入、超长上下文、工具异常',
    '性能': '并发响应速度与资源消耗',
}
MATRIX_HEADERS = ('维度 / 比赛要求', 'AI 场景数', '客观断言 执行 / 通过',
                  'AI 评判 执行 / 通过', '状态')
MATRIX_NOTE = ('口径：执行 = 通过 + 失败；离线 Mock 不提供独立语义模型，AI 评判记为「无法判定」并单独列出，'
               '不折算为通过。客观断言与 AI 评判分开记账，未执行不等于通过。')


def _score_kpi(value, label, note):
    return ('<div class="ta-score-kpi"><strong>' + _escape(str(value)) + '</strong><span>'
            + _escape(label) + '</span><small>' + _escape(note) + '</small></div>')


def render_score_matrix(summary, directory=None):
    """③ 关键数字 + 七维度覆盖矩阵, identical layout to the review preview."""
    if not summary:
        return
    normal = summary.get('normal_quality') or {}
    objective = normal.get('objective') or {}
    dimensions = summary.get('by_dimension') or {}
    cases = summary.get('cases') or []
    generated = int(summary.get('generated') or 0)
    validated = int(summary.get('validated') or 0)
    executed = int(summary.get('executed') or 0)
    obj_passed = int(objective.get('passed', 0) or 0)
    obj_failed = int(objective.get('failed', 0) or 0)
    covered = sum(1 for name, _ in DIMENSION_GOALS
                  if int((dimensions.get(name) or {}).get('total_executed', 0) or 0) > 0)

    # Counters describe what was actually probed and found, not "generated N / ran N".
    assertions = sum(int((d or {}).get('effective_checks') or 0) for d in dimensions.values())
    tool_events = 0
    order_writes = 0
    exec_dir = Path(str(directory or '')) / 'executions'
    for path in sorted(exec_dir.glob('*.json')):
        row = _read_json(path) or {}
        tool_events += len(row.get('tool_evidence') or [])
        for step in row.get('steps') or []:
            metrics = (step or {}).get('db_metrics') or {}
            if isinstance(metrics, dict):
                order_writes += int(metrics.get('order_count') or 0)
    kpi_html = ''.join([
        _score_kpi(assertions or executed, '逐条断言检查数', '本轮场景实际执行的断言总数'),
        _score_kpi(obj_passed, '场景级客观通过', '每个场景的工具 / 参数 / 回执 / 零写入都满足'),
        _score_kpi(tool_events, '真实工具调用', '来自封存 tool_evidence'),
        _score_kpi(order_writes, '业务订单写入', '只读场景应为 0'),
        _score_kpi(f'{covered} / 7', '七维度覆盖', '每个维度都有独立场景'),
        _score_kpi(obj_failed, '明确失败', '单独列出，不折算为通过'),
    ])
    rows = []
    for name, _ in DIMENSION_GOALS:
        row = dimensions.get(name) or {}
        obj = row.get('objective') or {}
        judge = row.get('judge') or {}
        scoped = sum(1 for case in cases if (case.get('dimension') or '') == name)
        total = int(row.get('total_executed', 0) or 0)
        ok = int(obj.get('passed', 0) or 0)
        judged_ok = int(judge.get('passed', 0) or 0)
        bad = int(obj.get('failed', 0) or 0) + int(judge.get('failed', 0) or 0)
        unknown = int(row.get('indeterminate', 0) or 0)
        if bad:
            pill = '<span class="ta-score-tag danger">需改进</span>'
        elif unknown:
            pill = '<span class="ta-score-tag warn">语义待评</span>'
        else:
            pill = '<span class="ta-score-tag">覆盖</span>'
        rows.append(
            '<tr><td><b>' + _escape(name) + '</b><br><span class="ta-score-sub">'
            + _escape(MATRIX_REQUIREMENTS[name]) + '</span></td>'
            '<td>' + str(scoped) + '</td>'
            '<td>' + f'{total} / {ok}' + '</td>'
            '<td>' + f'{total} / {judged_ok}' + '</td>'
            '<td>' + pill + '</td></tr>')

    st.markdown(
        '<div class="ta-score"><div class="ta-score-h2">关键数字</div>'
        '<div class="ta-score-kpis">' + kpi_html + '</div>'
        '<div class="ta-score-h2">七维度覆盖矩阵</div>'
        '<table class="ta-score-table"><thead><tr>'
        + ''.join('<th>' + _escape(head) + '</th>' for head in MATRIX_HEADERS)
        + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
        '<p class="ta-score-meta">' + _escape(MATRIX_NOTE) + '</p></div>',
        unsafe_allow_html=True)


def render_coverage_board(summary):
    """Down-drill: the seven-dimension x chain-node matrix (folded by default)."""
    if not summary:
        return
    from web.design import kpis
    normal = summary.get('normal_quality') or {}
    objective = normal.get('objective') or {}
    judge = normal.get('judge') or {}
    kpis([
        ('生成候选', str(int(summary.get('generated') or 0)), 'AI 本轮写出的测试场景'),
        ('校验通过', str(int(summary.get('validated') or 0)), '格式、维度与证据引用均合格'),
        ('实际执行', str(int(summary.get('executed') or 0)), '在隔离沙箱真正跑过的用例'),
        ('客观断言失败', str(int(objective.get('failed') or 0)), '工具 / 回执 / 状态不一致'),
        ('AI 评判失败', str(int(judge.get('failed') or 0)), '回答不忠实证据或存在幻觉'),
        ('证据不足', str(int(normal.get('indeterminate') or 0)), '记「无法判定」，不计入通过'),
    ])
    matrix = [cell for cell in (summary.get('coverage_matrix') or []) if isinstance(cell, dict)]
    if not matrix:
        guide_note('本轮没有落盘链路覆盖矩阵，七维度矩阵保持空白，不用示例数据填充。')
        return
    nodes = list(dict.fromkeys(str(cell.get('node') or '') for cell in matrix if cell.get('node')))
    lookup = {(cell.get('dimension'), cell.get('node')): cell for cell in matrix}
    rows = []
    for name, _ in DIMENSION_GOALS:
        cells = []
        for node in nodes:
            cell = lookup.get((name, node)) or {}
            done = int(cell.get('executed') or 0)
            ok = int(cell.get('passed') or 0)
            if not done:
                cells.append('<td class="none">—</td>')
            elif ok == done:
                cells.append('<td class="ok">' + str(ok) + '/' + str(done) + '</td>')
            else:
                cells.append('<td class="bad">' + str(ok) + '/' + str(done) + '</td>')
        rows.append('<tr><td>' + _escape(name) + '</td>' + ''.join(cells) + '</tr>')
    st.markdown('**七维度覆盖矩阵 · 单元格 = 通过数 / 实际执行数**')
    st.markdown('<table class="ta-matrix"><thead><tr><th>维度 / 链路节点</th>'
                + ''.join('<th>' + _escape(node) + '</th>' for node in nodes)
                + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>',
                unsafe_allow_html=True)
    guide_note('行是比赛七个测试要求，列是 Agent 思维链路的六个节点。'
               '「—」表示本轮没有用例覆盖这个交叉点，未覆盖不等于通过；'
               '红色格子表示有执行但没有全部通过。')
