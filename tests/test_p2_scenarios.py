"""Approved P2 scenarios as pytest cases. Empty approved set skips (never fakes a pass).

Every execution row keeps: case_id, batch_id, run_id, dimension, engine, checks.
Results go to artifacts/runtime/p2-results/ and are separate from P0/RAG1000.
"""
import json
import os
from pathlib import Path

import pytest

from target.p2_executor import run_case
from target.p2_review import load_approved

CASES, REJECTED = load_approved()
if REJECTED:
    print(f"P2 approved loader rejected {len(REJECTED)} rows: {REJECTED[:5]}")

RESULTS_DIR = Path(os.getenv("P2_RESULTS_DIR", "artifacts/runtime/p2-results"))


def _record(payload):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with (RESULTS_DIR / "results.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


if not CASES:
    def test_no_approved_p2_scenarios():
        """Collected but skipped, so pytest exit code stays 0 and no pass is faked."""
        pytest.skip("no approved P2 scenarios (human approval required)")
else:
    @pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
    def test_approved_p2_scenario(case, record_property):
        result = run_case(case)
        payload = {
            "suite": "p2",
            "case_id": case["case_id"],
            "batch_id": (case.get("provenance") or {}).get("batch_id"),
            "run_id": result.get("run_id"),
            "dimension": case["dimension"],
            "engine": result.get("engine"),
            "status": result["status"],
            "checks": result["checks"],
            "failed": result["failed"],
            "latency_ms": result["latency_ms"],
            "reviewer": (case.get("review") or {}).get("reviewer"),
            "reviewed_utc": (case.get("review") or {}).get("reviewed_utc"),
        }
        for key in ("case_id", "batch_id", "run_id", "dimension", "engine"):
            record_property(key, payload[key])
        _record(payload)
        assert result["status"] == "passed", json.dumps(payload, ensure_ascii=False)
