"""P2 human review channel: approve / reject / edit, publish and gated loading.

Rules enforced here (not by convention):
- Only a named human reviewer can approve. AI/system labels are rejected.
- Sandbox pass alone never approves anything.
- An edited case must pass full re-validation before it can be approved.
- Approved cases are copied to data/p2_scenarios/approved/ with review evidence.
- load_approved() re-validates every row and drops anything without a human approval.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_APPROVED = Path("data/p2_scenarios/approved")
FORBIDDEN_REVIEWERS = {"ai", "assistant", "model", "system", "auto", "bot", "deepseek", "qwen",
                       "gpt", "claude", "codex", "agent", "auto-approve", "automation"}
DECISIONS = ("approve", "reject", "edit")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def reviewer_ok(reviewer):
    name = str(reviewer or "").strip()
    if len(name) < 2:
        return False
    lowered = name.lower()
    if lowered in FORBIDDEN_REVIEWERS:
        return False
    if re.fullmatch(r"(ai|system|auto|model|bot)[-_ ].*", lowered):
        return False
    return True


def validate_case(case):
    from target import p2_case, p2_packets
    return p2_case.validate_case(case, docs=p2_packets.corpus_docs(), tools=p2_packets.tool_specs())


def _reviews(batch):
    path = batch.dir / "review.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_edit(batch, case_id):
    rows = [row for row in _reviews(batch)
            if row.get("case_id") == case_id and row.get("decision") in ("edit", "edit_invalid")]
    return rows[-1] if rows else None


def review_case(batch_id, case_id, decision, reviewer, reason="", edited=None, *,
                batch_root=None, approved_dir=None):
    """Record one review action. Approval publishes the case; edit only records a revision."""
    from target.p2_store import Batch
    if decision not in DECISIONS:
        raise ValueError("invalid_decision")
    if not reviewer_ok(reviewer):
        raise ValueError("human_reviewer_required")
    if decision in ("reject", "edit") and not str(reason).strip():
        raise ValueError("reason_required")
    batch = Batch(batch_id, root=batch_root or Path("artifacts/runtime/p2-gen"))
    case = next((row for row in batch.load_candidates() if row.get("case_id") == case_id), None)
    if not case:
        raise ValueError("case_not_found")
    if not str(case_id).startswith("P2-"):
        raise ValueError("case_id_not_p2")
    record = {"schema": "ticket-p2-review/1", "case_id": case_id, "batch_id": batch_id,
              "decision": decision, "reviewer": str(reviewer).strip(), "reviewed_utc": now(),
              "reason": str(reason).strip(),
              "candidate_sha256": sha_json(case)}
    if decision == "edit":
        if not isinstance(edited, dict) or not edited:
            raise ValueError("edited_payload_required")
        merged = json.loads(json.dumps(case))
        merged.update({key: value for key, value in edited.items() if key not in ("provenance", "case_id", "batch_id")})
        merged.setdefault("provenance", case.get("provenance"))
        merged["provenance"] = {**case.get("provenance", {}), "edited": True,
                                "edited_utc": now(), "edited_by": str(reviewer).strip()}
        errors, _ = validate_case(merged)
        record["edited_case_sha256"] = sha_json(merged)
        record["edited_case"] = merged
        record["validation"] = {"status": "valid" if not errors else "invalid", "errors": errors}
        if errors:
            record["decision"] = "edit_invalid"
    elif decision == "approve":
        edit = latest_edit(batch, case_id)
        if edit and edit.get("decision") != "edit":
            # An invalid edit must block approval: the reviewer's intended content
            # was rejected, so approving the old text silently would be wrong.
            raise ValueError("edit_invalid_pending")
        base = (edit or {}).get("edited_case") if edit else None
        base = base or case
        errors, _ = validate_case(base)
        if errors:
            raise ValueError("approved_case_invalid:" + ",".join(errors[:3]))
        if not base.get("provenance", {}).get("batch_id"):
            raise ValueError("missing_batch_provenance")
        record["validation"] = {"status": "valid", "errors": [], "revalidated_utc": now()}
        record["approved_case"] = base
        _publish(base, record, approved_dir or Path(os.getenv("P2_APPROVED_DIR", str(DEFAULT_APPROVED))))
    with (batch.dir / "review.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _publish(case, record, approved_dir):
    approved_dir = Path(approved_dir)
    approved_dir.mkdir(parents=True, exist_ok=True)
    row = json.loads(json.dumps(case))
    row["review"] = {"decision": "approve", "reviewer": record["reviewer"],
                     "reviewed_utc": record["reviewed_utc"], "reason": record["reason"],
                     "validation": record["validation"]}
    row["provenance"] = {**row.get("provenance", {}), "review_status": "approved"}
    path = approved_dir / f"{record['batch_id']}.jsonl"
    existing = []
    if path.is_file():
        existing = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    existing = [item for item in existing if item.get("case_id") != row["case_id"]]
    existing.append(row)
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in existing) + "\n", encoding="utf-8")
    return path


def load_approved(directory=None):
    """Return (approved_cases, rejected). Every row is re-validated on load."""
    directory = Path(directory or os.getenv("P2_APPROVED_DIR", str(DEFAULT_APPROVED)))
    approved, rejected = {}, []
    if not directory.is_dir():
        return [], []
    latest = {}
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                rejected.append({"case_id": None, "file": path.name, "reason": "invalid_json"})
                continue
            latest[row.get("case_id")] = row
    for case_id, row in latest.items():
        review = row.get("review") or {}
        if review.get("decision") != "approve":
            rejected.append({"case_id": case_id, "reason": "not_approved"})
            continue
        if not reviewer_ok(review.get("reviewer")):
            rejected.append({"case_id": case_id, "reason": "human_reviewer_required"})
            continue
        if not review.get("reviewed_utc"):
            rejected.append({"case_id": case_id, "reason": "missing_review_time"})
            continue
        if not str(case_id).startswith("P2-"):
            rejected.append({"case_id": case_id, "reason": "not_p2_namespace"})
            continue
        if str(row.get("dataset_version") or "").startswith("rag1000"):
            rejected.append({"case_id": case_id, "reason": "rag1000_source"})
            continue
        errors, _ = validate_case(row)
        if errors:
            rejected.append({"case_id": case_id, "reason": "invalid_on_load:" + ",".join(errors[:3])})
            continue
        approved[case_id] = row
    return list(approved.values()), rejected
