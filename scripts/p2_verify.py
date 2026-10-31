"""Verify a P2 batch: hashes, request ids, prompt fingerprints, template divergence."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from target import p2_case  # noqa: E402
from target.p2_store import Batch, sha_text  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    batch = Batch(args.batch)
    cases = batch.load_candidates()
    raws = {}
    for path in (batch.dir / "raw").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        raws[path.name] = {"sha": sha_text(data.get("raw") or ""), "prompt": data.get("prompt_sha256"),
                           "request_ids": data.get("request_ids") or []}
    raw_shas = {row["sha"] for row in raws.values()}
    problems = []
    for case in cases:
        prov = case.get("provenance") or {}
        if prov.get("response_sha256") not in raw_shas:
            problems.append({"case": case.get("case_id"), "issue": "response_sha_not_in_raw"})
        if not prov.get("prompt_sha256"):
            problems.append({"case": case.get("case_id"), "issue": "missing_prompt_sha"})
        if not prov.get("request_id"):
            problems.append({"case": case.get("case_id"), "issue": "missing_request_id"})
    questions = [" ".join(c.get("turns") or []) for c in cases]
    rag = Path("data/rag1000/v1.1.1/cases.jsonl")
    template_like = 0
    if rag.is_file():
        banks = [json.loads(line).get("question") for line in rag.read_text(encoding="utf-8").splitlines()[:1000] if line.strip()]
        grams = [(q, p2_case.bigrams(q)) for q in questions]
        for question, gram in grams:
            if any(p2_case.jaccard(gram, p2_case.bigrams(other)) >= 0.9 for other in banks if other):
                template_like += 1
    ratio = round(template_like / len(questions), 4) if questions else 0
    manifest = batch.manifest
    result = {
        "batch_id": args.batch,
        "candidates": len(cases),
        "raw_responses": len(raws),
        "real_api_requests": manifest.get("real_api_requests"),
        "request_ids": len(manifest.get("request_ids") or []),
        "tokens": manifest.get("tokens"),
        "hash_problems": problems[:20],
        "hash_ok": not problems,
        "template_similarity_ge_0.9": template_like,
        "template_similarity_ratio": ratio,
        "template_check_pass": ratio < 0.05,
        "origin_ai_generated": sum(1 for c in cases if (c.get("provenance") or {}).get("origin") == "ai_generated"),
    }
    batch.write_json("verify.json", result)
    print(json.dumps({k: result[k] for k in ("candidates", "real_api_requests", "hash_ok", "template_similarity_ratio",
                                            "template_check_pass", "origin_ai_generated")}, ensure_ascii=False))
    return 0 if result["hash_ok"] and result["template_check_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
