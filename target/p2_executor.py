"""Execute one P2 scenario against the real Agent in an isolated sandbox (offline Mock)."""
import copy
import json
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from unittest.mock import patch

import config


_SANDBOX_LOCK = RLock()  # config paths are process-wide; cases must not share them.


@contextmanager
def _fresh(engine="legacy", evidence_root=None):
    from target import providers
    from target.agent import Agent
    root = Path(evidence_root or config.BASE_DIR / "artifacts/runtime")
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="p2-exec-", dir=root))
    traces = folder / "traces"
    traces.mkdir()
    # No model selection or retrieval path may be inherited from a Live shell.
    with _SANDBOX_LOCK, patch.multiple(config, DB_PATH=folder / "tickets.db", TRACE_DIR=traces,
            PROVIDER="mock", ENGINE="legacy", USE_HTTP_MOCK=False, USE_VECTOR_RAG=False), \
         patch.dict("os.environ", {"AGENT_RAG_MODE":"", "RAG_ALLOW_NETWORK":"0",
            "LANGCHAIN_TRACING_V2":"false", "LANGSMITH_TRACING":"false"}):
        yield Agent(providers.MockProvider(mutations={}), engine="legacy", mutations={}), folder


def _expand(value, today):
    if isinstance(value, str):
        match = re.fullmatch(r"<rel_date:([+-]\d+)>", value)
        if match:
            from datetime import timedelta
            return (today + timedelta(days=int(match.group(1)))).isoformat()
        return value
    if isinstance(value, dict):
        return {k: _expand(v, today) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v, today) for v in value]
    return value


def _subset(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and all(x in actual for x in expected)
    return expected == actual


def _calls(result):
    rows = []
    for step in result.get("steps") or []:
        for call in step.get("calls") or []:
            rows.append(call)
    return rows


def _train_numbers(result):
    found = set()
    for call in _calls(result):
        preview = call.get("result_preview")
        text = preview if isinstance(preview, str) else json.dumps(preview or {}, ensure_ascii=False)
        found.update(re.findall(r"G\d{3,4}", text))
    return found


def evaluate(case, result, today, *, executions=None):
    expect = case.get("expect") or {}
    checks = []
    reply = str(result.get("reply") or "")
    # Five-field public calls do not tell a rejected proposal from an execution.
    # Unknown evidence must never turn a forbidden-tool assertion into a pass.
    calls = executions if executions is not None else [dict(c, executed=None) for c in _calls(result)]
    sequence = [c["tool"] for c in calls if c.get("executed") is True]

    if "must_call" in expect:
        missing = [t for t in expect["must_call"] if t not in sequence]
        checks.append(("must_call", not missing, f"missing={missing}"))

    if "must_not_call" in expect:
        forbidden = expect["must_not_call"]
        violations = [t for t in sequence if t in forbidden]
        unknown = [c["tool"] for c in calls if c.get("executed") is None and c.get("tool") in forbidden]
        checks.append(("must_not_call", not violations and not unknown,
                       f"violations={violations}; execution_unknown={unknown}"))

    for tool, expected in (expect.get("args") or {}).items():
        matched = [c for c in calls if c.get("tool") == tool and c.get("executed") is True]
        ok = any(_subset(_expand(expected, today), _expand(c.get("args") or {}, today)) for c in matched)
        checks.append((f"args:{tool}", ok, f"calls={len(matched)}"))

    if "reply_contains" in expect:
        missing = [x for x in expect["reply_contains"] if x not in reply]
        checks.append(("reply_contains", not missing, f"missing={missing}"))

    if "reply_not_contains" in expect:
        hit = [x for x in expect["reply_not_contains"] if x in reply]
        checks.append(("reply_not_contains", not hit, f"hit={hit}"))

    if "finish_reason" in expect:
        checks.append(("finish_reason", result.get("finish_reason") == expect["finish_reason"],
                       f"actual={result.get('finish_reason')}"))

    if expect.get("require_citation"):
        docs = case.get("expected_doc_ids") or []
        hit = [d for d in docs if d in reply]
        checks.append(("require_citation", bool(hit), f"cited={hit}"))

    passed = all(ok for _, ok, _ in checks)
    failed = [name for name, ok, _ in checks if not ok]
    return passed, failed, checks


def _executions(events, result, dispatches=None):
    """Project actual producer events, retaining blocked and unresolved proposals."""
    rows = {}
    for event_index, event in enumerate(events):
        kind = event.get("event_type")
        if kind not in ("model_tool_proposed", "tool_proposed", "tool_start", "tool_result"):
            continue
        key = event.get("call_id") or event["event_id"]
        row = rows.setdefault(key, {"tool":event.get("tool"), "call_id":event.get("call_id"),
                                   "args":{}, "executed":None, "event_ids":[]})
        row["event_ids"].append(event["event_id"])
        if "args" in event:
            row["args"] = event["args"]
        if kind == "tool_start":
            row.update(executed=True, started_at=event["timestamp"], execution_event_index=event_index)
        if kind == "tool_result":
            row.update(executed=event.get("executed"), ok=event.get("status")=="succeeded",
                       result=event.get("output"), duration_ms=event.get("duration_ms"))
            row.setdefault("execution_event_index", event_index)
    # Missing instrumentation is explicit unknown, not proof that a call was safe.
    known = {r["tool"] for r in rows.values()}
    for tool in result.get("tool_sequence") or []:
        if tool not in known:
            rows["unrecorded:"+tool] = {"tool":tool, "executed":None, "args":{}, "event_ids":[]}
    # Assertion input uses the dispatcher's original arguments in memory. Saved
    # events mask phones/passengers, so comparing their masks would lose identity.
    for call_id, row in rows.items():
        entry = (dispatches or {}).get(call_id, {})
        if "args" in entry:
            row["args"] = copy.deepcopy(entry["args"])
    return sorted(rows.values(), key=lambda row: row.get("execution_event_index", len(events)))


def _checks(expect, case, result, executions, today, *, scope, turn_index, run_id):
    _, _, checks = evaluate(dict(case, expect=expect), result, today, executions=executions)
    actual = [r["tool"] for r in executions if r.get("executed") is True]
    return [{"name":name, "ok":ok, "detail":detail, "scope":scope,
             "turn_index":turn_index, "run_id":run_id,
             "expected_tools":list(expect.get("must_call", [])), "actual_tools":actual,
             "forbidden_tools":list(expect.get("must_not_call", [])),
             "violating_tools":[t for t in actual if t in expect.get("must_not_call", [])]
             if name == "must_not_call" else []} for name, ok, detail in checks]


def run_case(case, engine="legacy", *, evidence_root=None):
    """One fresh offline DB per case. expect = final turn; turn_expects = indexed turns.

    All supplied assertions are evaluated (AND); execution success never approves a case.
    Original return keys stay available; turn_results and aggregate_tool_sequence are additive.
    """
    from target import p2_case, p2_packets
    from target.run_events import capture, finish, emit
    from target.diagnostics import sanitize
    started = time.perf_counter()
    errors, warnings = p2_case.validate_case(case, docs=p2_packets.corpus_docs(), tools=p2_packets.tool_specs())
    base = {"id":case.get("case_id"), "case_id":case.get("case_id"), "dimension":case.get("dimension"),
            "batch_id":(case.get("provenance") or {}).get("batch_id"), "run_id":None,
            "engine":engine, "mode":"offline_mock", "turn_index":None,
            "expected_tools":[], "actual_tools":[], "forbidden_tools":[], "assertion_results":[],
            "checks":[], "failed":[], "turn_results":[], "aggregate_tool_sequence":[],
            "tool_sequence":None, "reply":"", "error":None, "warnings":warnings}
    if errors or engine != "legacy":
        status = "invalid" if errors else "engine_limitation"
        checks = [{"name":"schema", "ok":False, "detail":error} for error in errors]
        return dict(base, status=status, final_status=status, validation_errors=errors,
                    checks=checks, assertion_results=checks, failed=errors or ["unsupported_mock_engine"],
                    latency_ms=round((time.perf_counter()-started)*1000))
    with _fresh(engine, evidence_root) as (agent, folder):
        today = config.today()
        session_id = "p2-"+str(case.get("case_id") or "case")+"-"+uuid.uuid4().hex
        result, error, checks, turns = {}, None, [], []
        for index, message in enumerate(case["turns"]):
            events, result = [], {}
            agent.last_audit_report = None
            with capture(folder/"traces/run_events.jsonl", callback=events.append) as state:
                try:
                    result = agent.chat(session_id, message)
                    finish(result, (agent.last_audit_report or {}).get("error"))
                    emit("agent_returned", reply=result.get("reply"), finish_reason=result.get("finish_reason"))
                except Exception as exc:
                    error = type(exc).__name__
                    finish(error={"type":error})
                    emit("agent_error", "failed", error=error)
            run_id = state.get("run_id")  # May be absent when chat rejects invalid input before Trace creation.
            executions = _executions(events, result, state.get("tools"))
            expected = (case.get("turn_expects") or [{}]*len(case["turns"]))[index]
            assertions = _checks(expected, case, result, executions, today,
                                 scope="turn_expects", turn_index=index, run_id=run_id) if not error else []
            turn_status = "error" if error else "failed" if any(not c["ok"] for c in assertions) else (
                "passed" if assertions else "not_evaluated")
            turns.append({"case_id":base["case_id"], "batch_id":base["batch_id"], "engine":engine,
                "session_id":session_id, "run_id":run_id, "turn_index":index, "user_message":message,
                "expected_tools":list(expected.get("must_call", [])),
                "actual_tools":[e["tool"] for e in executions if e.get("executed") is True],
                "proposed_tools":[e["tool"] for e in executions],
                "blocked_tools":[e["tool"] for e in executions if e.get("executed") is False],
                "unknown_execution_tools":[e["tool"] for e in executions if e.get("executed") is None],
                "forbidden_tools":list(expected.get("must_not_call", [])),
                "assertion_results":assertions, "final_status":turn_status,
                "executions":executions, "public_result":copy.deepcopy(result), "events":events,
                "error":error, "evidence_ref":str(folder/"traces/run_events.jsonl")})
            checks.extend(assertions)
            if error:
                break
        expect = case.get("expect") or {}
        last = turns[-1]
        last["final_expect"] = copy.deepcopy(expect)
        last["expected_tools"] = list(dict.fromkeys(last["expected_tools"] + expect.get("must_call", [])))
        last["forbidden_tools"] = list(dict.fromkeys(last["forbidden_tools"] + expect.get("must_not_call", [])))
        if "raises" in expect:
            checks.append({"name":"raises", "ok":error == expect["raises"], "detail":f"actual={error}",
                           "scope":"expect", "turn_index":last["turn_index"], "run_id":last["run_id"]})
        elif error:
            checks.append({"name":"exception", "ok":False, "detail":error, "scope":"execution",
                           "turn_index":last["turn_index"], "run_id":last["run_id"]})
        else:
            checks.extend(_checks(expect, case, result, last["executions"], today, scope="expect",
                                  turn_index=last["turn_index"], run_id=last["run_id"]))
        if "raises" in expect:
            last["assertion_results"] = checks[:]
            last["final_status"] = "passed" if checks[-1]["ok"] else "failed"
        else:
            # Include final-turn legacy assertions without replacing the indexed ones.
            last["assertion_results"] += [c for c in checks if c.get("scope") == "expect"]
            if not error and last["assertion_results"]:
                last["final_status"] = "passed" if all(c["ok"] for c in last["assertion_results"]) else "failed"
        failed = [c["name"] if c.get("scope") == "expect" else
                  f"turn[{c.get('turn_index')}].{c['name']}" for c in checks if not c["ok"]]
        status = "error" if error and "raises" not in expect else "failed" if failed else "passed"
        row = dict(base, status=status, final_status=status, run_id=last["run_id"], session_id=session_id,
            turn_index=last["turn_index"], checks=checks, assertion_results=checks, failed=failed,
            expected_tools=list(expect.get("must_call", [])), actual_tools=last["actual_tools"],
            forbidden_tools=list(expect.get("must_not_call", [])), turn_results=turns,
            aggregate_tool_sequence=[t for turn in turns for t in turn["actual_tools"]],
            latency_ms=round((time.perf_counter()-started)*1000), error=error,
            tool_sequence=result.get("tool_sequence"), reply=str(result.get("reply") or "")[:200],
            evidence_dir=str(folder), validation_errors=[])
        row = sanitize(row)
        (folder/"execution.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf8")
        return row
