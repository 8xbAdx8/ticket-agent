"""Run P2 scenarios in an isolated offline sandbox (Mock provider, fresh DB per case).

Default: all candidates of a batch (sandbox measurement, NOT a formal score).
--approved-only: only cases with review decision=approve (formal track).
"""
import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from target.p2_executor import run_case  # noqa: E402
from target.p2_store import Batch  # noqa: E402


def approved_ids(batch):
    path = batch.dir / "review.jsonl"
    if not path.is_file():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("decision") == "approve":
            ids.add(row.get("case_id"))
    return ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--engine", default="legacy", choices=["legacy"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--approved-only", action="store_true")
    args = parser.parse_args()

    batch = Batch(args.batch)
    cases = batch.load_candidates()
    if args.approved_only:
        keep = approved_ids(batch)
        cases = [c for c in cases if c.get("case_id") in keep]
        if not cases:
            print("no approved cases")
            return 0
    if args.limit:
        cases = cases[:args.limit]

    rows = [run_case(case, engine=args.engine) for case in cases]
    counts = Counter(row["status"] for row in rows)
    by_dim = {}
    for row in rows:
        dim = by_dim.setdefault(row["dimension"], Counter())
        dim[row["status"]] += 1
    summary = {"batch_id": args.batch, "ran_utc": datetime.now(timezone.utc).isoformat(),
               "engine": args.engine, "mode": "approved" if args.approved_only else "sandbox",
               "total": len(rows), "passed": counts["passed"], "failed": counts["failed"],
               "error": counts["error"],
               "pass_rate": round(counts["passed"] / len(rows), 4) if rows else 0,
               "by_dimension": {k: dict(v) for k, v in by_dim.items()},
               "note": "sandbox measurement only; failures may be real defects or wrong expectations"}
    (batch.dir / "results.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    batch.write_json("results_summary.json", summary)
    batch.save_manifest(status="executed" if args.approved_only else "sandbox_executed")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
