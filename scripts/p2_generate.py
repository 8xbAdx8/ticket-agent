"""P2 generator CLI: real model calls, 7 dimensions, append-only batch.

Example:
  python scripts/p2_generate.py --batch p2-20261101-abc --per-call 5
  python scripts/p2_generate.py --dry-run          # prompts only, no API
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Provider selection must happen before config is imported anywhere below.
os.environ.setdefault("AGENT_PROVIDER", "bailian" if "--provider" in sys.argv and "bailian" in sys.argv else "deepseek")
os.environ.setdefault("AGENT_ENGINE", "langchain")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from target import p2_generator, p2_packets, p2_store  # noqa: E402
from target.p2_case import DIMENSIONS, DIM_CODE  # noqa: E402

B = Path(__file__).resolve().parent.parent


def existing_questions():
    questions = []
    catalog = B / "web/datasets/b_v32_20261020/case_catalog.json"
    if catalog.is_file():
        questions.extend(row.get("message") or row.get("name") for row in json.loads(catalog.read_text(encoding="utf-8-sig")))
    cases = B / "data/rag1000/v1.1.1/cases.jsonl"
    if cases.is_file():
        for line in cases.read_text(encoding="utf-8").splitlines()[:400]:
            if line.strip():
                questions.append(json.loads(line).get("question"))
    return [q for q in questions if q]


def emit_event(batch, kind, **fields):
    from target.run_events import capture, emit
    with capture(batch.events_path) as state:
        state.update(run_id=batch.batch_id, session_id="p2-generator",
                     provider=batch.manifest.get("provider"), model=batch.manifest.get("model"), last=None)
        return emit(kind, **fields)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", default="p2-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--provider", default="deepseek", choices=["deepseek", "bailian"])
    parser.add_argument("--per-call", type=int, default=5)
    parser.add_argument("--per-dimension", type=int, default=10)
    parser.add_argument("--dimension", default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    dimensions = list(DIMENSIONS) if args.dimension == "all" else [args.dimension]
    packets = p2_packets.build_all()
    avoid = existing_questions()
    generated_questions = []
    batch = p2_store.Batch(args.batch, provider=args.provider,
                           model="deepseek-flash" if args.provider == "deepseek" else "qwen")

    if args.dry_run:
        out = {}
        for dimension in dimensions:
            user = p2_generator.build_user(dimension, packets[dimension], args.per_call, avoid)
            out[dimension] = {"system_chars": len(p2_generator.SYSTEM), "user": user,
                              "prompt_sha256": p2_generator.prompt_sha(p2_generator.SYSTEM, user)}
        path = batch.write_json("dry_run_prompts.json", out)
        print(f"dry-run: {path} ({len(out)} dimensions), no API call")
        return 0

    from target.deepseek_runtime import Settings, validate_configuration
    validate_configuration()
    settings = Settings(max_output_tokens=3072, timeout=40, max_model_calls=1)
    batch.save_manifest(model="deepseek-flash" if args.provider == "deepseek" else "qwen",
                        structured_mode="native_json")
    seq = {}
    total_requests, errors = 0, []
    for dimension in dimensions:
        if batch.manifest.get("dimensions", {}).get(dimension, {}).get("generated", 0) and not args.force:
            print(f"skip {dimension}: already generated")
            continue
        remaining = args.per_dimension
        emit_event(batch, "p2_gen_started", dimension=dimension, requested=args.per_dimension,
                   provider=args.provider, model=batch.manifest.get("model"))
        while remaining > 0:
            count = min(args.per_call, remaining)
            result = p2_generator.generate(
                args.provider, settings, dimension, packets[dimension], count,
                list(avoid) + generated_questions, run_id=batch.batch_id)
            total_requests += len(result["request_ids"])
            batch.save_raw(f"{DIM_CODE[dimension]}_{seq.get(dimension, 0) + 1}", {
                "dimension": dimension, "raw": result["raw"], "error": result["error"],
                "request_ids": result["request_ids"], "usage": result["usage"],
                "prompt_sha256": result["prompt_sha256"],
            })
            if not result["ok"]:
                errors.append(f"{dimension}:{result['error']}")
                emit_event(batch, "p2_gen_failed", dimension=dimension, error=result["error"],
                           attempts=result["attempts"])
                break
            seq[dimension] = seq.get(dimension, 0) + len(result["scenarios"])
            cases = p2_generator.normalize(
                result["scenarios"], dimension, args.provider, batch.manifest.get("model"),
                response_sha=p2_store.sha_text(result["raw"]),
                request_id=(result["request_ids"] or [None])[0],
                prompt_sha256=result["prompt_sha256"], start_seq=seq[dimension] - len(result["scenarios"]) + 1)
            for case in cases:
                case["provenance"]["batch_id"] = batch.batch_id
                case["provenance"]["generated_utc"] = datetime.now(timezone.utc).isoformat()
                batch.append(case)
                generated_questions.append(" ".join(case.get("turns") or []))
            remaining -= len(cases)
            batch.record_generation(dimension, len(cases), result["request_ids"], result["usage"],
                                    [] if result["ok"] else [result["error"]])
            emit_event(batch, "p2_gen_completed", dimension=dimension, generated=len(cases),
                       request_ids=result["request_ids"], tokens=result["usage"],
                       prompt_sha256=result["prompt_sha256"])
    batch.save_manifest(status="candidates", per_dimension=args.per_dimension,
                        per_call=args.per_call, dimensions_requested=dimensions,
                        errors=errors, candidates=batch.count_candidates())
    print(f"batch {batch.batch_id}: {batch.count_candidates()} candidates, {total_requests} requests, errors={errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
