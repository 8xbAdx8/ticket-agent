"""Test-console projections: cases, RAG dimensions, mutation matrix, comparison.

Every function reports what the files actually contain. A dimension that was not
measured is returned as 未评估 / 未记录 and is never rendered as a pass.
"""
import json
from pathlib import Path

import config
from web.evidence import mutation_rows, mutation_totals

STATUS_LABELS = {"passed": "通过", "failed": "失败", "skipped": "跳过", "error": "错误"}
STAGE_LABELS = {"call": "用例执行", "setup": "前置条件", "teardown": "清理"}
OWNER_NOTE = "A 自测 / 工程验收，不是 B 正式测试成绩"


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def batch_meta(report):
    """Version, time, environment and scope exactly as recorded in the batch."""
    steps = report.get("steps") or []
    scope = " · ".join(f"{s.get('name')}=" + {"passed": "通过", "failed": "失败", "skipped": "跳过",
                                               "blocked": "阻塞", "running": "进行中",
                                               "pending": "未执行"}.get(s.get("status"), "未记录")
                       for s in steps) or "未记录"
    configuration = report.get("configuration") or {}
    env = ", ".join(f"{k}={v}" for k, v in sorted(configuration.items())) or "未记录"
    return [
        ("批次", report.get("batch_id") or "未记录"),
        ("归属", (report.get("owner") or "未记录") + " · " + OWNER_NOTE),
        ("开始 / 结束（UTC）", str(report.get("started") or "未记录") + " / " + str(report.get("ended") or "未记录")),
        ("Git", report.get("git_sha") or "未记录"),
        ("源码指纹", (report.get("source_sha256") or "未记录")[:16]),
        ("测试集指纹", (report.get("suite_sha256") or "未记录")[:16]),
        ("配置指纹", (report.get("config_sha256") or "未记录")[:16]),
        ("运行环境", env),
        ("网络策略", str(report.get("network_policy") or "未记录")
         + "；阻断外部连接 " + str(report.get("blocked_external_connections", "未记录")) + " 次"),
        ("测试范围", scope),
    ]


def case_rows(directory):
    """One row per recorded pytest result; no row is invented for a missing case."""
    data = _read(Path(directory) / "results.json")
    rows = []
    for index, item in enumerate(data.get("results") or []):
        case_id = str(item.get("case_id") or "")
        if not case_id:
            continue
        parts = case_id.split("::")
        rows.append({
            "序号": index,
            "用例": case_id,
            "阶段": STAGE_LABELS.get(item.get("stage"), str(item.get("stage") or "未记录")),
            "状态": STATUS_LABELS.get(item.get("status"), "未记录"),
            "耗时（秒）": round(item["duration_s"], 3) if isinstance(item.get("duration_s"), (int, float)) else None,
            "子测试": "是" if item.get("is_subtest") else "否",
            "断言证据": item.get("assertion_evidence") or "",
        })
    return rows


def case_stats(rows):
    """Sample size and every status bucket, so a rate never hides 未记录/跳过."""
    counts = {}
    for row in rows:
        counts[row["状态"]] = counts.get(row["状态"], 0) + 1
    return {"总计": len(rows), "通过": counts.get("通过", 0), "失败": counts.get("失败", 0),
            "跳过": counts.get("跳过", 0), "未记录": counts.get("未记录", 0)}


def filter_cases(rows, status="全部", keyword=""):
    needle = (keyword or "").strip().lower()
    return [row for row in rows
            if (status == "全部" or row["状态"] == status)
            and (not needle or needle in row["用例"].lower() or needle in row["断言证据"].lower())]


def case_source(case_id, root=None):
    """Return the test body that defines the expectation, or None when unavailable."""
    root = Path(root or config.BASE_DIR)
    parts = str(case_id).split("::")
    relative = parts[0]
    if not relative.startswith("tests/") or ".." in Path(relative).parts or len(parts) < 2:
        return None
    path = (root / relative).resolve()
    if not path.is_relative_to((root / "tests").resolve()) or not path.is_file():
        return None
    from web.presentation import code_excerpt
    try:
        line, source = code_excerpt(root, relative, parts[-1], parts[1] if len(parts) > 2 else None)
        return {"line": line, "source": source, "file": relative}
    except (OSError, ValueError, SyntaxError, StopIteration, TypeError):
        return None


def case_detail(row, directory, root=None):
    """Expected behaviour comes from the test source; actual comes from the run."""
    source = case_source(row["用例"], root)
    evidence = (row.get("断言证据") or "").strip()
    failure_line = ""
    for line in evidence.splitlines():
        if line.startswith("E "):
            failure_line = line[2:].strip()
    if failure_line:
        actual = failure_line
    elif row["状态"] == "通过":
        actual = "用例通过；本次没有产生失败断言文本"
    elif row["状态"] == "跳过":
        actual = "用例被跳过；断言未执行，不能记为通过"
    else:
        actual = "未记录判定文本"
    return {
        "用例": row["用例"],
        "阶段": row["阶段"],
        "状态": row["状态"],
        "耗时": row.get("耗时（秒）"),
        "预期行为来源": (source["file"] + ":" + str(source["line"])) if source else "未找到测试源码（不推断预期行为）",
        "测试源码": source["source"] if source else None,
        "实际结果": actual,
        "原始断言证据": evidence or None,
        "进程日志": _log_tail(Path(directory) / "pytest.log"),
    }


def _log_tail(path, limit=6000):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text[-limit:] if text else None


def rag_dimensions(rag):
    """Four separate dimensions; an unmeasured one is never reported as passing."""
    rag = rag or {}
    metrics = rag.get("metrics") or {}
    keyword = metrics.get("keyword") or {}
    positives = keyword.get("positive_samples")
    negatives = keyword.get("negative_samples")
    false_recall = keyword.get("no_answer_false_recall")
    faithfulness = rag.get("answer_faithfulness") or "not_recorded"
    retrieval_measured = isinstance(positives, int) and positives > 0
    answer_assessed = isinstance(faithfulness, str) and bool(faithfulness) and not faithfulness.startswith("not_")
    abstention_detail = (f"负样本 {negatives} 条中误召回 {false_recall} 条"
                         if isinstance(negatives, int) and isinstance(false_recall, int) else "未记录负样本统计")
    return [
        {"评估项": "检索命中", "状态": "已评估" if retrieval_measured else "未评估",
         "分母": f"{positives} 条正样本" if isinstance(positives, int) else "未记录",
         "依据": "keyword 模式 recall@1 / recall@3 / MRR",
         "说明": "只评价检索是否取到标注文档，不评价回答是否正确。"},
        {"评估项": "引用支持", "状态": "未评估",
         "分母": "未记录",
         "依据": "本轮没有生成回答，也没有引用判定记录",
         "说明": "检索命中不等于回答引用了该文档；未评估不显示为通过。"},
        {"评估项": "回答正确", "状态": "已评估" if answer_assessed else "未评估",
         "分母": "未记录",
         "依据": "answer_faithfulness = " + str(faithfulness),
         "说明": "本次批次不产生新回答，忠实度与正确性都没有依据。"},
        {"评估项": "无答案拒答", "状态": "仅检索层代理指标",
         "分母": f"{negatives} 条负样本" if isinstance(negatives, int) else "未记录",
         "依据": abstention_detail,
         "说明": "这是检索器在无答案题上的误召回，不是 Agent 是否拒答的判定。"},
    ]


def rag_mode_rows(rag):
    rows = []
    for mode, value in ((rag or {}).get("metrics") or {}).items():
        if not isinstance(value, dict):
            continue
        rows.append({
            "检索模式": mode,
            "正样本": value.get("positive_samples"),
            "recall@1": round(value["recall1"], 4) if isinstance(value.get("recall1"), (int, float)) else None,
            "recall@3": round(value["recall3"], 4) if isinstance(value.get("recall3"), (int, float)) else None,
            "MRR": round(value["mrr"], 4) if isinstance(value.get("mrr"), (int, float)) else None,
            "负样本": value.get("negative_samples"),
            "负样本误召回": value.get("no_answer_false_recall"),
        })
    return rows


def mutation_state(killed, not_applicable=False):
    """A missing verdict is '未记录', never '已检出'."""
    if not_applicable:
        return "不适用"
    if killed is True:
        return "已检出"
    if killed is False:
        return "未检出"
    return "未记录"


def mutation_matrix():
    """B 的历史选定矩阵 + 额外探测；两者分母分开，`killed` 缺失不等于检出。"""
    rows = mutation_rows(True)
    items = []
    for row in rows:
        items.append({
            "变异": row.get("mutation"),
            "用例": row.get("case_id"),
            "来源": row.get("origin"),
            "结果": mutation_state(row.get("killed"), row.get("status") == "not_applicable"),
            "命中规则": ", ".join(row.get("failed_rules") or []) or "未记录",
            "C5": "是" if row.get("c5") else "否",
        })
    return items


def mutation_summary():
    rows = mutation_matrix()
    summary = []
    for row in mutation_totals():
        selected = [r for r in rows if r["变异"] == row["mutation"] and r["来源"] == "选定矩阵"]
        recorded = row["tested"] is not None
        summary.append({
            "变异": row["mutation"],
            "选定组合": row["tested"] if recorded else "未记录",
            "已检出": sum(1 for r in selected if r["结果"] == "已检出") if recorded else "未记录",
            "未检出": sum(1 for r in selected if r["结果"] == "未检出") if recorded else "未记录",
            "不适用": sum(1 for r in selected if r["结果"] == "不适用") if recorded else "未记录",
        })
    return summary


def comparable(left, right):
    """Two batches are only comparable with the same suite and source fingerprint."""
    return (bool(left) and bool(right)
            and left.get("suite_sha256") == right.get("suite_sha256")
            and left.get("source_sha256") == right.get("source_sha256"))


def compare(left, right):
    if not left or not right:
        return None
    steps = {s.get("id"): s for s in right.get("steps") or []}
    rows = []
    for step in left.get("steps") or []:
        other = steps.get(step.get("id")) or {}
        rows.append({
            "步骤": step.get("name"),
            "本批": step.get("status"),
            "对照批": other.get("status") or "未记录",
            "变化": "相同" if other.get("status") == step.get("status") else "不同",
        })
    return {
        "same_suite": left.get("suite_sha256") == right.get("suite_sha256"),
        "same_source": left.get("source_sha256") == right.get("source_sha256"),
        "comparable": comparable(left, right),
        "steps": rows,
        "pytest": _pytest_counts(left, right),
    }


def _pytest_counts(left, right):
    def counts(report):
        step = next((s for s in report.get("steps") or [] if s.get("id") == "pytest"), {})
        details = step.get("details") or {}
        return {k: details.get(k) for k in ("passed", "failed", "skipped", "subtests_passed", "subtests_failed")}
    return [{"批次": "本批", **counts(left)}, {"批次": "对照批", **counts(right)}]
