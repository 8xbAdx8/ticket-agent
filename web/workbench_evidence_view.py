"""Read and present evidence from an already verified workbench run."""
import hashlib
import json
from pathlib import Path
import re

import streamlit as st

from web.design import escape


def approved_case_ids(directory, run):
    """Older runs without an approval receipt have an unknown approval count."""
    checksum = run.get('review_sha256')
    if not checksum:
        return set() if run.get('status') == 'AWAITING_REVIEW' else None
    raw = (directory / 'review.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != checksum:
        raise ValueError('INVALID_APPROVAL_HASH')
    review = json.loads(raw)
    if any(review.get(key) != run[key] for key in ('run_id', 'session_id')):
        raise ValueError('INVALID_APPROVAL_OWNER')
    return set(review['case_ids'])


def case_evidence(directory, case):
    case_id = case['case_id']
    execution = judgement = None
    if ref := case.get('execution_ref'):
        if not re.fullmatch(r'case-[0-9]+', case_id) or ref != f'executions/{case_id}.json':
            raise ValueError('INVALID_EXECUTION_REFERENCE')
        execution = json.loads((directory / ref).read_text(encoding='utf8'))
        if execution['case_id'] != case_id:
            raise ValueError('INVALID_EXECUTION_CASE')
    if ref := case.get('judge_ref'):
        match = re.fullmatch(r'(judgements(?:-revision-2)?\.jsonl)#line=([1-9][0-9]*)', ref)
        if not match:
            raise ValueError('INVALID_JUDGE_REFERENCE')
        filename, line = match.groups()
        rows = (directory / filename).read_text(encoding='utf8').splitlines()
        judgement = json.loads(rows[int(line)-1])
        if judgement['case_id'] != case_id:
            raise ValueError('INVALID_JUDGE_CASE')
    return execution, judgement


def render_metrics(items):
    cells = ''.join(f'<div class="ta-eval-metric"><span>{escape(label)}</span>'
                    f'<strong>{escape(value)}</strong></div>' for label, value in items)
    st.markdown('<div class="ta-eval-metrics">' + cells + '</div>', unsafe_allow_html=True)


def styles():
    st.markdown('<span hidden class="ta-workbench-marker"></span><style>'
                + Path(__file__).with_name('workbench_evidence.css').read_text(encoding='utf8') + '</style>',
                unsafe_allow_html=True)


def render_plan(candidate, plan=None):
    st.text(candidate.get('objective') or '未取得可执行的测试目标。')
    if plan:
        for index, step in enumerate(plan['integration_steps'], 1):
            st.text(f"{index}. {step.get('message') or step.get('tool') or step['kind']}")
            if step.get('args'):
                st.json(step['args'], expanded=False)
            for check in step.get('checks', []):
                st.text(f"{check['path']} · {check['op']} · {check['value']}")
    else:
        for index, turn in enumerate(candidate.get('conversation', []), 1):
            st.text(f'{index}. {turn}')
        for index, checks in enumerate(candidate.get('assertions', []), 1):
            for check in checks:
                st.text(f"步骤 {index} · {check['path']} · {check['op']} · {check['value']}")
    if candidate.get('errors'):
        st.text('校验原因 · ' + '；'.join(candidate['errors']))


def render_execution(execution, judgement, *, dimension, status, candidate):
    if not execution or execution.get('executed') is not True:
        st.caption('没有实际执行证据。')
        return
    st.caption(execution.get('ref') or '执行记录')
    messages = iter(candidate.get('conversation', []))
    for step in execution.get('steps', []):
        st.markdown(f"**步骤 {step['index']} · {step['kind']}**")
        if step['kind'] == 'chat':
            message = next(messages, None)
            if message:
                st.text(f'测试输入 · {message}')
        result = step.get('result') or {}
        if reply := result.get('reply'):
            st.text('Agent 最终回复')
            st.text(reply)
        if step.get('trace_id'):
            st.caption('Trace · ' + step['trace_id'])
        for check in step.get('checks', []):
            verdict = '通过' if check.get('ok') is True else '失败'
            st.text(f"{verdict} · {check['path']}")
            st.json({label: check[key] for key, label in (
                ('op', '比较方式'), ('expected', '预期'), ('actual', '实测'), ('error', '取证错误'),
            ) if key in check}, expanded=verdict == '失败')
        if dimension in ('安全', '边界') and (step.get('state') or step.get('db_metrics')):
            st.caption('执行后的状态与数据库观测')
            st.json({'状态': step.get('state'), '数据库指标': step.get('db_metrics')}, expanded=False)
    if dimension == 'RAG':
        for retrieval in execution.get('retrieval_evidence', []):
            st.caption('实际检索 · ' + retrieval['ref'])
            if retrieval['documents']:
                st.json(retrieval['documents'], expanded=False)
            else:
                st.caption('已执行检索，返回 0 条。')
        if not execution.get('retrieval_evidence'):
            st.caption('未记录可核验的检索事件。')
        if candidate.get('expected_policy_ids'):
            st.text('预期政策 ID · ' + '、'.join(candidate['expected_policy_ids']))
    for event in execution.get('tool_evidence', []):
        name = event.get('tool') or event.get('event_type') or '工具名称未记录'
        outcome = event.get('status') or ('已调用' if event.get('executed') is True else '状态未记录')
        st.text(f'{name} · {outcome}')
        if event.get('event_id'):
            st.caption('run_events.jsonl#' + event['event_id'])
        st.json({label: event[key] for key, label in (
            ('call_id', '调用 ID'), ('executed', '实际执行'), ('args', '实际参数'), ('output', '工具返回'),
        ) if key in event}, expanded=False)
    if judgement:
        st.markdown('**AI 评判**')
        st.text(status(judgement['status']))
        if goal := judgement.get('objective'):
            st.caption('评判标准 · ' + ('RAG 回答忠实度' if goal == 'rag_faithfulness' else '用例目标与执行证据'))
        if reason := judgement.get('judge_reason'):
            st.text(reason)
        for ref in judgement.get('evidence_refs', []):
            st.caption(ref)
    if dimension == '多轮' and (memory := execution.get('metrics', {}).get('memory')) is not None:
        st.text('实测跨轮条件核对 · ' + ('通过' if memory else '失败'))
    if dimension == '边界':
        if execution.get('mutation_status'):
            st.caption('注入判定 · ' + execution['mutation_status'])
        if execution.get('concurrency_evidence'):
            st.json(execution['concurrency_evidence'], expanded=False)
