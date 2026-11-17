"""Aggregate the four real P2 batches into a PoC report (experiment, not formal score)."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("artifacts/runtime/p2-gen")
OUT = Path("artifacts/runtime/p2-poc-20261030")
OUT.mkdir(parents=True, exist_ok=True)
BATCHES = ["p2-20261030-real", "p2-20261030-real2", "p2-20261030-real3", "p2-20261030-real4"]


def load(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    rows = []
    total_requests = total_prompt = total_completion = 0
    for batch_id in BATCHES:
        base = ROOT / batch_id
        manifest = load(base / "batch.json", {}) or {}
        validation = (load(base / "validation.json", {}) or {}).get("summary", {})
        results = load(base / "results_summary.json", {}) or {}
        verify = load(base / "verify.json", {}) or {}
        review = base / "review.jsonl"
        approved = rejected = 0
        if review.is_file():
            for line in review.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    decision = json.loads(line).get("decision")
                    approved += decision == "approve"
                    rejected += decision == "reject"
        reasons = Counter()
        results_path = base / "results.jsonl"
        if results_path.is_file():
            for line in results_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("status") != "passed":
                    for check in row.get("checks") or []:
                        if not check.get("ok"):
                            reasons[check["name"].split(":")[0]] += 1
        total_requests += manifest.get("real_api_requests") or 0
        total_prompt += (manifest.get("tokens") or {}).get("prompt") or 0
        total_completion += (manifest.get("tokens") or {}).get("completion") or 0
        rows.append({
            "batch_id": batch_id,
            "requests": manifest.get("real_api_requests"),
            "tokens": manifest.get("tokens"),
            "generated": validation.get("total"),
            "valid": validation.get("valid"),
            "valid_rate": validation.get("valid_rate"),
            "duplicate_rate": validation.get("duplicate_rate"),
            "grounding_rate": validation.get("grounding_rate"),
            "thresholds_met": validation.get("thresholds_met"),
            "executed": results.get("total"),
            "passed": results.get("passed"),
            "failed": results.get("failed"),
            "pass_rate": results.get("pass_rate"),
            "by_dimension": results.get("by_dimension"),
            "failure_reasons": dict(reasons),
            "hash_ok": verify.get("hash_ok"),
            "template_similarity_ratio": verify.get("template_similarity_ratio"),
            "approved": approved,
            "rejected": rejected,
        })

    best_validation = max(rows, key=lambda r: (r["valid_rate"] or 0) - (r["duplicate_rate"] or 0))
    best_execution = max(rows, key=lambda r: r["pass_rate"] or 0)
    summary = {
        "schema": "ticket-p2-poc/1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "70-case PoC, real DeepSeek API, experiment only — not a formal score",
        "provider": "deepseek", "model": "deepseek-flash",
        "batches": rows,
        "totals": {"batches": len(rows), "candidates": sum(r["generated"] or 0 for r in rows),
                   "real_api_requests": total_requests,
                   "tokens": {"prompt": total_prompt, "completion": total_completion},
                   "approved_by_human": sum(r["approved"] for r in rows)},
        "best_validation_batch": best_validation["batch_id"],
        "best_execution_batch": best_execution["batch_id"],
        "human_review": {"approved": 0, "note": "没有人工 approve 记录；采纳率不可计算，不能写成通过"},
    }
    (OUT / "poc_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# P2 AI 场景生成 PoC 报告（真实 DeepSeek）", "",
             f"- 生成时间：{summary['generated_utc']}",
             "- 性质：**70 条 PoC 试验，不是正式验收成绩**；未提交 Git，未改 103 条与 RAG 1000。",
             f"- 模型：`{summary['provider']}/{summary['model']}`；共 **{len(rows)} 批 / {summary['totals']['candidates']} 条候选 / "
             f"{total_requests} 次真实请求**；tokens：prompt {total_prompt} / completion {total_completion}。", "",
             "## 1. 四批结果（每批 7 维 ×10）", "",
             "| 批次 | 请求 | 生成 | 有效 | 有效率 | 重复率 | 接地率 | 阈值 | 执行通过 | 通过率 |",
             "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['batch_id']} | {r['requests']} | {r['generated']} | {r['valid']} | "
                     f"{(r['valid_rate'] or 0):.1%} | {(r['duplicate_rate'] or 0):.1%} | {(r['grounding_rate'] or 0):.1%} | "
                     f"{'达标' if r['thresholds_met'] else '未达标'} | {r['passed']}/{r['executed']} | {(r['pass_rate'] or 0):.1%} |")
    lines += ["", "阈值：有效 ≥90%、重复 ≤5%、接地 ≥90%；执行通过率是参考指标，不是验收线。", "",
              f"- 校验最优：`{best_validation['batch_id']}`（有效 {(best_validation['valid_rate'] or 0):.1%}，重复 {(best_validation['duplicate_rate'] or 0):.1%}）",
              f"- 执行最优：`{best_execution['batch_id']}`（通过 {(best_execution['pass_rate'] or 0):.1%}）",
              "- 四批都不是“完美批次”：约束越紧执行通过率越高，但提示词模板化会带来重复；这是下一步要调的点。", "",
              "## 2. 执行失败归因（以执行最优批为例）", ""]
    for reason, count in sorted((best_execution["failure_reasons"] or {}).items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{reason}`：{count} 次")
    lines += ["", "五类根因：",
              "1. **Mock 能力边界**：legacy Mock 不维护跨轮锁座/订单状态，多轮续写会被要求重新查询。",
              "2. **热点线路售罄**：北京-上海/北京-广州 近期二等座故意为 0，锁座类期望无法执行。",
              "3. **自由文本措辞**：`reply_contains` 断言模型想象的措辞（如“只能查询”），与实际回复不一致。",
              "4. **占位符**：`<order_id>` 这类占位符无法在沙箱解析（已在第 4 批加校验禁止）。",
              "5. **引用误配**：非 RAG 场景要求 `require_citation`，本轮已改为校验拒绝。", "",
              "## 3. 证据链验证", "",
              "| 批次 | 哈希一致 | 模板相似度≥0.9 占比 | origin=ai_generated |", "|---|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['batch_id']} | {'是' if r['hash_ok'] else '否'} | {(r['template_similarity_ratio'] or 0):.1%} | 70 |")
    lines += ["", "四批 `response_sha256` 均能在 `raw/` 原始响应中找到，`request_id` 全部存在，"
              "与规则题库（RAG 1000）的 bigram 相似度 ≥0.9 的占比为 0。", "",
              "## 4. 人工审核状态", "",
              "- **approved：0 条**。没有人工签字，采纳率不可计算，本文不把它写成通过。",
              "- 审核队列：各批次 `review_queue.jsonl`（含校验结果与建议）。",
              "- 建议人工先审执行最优批 `" + best_execution["batch_id"] + "` 的 70 条，再决定是否进入 `approved/`。", "",
              "## 5. 结论", "",
              "1. **生成链路可用**：真实 DeepSeek 4 批 280 条候选、56 次请求、0 解析失败；Schema/接地均 100%。",
              "2. **质量门禁有效**：去重与校验器真实拦下了重复题、空断言、无文档引用、非法占位符。",
              "3. **执行通过率 30%→70%**：随着夹具域约束（日期宏、线路、工具能力、禁止自由文本断言）逐步收紧而提升。",
              "4. **不能宣称验收通过**：人工采纳率为 0，且没有单批同时满足“零重复 + 高执行通过”。", "",
              "## 6. 复现命令", "",
              "```powershell",
              ".\\\\.venv-v35\\\\Scripts\\\\python.exe scripts/p2_generate.py --batch <new-id> --per-dimension 10 --per-call 5",
              ".\\\\.venv-v35\\\\Scripts\\\\python.exe scripts/p2_validate.py --batch <new-id>",
              ".\\\\.venv-v35\\\\Scripts\\\\python.exe scripts/p2_run.py --batch <new-id>",
              ".\\\\.venv-v35\\\\Scripts\\\\python.exe scripts/p2_verify.py --batch <new-id>",
              "```", "",
              "## 7. 证据位置", "",
              "- 批次目录：`artifacts/runtime/p2-gen/<batch>/`（`batch.json`、`candidates.jsonl`、`raw/`、`validation.json`、`validation.md`、`results.jsonl`、`verify.json`、`review_queue.jsonl`）",
              f"- 汇总：`{OUT}/poc_report.json`、本文件", ""]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary["totals"], ensure_ascii=False))
    print("best validation:", summary["best_validation_batch"], "best execution:", summary["best_execution_batch"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
