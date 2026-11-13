
"""Deterministic aggregation of a single workbench run."""
from collections import Counter
from math import ceil, isfinite

from target.diagnostics import IDS
from web.evidence import DIMENSIONS

NODES = ("意图识别", "工具选择", "参数构造", "结果处理", "业务状态变更", "回复忠实度")
BOUNDARIES = ("输入不完整", "超长上下文", "工具异常返回", "并发与重复", "状态冲突")


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def _quality(rows):
    executed = [row for row in rows if row.get("executed") is True]
    objective = Counter(row["objective_status"] for row in executed)
    judged = Counter(row["ai_status"] for row in executed)
    return {
        "executed": len(executed),
        "objective": dict(objective),
        "judge": dict(judged),
        "objective_rate": ratio(objective["passed"], len(executed)),
        "judge_rate": ratio(judged["passed"], judged["passed"] + judged["failed"]),
        "indeterminate": judged["indeterminate"],
    }


def _mutation_results(rows):
    summary = []
    for kind, label in IDS.items():
        selected = [row for row in rows if row.get("mutation") == kind]
        counts = Counter(row.get("mutation_status") for row in selected)
        injected = counts["detected"] + counts["missed"] + counts["indeterminate"]
        summary.append(dict(code=label, kind=kind, planned=len(selected), injected=injected,
                            detected=counts["detected"], missed=counts["missed"],
                            indeterminate=counts["indeterminate"], not_triggered=counts["not_triggered"],
                            not_run=counts["not_run"], rate=ratio(counts["detected"], injected),
                            evidence=[row["execution_ref"] for row in selected if row.get("execution_ref")]))
    return summary


def summarize(run_id, cases, executions, judgements, consistency):
    by_execution = {row["case_id"]: row for row in executions}
    by_judge = {row["case_id"]: row for row in judgements}
    rows = []
    for case in cases:
        case_id = case["case_id"]
        execution = by_execution.get(case_id, {})
        judge = by_judge.get(case_id, {})
        ran = execution.get("executed") is True
        rows.append({
            "case_id": case_id, "title": case["title"], "dimension": case.get("dimension"),
            "validated": case["validated"], "executed": ran,
            "objective_status": execution.get("objective_status", "not_run"),
            "ai_status": judge.get("status", "not_run"),
            "mutation": case.get("mutation"), "boundary": case.get("boundary"),
            "mutation_status": execution.get("mutation_status", "not_run"),
            "agent_invoked": execution.get("agent_invoked") is True,
            "covered_nodes": execution.get("verified_nodes", []),
            "execution_ref": execution.get("ref"), "judge_ref": judge.get("ref"),
            "evidence_complete": bool(ran and execution.get("trace_refs") and case.get("request_id")
                                      and case.get("prompt_sha256") and case.get("response_sha256")
                                      and judge.get("request_id") and judge.get("response_sha256")
                                      and judge.get("evidence_refs")),
        })
    executed = [row for row in rows if row["executed"]]
    ordinary = [row for row in executed if row["mutation"] is None]
    cells = []
    for dimension in DIMENSIONS:
        for node in NODES:
            declared = [case["case_id"] for case in cases if case["validated"] and case["dimension"] == dimension
                        and node in case["covered_nodes"]]
            verified = [row for row in executed if row["case_id"] in declared and node in row["covered_nodes"]]
            cells.append(dict(dimension=dimension, node=node, case_ids=declared, planned=len(declared),
                              executed=len(verified), passed=sum(row["objective_status"] == "passed" and
                                                               row["mutation"] is None for row in verified),
                              status="covered" if verified else "not_covered"))
    coverage = ratio(sum(cell["executed"] > 0 for cell in cells), len(cells))
    by_dimension = {}
    for dimension in DIMENSIONS:
        relevant = [row for row in rows if row['dimension'] == dimension]
        tested = [row for row in relevant if row['executed']]
        by_dimension[dimension] = {**_quality([row for row in tested if row['mutation'] is None]),
            'case_ids': [row['case_id'] for row in relevant], 'total_executed': len(tested),
            'effective_checks': sum(check.get('actual') is not None and not check.get('error')
                                    for row in tested for step in by_execution[row['case_id']].get('steps', [])
                                    for check in step.get('checks', [])),
            'uncovered_nodes': sum(cell['status'] == 'not_covered' for cell in cells if cell['dimension'] == dimension),
            'evidence': [row['execution_ref'] for row in tested if row['execution_ref']]}
    def samples(dimension, metric):
        return [value for row in ordinary if row['dimension'] == dimension
                and (value := by_execution[row['case_id']].get('metrics', {}).get(metric)) is not None]

    recalls = samples('RAG', 'recall')
    memory = samples('多轮', 'memory')
    security = samples('安全', 'security_block')
    faithful = [row['ai_status'] for row in ordinary if row['dimension'] == 'RAG'
                and by_execution[row['case_id']].get('metrics', {}).get('recall')
                and by_judge.get(row['case_id'], {}).get('objective') == 'rag_faithfulness'
                and row['ai_status'] in ('passed', 'failed')]
    special = {
        'RAG': {'政策 ID 召回（本轮对话参照）': ratio(sum(row['matches'] for row in recalls), sum(row['expected'] for row in recalls)),
                '回答忠实度（AI 评判）': ratio(faithful.count('passed'), len(faithful))},
        '多轮': {'跨轮记忆命中率': ratio(memory.count(True), len(memory))},
        '安全': {'权限拦截证据': ratio(security.count(True), len(security))},
    }
    groups = []
    for name in BOUNDARIES:
        scoped = [row for row in rows if row["boundary"] == name and row["mutation"]]
        injected = [row for row in scoped if row["mutation_status"] in ("detected", "missed", "indeterminate")]
        detected = sum(row["mutation_status"] == "detected" for row in injected)
        groups.append(dict(category=name, planned=len(scoped), injected=len(injected), detected=detected,
                           rate=ratio(detected, len(injected)), case_ids=[row["case_id"] for row in scoped]))
    durations = sorted(row["duration_ms"] for row in executions if row["case_id"] in
                       by_dimension["性能"]["case_ids"] and row.get("agent_invoked")
                       and type(row.get("duration_ms")) in (int, float) and isfinite(row["duration_ms"]))
    concurrency = [row["concurrency"] for row in executions if row.get("concurrency")]
    return dict(run_id=run_id, generated=len(cases), validated=sum(row["validated"] for row in rows),
                executed=len(executed), agent_invoked=sum(row["agent_invoked"] for row in executed),
                normal_quality=_quality(ordinary), injected_quality=_quality([row for row in executed if row["mutation"]]),
                coverage_rate=coverage, coverage_matrix=cells,
                evidence_rate=ratio(sum(row["evidence_complete"] for row in rows), len(rows)),
                by_dimension=by_dimension, special_metrics=special, cases=rows, mutations=_mutation_results(rows), boundaries=groups,
                consistency=consistency,
                performance=dict(case_wall_ms=durations,
                                 p50=durations[ceil(len(durations) * .50) - 1] if durations else None,
                                 p95=durations[ceil(len(durations) * .95) - 1] if durations else None,
                                 concurrency=concurrency,
                                 tool_times=[sample for row in executions for sample in row.get('metrics', {}).get('tool_times', [])]))

