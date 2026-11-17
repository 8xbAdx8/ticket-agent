"""P2 validator: 7 deterministic checks, no model, no network.

Writes validation.json, review_queue.jsonl and validation.md into the batch directory.
Exit 2 when the PoC thresholds are not met.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from target import p2_case, p2_packets  # noqa: E402
from target.p2_store import Batch  # noqa: E402

B = Path(__file__).resolve().parent.parent


def existing_questions():
    questions = []
    catalog = B / "web/datasets/b_v32_20261020/case_catalog.json"
    if catalog.is_file():
        questions.extend(row.get("message") for row in json.loads(catalog.read_text(encoding="utf-8-sig")))
    cases = B / "data/rag1000/v1.1.1/cases.jsonl"
    if cases.is_file():
        for line in cases.read_text(encoding="utf-8").splitlines()[:400]:
            if line.strip():
                questions.append(json.loads(line).get("question"))
    return [q for q in questions if q]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()

    batch = Batch(args.batch)
    candidates = batch.load_candidates()
    docs = p2_packets.corpus_docs()
    tools = p2_packets.tool_specs()
    prior = existing_questions()

    seen = []
    items, review = [], []
    status_count = {"valid": 0, "invalid": 0}
    for case in candidates:
        errors, warnings = p2_case.validate_case(case, docs=docs, tools=tools,
                                                 existing_questions=prior, batch_questions=seen)
        if not str(case.get("case_id", "")).startswith("P2-"):
            errors.append("case_id_prefix")
        if case.get("dimension") not in p2_case.DIMENSIONS:
            errors.append("dimension_unknown")
        question = " ".join(case.get("turns") or [])
        seen.append(question)
        status = "valid" if not errors else "invalid"
        status_count[status] += 1
        item = {"case_id": case.get("case_id"), "dimension": case.get("dimension"),
                "status": status, "errors": errors, "warnings": warnings,
                "packet_id": case.get("packet_id")}
        items.append(item)
        review.append({**case, "review_status": "pending", "validation": item})

    dimensions = {}
    for case, item in zip(candidates, items):
        dim = case.get("dimension", "?")
        row = dimensions.setdefault(dim, {"total": 0, "valid": 0, "invalid": 0, "errors": {}})
        row["total"] += 1
        row[item["status"]] += 1
        for error in item["errors"]:
            key = error.split(":")[0]
            row["errors"][key] = row["errors"].get(key, 0) + 1

    total = len(candidates)
    valid = status_count["valid"]
    duplicates = sum(1 for item in items if "duplicate_question" in item["errors"])
    grounding = sum(1 for item in items if any(e.startswith(("quote_not_verbatim", "evidence_doc_missing",
                                                             "doc_not_in_corpus")) for e in item["errors"]))
    schema_bad = sum(1 for item in items if any(e.startswith(("missing:", "unknown_", "bad_")) for e in item["errors"]))
    summary = {
        "batch_id": args.batch, "generated_utc": datetime.now(timezone.utc).isoformat(),
        "total": total, "valid": valid, "invalid": total - valid,
        "valid_rate": round(valid / total, 4) if total else 0,
        "duplicate": duplicates, "duplicate_rate": round(duplicates / total, 4) if total else 0,
        "grounding_fail": grounding, "grounding_rate": round(1 - grounding / total, 4) if total else 0,
        "schema_fail": schema_bad, "schema_rate": round(1 - schema_bad / total, 4) if total else 0,
        "dimensions": dimensions,
        "thresholds": {"valid_rate": 0.9, "duplicate_rate": 0.05, "grounding_rate": 0.9},
    }
    summary["thresholds_met"] = (summary["valid_rate"] >= 0.9 and summary["duplicate_rate"] <= 0.05
                                 and summary["grounding_rate"] >= 0.9)
    batch.write_json("validation.json", {"summary": summary, "items": items})
    with (batch.dir / "review_queue.jsonl").open("w", encoding="utf-8") as stream:
        for row in review:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    lines = [f"# P2 校验报告：{args.batch}", "",
             f"- 候选：{total}；有效：{valid}（{summary['valid_rate']:.1%}）；无效：{total - valid}",
             f"- 重复：{duplicates}（{summary['duplicate_rate']:.1%}）；接地失败：{grounding}；Schema 失败：{schema_bad}",
             f"- 阈值：{'达标' if summary['thresholds_met'] else '未达标'}（有效≥90%、重复≤5%、接地≥90%）", "",
             "| 维度 | 总数 | 有效 | 无效 | 主要错误 |", "|---|---|---|---|---|"]
    for dim, row in sorted(dimensions.items()):
        errs = ", ".join(f"{k}×{v}" for k, v in sorted(row["errors"].items(), key=lambda kv: -kv[1])[:3]) or "-"
        lines.append(f"| {dim} | {row['total']} | {row['valid']} | {row['invalid']} | {errs} |")
    invalids = [item for item in items if item["status"] == "invalid"][:20]
    if invalids:
        lines += ["", "## 无效样本（前 20）", ""]
        for item in invalids:
            lines.append(f"- `{item['case_id']}`：{'; '.join(item['errors'][:4])}")
    (batch.dir / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    batch.save_manifest(status="validated", validation=summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["thresholds_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
