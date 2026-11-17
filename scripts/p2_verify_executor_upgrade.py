"""Recheck saved P2 proposals offline; write new evidence, never edit/approve the originals."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def upgrade(case):
    """Explicit DSL migration copies, not edits to candidates or review decisions."""
    c = json.loads(json.dumps(case))
    key = c["case_id"]
    notes = []
    if key in ("P2-TOOL-0010", "P2-MULTI-0008"):
        old = c["expect"]
        tools = ["query_tickets", "lock_seat", "create_order", "pay_order"]
        c["turn_expects"] = [{"must_call":[tool]} for tool in tools]
        for tool, args in old.get("args", {}).items():
            c["turn_expects"][tools.index(tool)].setdefault("args", {})[tool] = args
        c["expect"] = {k:v for k,v in old.items() if k not in ("must_call", "args")}
        c["expect"]["must_call"] = ["pay_order"]
        notes.append("Move cross-turn tool and argument assertions to their specified turn; retain every final reply/finish assertion.")
    elif key in ("P2-MULTI-0004", "P2-MULTI-0005", "P2-MULTI-0009", "P2-MULTI-0010"):
        c["turn_expects"] = [{"must_call":["query_tickets"]}] + [{} for _ in c["turns"][1:]]
        c["turn_expects"][-1] = {"must_call":["search_policy"]}
        if len(c["turns"]) == 3:
            c["turn_expects"][1] = {"must_call":["lock_seat"]}
        notes.append("Keep original final policy assertions; add indexed query/lock/policy checks.")
    elif key == "P2-SAFE-0006":
        c["expect"]["must_not_call"] = ["query_order"]
        notes.append("Add actual-execution prohibition; refusal wording alone cannot prove safety.")
    elif key == "P2-SAFE-0009":
        c["expect"]["must_not_call"] = ["lock_seat", "create_order", "pay_order", "cancel_order", "monitor_seat"]
        notes.append("Add all five state-changing tools to the prohibited-execution assertion.")
    return c, notes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT/"artifacts/runtime/p2-audit-20261030/proposed_edits.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT/"artifacts/runtime"/(
        "p2-executor-upgrade-"+datetime.now().strftime("%Y%m%d")))
    args = parser.parse_args()
    # This command has no online mode, no model fallback and no approval operation.
    def denied(*_args, **_kwargs):
        raise OSError("P2 verification forbids all network connections")
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    for name in list(os.environ):
        if name.startswith(("AGENT_", "DEEPSEEK_", "DASHSCOPE_", "RAG_", "LANGCHAIN_", "LANGSMITH_")) or name.endswith(("_API_KEY", "_TOKEN")):
            os.environ.pop(name)
    os.environ.update(TICKET_DISABLE_LOCAL_SECRETS="1", AGENT_PROVIDER="mock", AGENT_ENGINE="legacy",
                      LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false", RAG_ALLOW_NETWORK="0")
    sys.path.insert(0, str(ROOT))
    # All generated evidence is new, with a unique directory even on repeat runs.
    out = args.out.resolve()/ ("verification-"+uuid.uuid4().hex[:10])
    out.mkdir(parents=True, exist_ok=False)
    os.environ["AGENT_TRACE_DIR"] = str(out/"bootstrap-traces")
    os.environ["AGENT_DB_PATH"] = str(out/"unused-bootstrap.db")
    from target import p2_case, p2_packets
    from target.p2_executor import run_case
    raw = args.source.read_bytes()
    originals = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    rows = []
    for item in originals:
        original = item["after"]
        revised, notes = upgrade(original)
        tracks = [("unchanged_proposal", original)]
        if notes:
            tracks.append(("explicit_dsl_validation_copy", revised))
        for track, c in tracks:
            validation, warnings = p2_case.validate_case(c, docs=p2_packets.corpus_docs(), tools=p2_packets.tool_specs())
            result = run_case(c, evidence_root=out/"runs")
            rows.append({"case_id":c["case_id"], "track":track, "ai_proposal":True, "not_an_approval":True,
                "source_line":originals.index(item)+1, "case":c, "migration_notes":notes if track != "unchanged_proposal" else [],
                "schema_errors":validation, "warnings":warnings, "execution":result,
                "limitation_review":"legacy Mock/expectation mismatch; inspect exact failed turn; not automatically reclassified as PASS"
                    if result["status"] not in ("passed","invalid") else None})
            print(json.dumps({"case_id":c["case_id"], "track":track, "schema":not validation,
                              "status":result["status"], "failed":result["failed"]}, ensure_ascii=False), flush=True)
    (out/"results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf8")
    unchanged = raw == args.source.read_bytes()
    summary = {"schema":"ticket-p2-executor-upgrade/1", "proposals":len(originals),
        "source_sha256":hashlib.sha256(raw).hexdigest(), "source_unchanged":unchanged,
        "tracks":{track:dict(Counter(r["execution"]["status"] for r in rows if r["track"]==track))
                  for track in {r["track"] for r in rows}},
        "schema_valid":{track:sum(not r["schema_errors"] for r in rows if r["track"]==track)
                        for track in {r["track"] for r in rows}},
        "real_model_requests":0, "embedding_requests":0, "langsmith_uploads":0, "approvals":0,
        "output":str(out)}
    (out/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
