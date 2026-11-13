"""Evidence-based gaps and an explicit, session-owned retest plan."""
import hashlib
import json
from pathlib import Path

from target.scenario_workbench import load_run_results, read_manifest, run_directory


def inspect_run(run_id, session_id, *, root):
    summary = load_run_results(run_id, session_id, root=root)
    directory = run_directory(run_id, root)
    manifest = read_manifest(run_id, session_id, root=root)
    gaps = []

    def add(key, feature, status, risk, reason, refs, steps, expected, tools=(), *, live=False,
            case_id=None, dimension=None, independent=False):
        digest = hashlib.sha256(f'{run_id}:{key}'.encode()).hexdigest()[:16]
        gaps.append(dict(gap_id=f'GAP-{digest}', feature=feature, status=status, risk=risk,
                         reason=reason, evidence_refs=list(dict.fromkeys(refs)), objective=reason,
                         steps=steps, expected=expected, tools=list(tools),
                         related_case=case_id, bug=None, dimension=dimension, independent=independent,
                         acceptance=expected, requires_live=live, requires_review=True,
                         prerequisites='隔离测试数据；候选经人工批准后才可执行'))

    cases = summary['cases']
    executions = {}
    for case in cases:
        case_id = case['case_id']
        ref = case.get('execution_ref')
        judge_ref = case.get('judge_ref')
        refs = [value for value in ('cases.jsonl', ref, judge_ref) if value]
        feature = f"{case_id} · {case['title']}"
        objective, judge = case['objective_status'], case['ai_status']
        if ref:
            execution = json.loads((directory / ref).read_text(encoding='utf8'))
            executions[case_id] = execution
            refs.extend(execution.get('agent_trace_refs', [])[:3])
        else:
            execution = {}
        checks = [check for step in execution.get('steps', []) for check in step.get('checks', [])]
        evidence_paths = sorted({check['path'] for check in checks if check.get('path')})
        declared_tools = sorted({row['tool'] for row in execution.get('tool_evidence', [])
                                 if row.get('executed') is True and row.get('tool')})
        if not case['executed']:
            add(f'{case_id}-execution', feature, 'NOT_RUN' if case['validated'] else 'BLOCKED', 'P2',
                '尚无实际执行，或候选未通过质量门。', refs,
                ['核对候选 Schema 与审核记录', '在隔离环境执行已批准的计划'], '有独立断言与同一运行的 Trace',
                dimension=case['dimension'])
            continue
        if objective == 'failed':
            paths = [check['path'] for check in checks if check.get('ok') is False and check.get('path')]
            add(f'{case_id}-assertions', feature, 'FAIL', 'P1',
                '存在客观断言失败。' + (' 失败字段：' + '、'.join(paths[:6]) if paths else ''), refs,
                ['复现原用例', '保留原断言并检查工具调用参数和结果'],
                '原失败字段有明确证据，且修复后通过原断言', declared_tools, case_id=case_id,
                dimension=case['dimension'])
        elif objective != 'passed' or not evidence_paths:
            add(f'{case_id}-checks', feature, 'INSUFFICIENT_EVIDENCE', 'P2', '缺少可核对的客观断言。', refs,
                ['从已执行工具的参数和输出添加独立断言'], '断言绑定具体步骤和原始回执', declared_tools,
                dimension=case['dimension'])
        if objective in ('passed', 'failed') and judge in ('passed', 'failed') and objective != judge:
            add(f'{case_id}-judge', feature, 'INSUFFICIENT_EVIDENCE', 'P1',
                '客观断言与 AI Judge 判定分歧。', refs,
                ['对照原目标、客观断言、原回复与 Judge 理由', '补上遗漏的可判定条件，保留两个原判定'],
                '每项分歧有独立证据及正反例', declared_tools, case_id=case_id, dimension=case['dimension'])
        if declared_tools and not any(path.startswith('result.reply') for path in evidence_paths):
            add(f'{case_id}-reply', feature, 'INSUFFICIENT_EVIDENCE', 'P2',
                '存在工具执行记录，缺少最终回复的确定性断言。', refs,
                ['用工具回执核对最终回复中的计数、时刻或引用'],
                '回复与同一轮工具证据一致', declared_tools, case_id=case_id, dimension=case['dimension'])

    scoped = {key: [] for key in ('RAG', '多轮')}
    for case in cases:
        if case['dimension'] in scoped and case['executed']:
            scoped[case['dimension']].append(executions.get(case['case_id'], {}))
    rag = scoped['RAG']
    if not rag or not all(row.get('citation_verification_ref') for row in rag):
        add('rag-citations', 'RAG 引用', 'INSUFFICIENT_EVIDENCE' if rag else 'NOT_RUN', 'P2',
            '缺少独立的政策引用核验。', [row['ref'] for row in rag if row.get('ref')] or ['summary.json#/by_dimension/RAG'],
            ['使用冻结语料执行检索', '核对政策 ID、版本、回复引用和无答案行为'],
            '分别报告检索、引用和回答的结果', ('search_policy',), dimension='RAG')
    memory = scoped['多轮']
    unknown_memory = not memory or any(row.get('metrics', {}).get('memory') is not True for row in memory)
    if unknown_memory:
        failed = any(row.get('metrics', {}).get('memory') is False for row in memory)
        add('multi-turn', '跨轮记忆', 'FAIL' if failed else 'INSUFFICIENT_EVIDENCE' if memory else 'NOT_RUN',
            'P1' if failed else 'P2', '跨轮继承的参数或游标缺少通过证据。',
            [row['ref'] for row in memory if row.get('ref')] or ['summary.json#/special_metrics/多轮'],
            ['在同一会话查询车次', '下一轮只要求翻页', '核对站点、日期、游标及无重复班次'],
            '实际工具沿用上一轮的合法参数和下一页游标', ('railway_query_trips',), dimension='多轮')
    for item in summary['mutations']:
        if not item['injected'] or item.get('missed') or item.get('indeterminate') or not item.get('recovery_verified'):
            add(f"mutation-{item['code']}", f"{item['code']} · {item['kind']}",
                'FAIL' if item.get('missed') else 'INSUFFICIENT_EVIDENCE' if item['injected'] else 'NOT_RUN',
                'P2', '缺少注入后的检出或业务恢复证据。',
                item['evidence'] or ['summary.json#/mutations'],
                ['运行原异常注入器', '核对检出、写操作、恢复和数据库最终状态'],
                'Trace 与独立数据库核验支持结论', dimension='边界')
    if not any(case['dimension'] == '安全' and case['executed'] for case in cases):
        add('security', '未确认交易防护', 'NOT_RUN', 'P2', '缺少安全用例的执行记录。',
            ['summary.json#/by_dimension/安全'], ['从当前对话提取相关写操作风险', '模拟未确认请求并检查隔离数据库'],
            '没有未经确认的订单、支付或退款写入', dimension='安全')
    if not summary['performance']['case_wall_ms']:
        add('case-timing', '用例总耗时', 'NOT_RUN', 'P2', '缺少性能类用例的耗时样本。',
            ['summary.json#/performance/case_wall_ms'], ['对本轮相关查询设计连续只读步骤', '审核后执行并采集实际耗时'],
            '性能页显示对应的用例耗时，保留 Trace 和客观断言', dimension='性能')
    if not any(isinstance(row, dict) and row.get('measurement_kind') == 'load_test'
               for row in summary['performance']['concurrency']):
        add('concurrency', '并发性能', 'NOT_RUN', 'P2', '缺少系统并发负载测量。',
            ['summary.json#/performance'], ['隔离运行多级并发', '记录延迟分布、吞吐量、超时和数据库一致性'],
            '有原始样本、错误分母和并发数据库核验', dimension='性能', independent=True)
    if executions and not any(row.get('mode') == 'live_agent' and row.get('agent_invoked') is True
                              for row in executions.values()):
        add('live-agent', '真实模型 Agent 执行', 'NOT_RUN', 'P2', '当前运行没有 Live Agent 执行证据。',
            ['summary.json#/cases'], ['单独授权后重跑关键场景', '核对真实 HTTP 账本和工具 Trace'],
            'Live Agent 调用与真实执行绑定', live=True, independent=True)
    uncovered = [(index, row) for index, row in enumerate(summary['coverage_matrix']) if not row['executed']]
    for index, cell in uncovered:
        dimension, node = cell['dimension'], cell['node']
        add(f'coverage-{dimension}-{node}', f'{dimension} · {node}', 'NOT_RUN', 'P3',
            '此链路单元尚无已执行的验证。', [f'summary.json#/coverage_matrix/{index}'],
            ['为此链路添加一个具备可核验断言的场景'], '实际执行证据命中该链路单元', dimension=dimension)
    gaps.sort(key=lambda row: (row['risk'], row['status'] != 'FAIL', row['feature']))
    return dict(schema='ticket-workbench-gaps/1', run_id=run_id, session_id=session_id,
                coverage=dict(covered=len(summary['coverage_matrix']) - len(uncovered),
                              total=len(summary['coverage_matrix']), uncovered=len(uncovered)),
                disagreements=sum(row['objective_status'] in ('passed', 'failed') and
                                  row['ai_status'] in ('passed', 'failed') and
                                  row['objective_status'] != row['ai_status'] for row in cases),
                model_source=manifest['model_source'], gaps=gaps)


def select_gaps(report, gap_ids):
    known = {row['gap_id']: row for row in report['gaps'] if not row.get('independent')}
    ids = tuple(gap_ids)
    if not 1 <= len(ids) <= 3 or len(ids) != len(set(ids)) or any(key not in known for key in ids):
        raise ValueError('C_WORKBENCH_INVALID_GAP_SELECTION')
    return dict(run_id=report['run_id'], gaps=[known[key] for key in ids])


def source_evidence(selection, *, root):
    """Project bounded fields from the parent run already verified by inspect_run."""
    from target.scenario_workbench_evidence import private_evidence

    directory = run_directory(selection['run_id'], root)
    evidence = {}
    for gap in selection['gaps']:
        ref = next((ref for ref in gap['evidence_refs'] if ref.startswith('executions/') and ref.endswith('.json')), None)
        if ref is None:
            continue
        execution = json.loads((directory/ref).read_text(encoding='utf8'))
        evidence[gap['gap_id']] = [
            dict(trace_id=step.get('trace_id'), reply=str(step.get('result', {}).get('reply') or '')[:500],
                 tools=[{'tool': row.get('tool'), 'args': row.get('args')}
                        for row in step.get('result', {}).get('queries', [])[:4]],
                 checks=[{key: check.get(key) for key in ('path', 'ok', 'expected')}
                         for check in step.get('checks', [])[:6]])
            for step in execution['steps'][:4]
        ]
    return private_evidence(evidence)


def quality_history(session_id, *, root, exclude, limit=10):
    """Only sealed, owned runs from the configured workbench store."""
    rows = []
    root = Path(root)
    manifests = sorted(root.glob('*/manifest.json'), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in manifests:
        run_id = path.parent.name
        if run_id == exclude:
            continue
        try:
            if read_manifest(run_id, session_id, root=root)['status'] != 'COMPLETED':
                continue
            summary = load_run_results(run_id, session_id, root=root)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        rows.append(dict(run_id=run_id, created_at=summary['created_at'],
                         executed=summary['executed'], coverage=summary['coverage_rate'],
                         objective=summary['normal_quality']['objective_rate'],
                         judge=summary['normal_quality']['judge_rate']))
        if len(rows) == limit:
            break
    return rows
