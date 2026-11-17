"""P2 review CLI: list pending cases, approve / reject / edit.

Examples:
  python scripts/p2_review.py --batch p2-... list
  python scripts/p2_review.py --batch p2-... approve --case-id P2-RAG-0001 --reviewer 张三 --reason 依据充分
  python scripts/p2_review.py --batch p2-... edit --case-id P2-RAG-0001 --reviewer 张三 --reason 修正措辞 --edited-file edits.json
  python scripts/p2_review.py --batch p2-... reject --case-id P2-RAG-0001 --reviewer 张三 --reason 期望不可判定
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from target import p2_review  # noqa: E402
from target.p2_store import Batch  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--batch-root", default="artifacts/runtime/p2-gen")
    parser.add_argument("--approved-dir", default=None)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    for name in ("approve", "reject", "edit"):
        node = sub.add_parser(name)
        node.add_argument("--case-id", required=True)
        node.add_argument("--reviewer", required=True)
        node.add_argument("--reason", default="")
        if name == "edit":
            node.add_argument("--edited-file", required=True)
    args = parser.parse_args()

    batch = Batch(args.batch, root=Path(args.batch_root))
    if args.action == "list":
        results_path = batch.dir / "results.jsonl"
        sandbox = {}
        if results_path.is_file():
            for line in results_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    sandbox[row["id"]] = row["status"]
        reviewed = {}
        review_path = batch.dir / "review.jsonl"
        if review_path.is_file():
            for line in review_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    reviewed[row["case_id"]] = row["decision"]
        for case in batch.load_candidates():
            print(f'{case["case_id"]}\t{case["dimension"]}\t'
                  f'sandbox={sandbox.get(case["case_id"], "-")}\treview={reviewed.get(case["case_id"], "pending")}\t'
                  f'{case.get("title", "")[:30]}')
        return 0

    edited = None
    if args.action == "edit":
        edited = json.loads(Path(args.edited_file).read_text(encoding="utf-8"))
    try:
        record = p2_review.review_case(args.batch, args.case_id, args.action, args.reviewer,
                                       reason=args.reason, edited=edited,
                                       batch_root=Path(args.batch_root),
                                       approved_dir=Path(args.approved_dir) if args.approved_dir else None)
    except ValueError as exc:
        print(f"REJECTED: {exc}")
        return 2
    print(json.dumps({"case_id": record["case_id"], "decision": record["decision"],
                      "reviewer": record["reviewer"], "validation": record.get("validation")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
