
"""Current-session evidence for the C workbench. Reads never replay user actions."""
import re
from collections import Counter
from pathlib import Path

from target.diagnostics import digest, sanitize

MAX_TURNS = 12
TOOL_EVENTS = {"tool_result", "railway_tool_result", "railway_tool_error", "railway_input_required"}
BOUNDARY_EVENTS = {"business_operation_completed", "ui_order_state_rendered", "agent_order_state_declared"}
IDENTITY_FIELDS = ("event_id", "parent_event_id", "run_id", "session_id", "event_type", "timestamp",
                   "status", "tool", "call_id", "executed", "args", "output", "duration_ms",
                   "operation_status", "business_receipt", "order_id", "proposal_id", "order_status",
                   "payment_status", "operation_id", "source", "source_run_id", "retrieval_id", "documents", "hit_count",
                   "rendered_from_run_id", "render_text_sha256", "declaration_sha256")
TEXT_PRIVATE = (
    re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b"),
    re.compile(r"(?<![\w])\d{17}[\dXx](?![\w])"),
    re.compile(r"(?i)(?:api[-_ ]?key|access[-_ ]?token|password|密码|密钥)\s*[:=：]\s*[^\s，。]+"),
    re.compile(r"(?:乘车人|乘客(?:姓名)?|姓名)\s*(?:是|叫|为|[:：])\s*[^\s，。；、,;]+"),
    re.compile(r"(?<=名字叫)[^\s，。；、,;]+"),
)
PRIVATE_KEYS = {"confirmation_token", "owner_phone", "contact", "phone", "passenger_name",
                "passenger_names", "name_on_ticket", "identity_number", "id_number", "secret"}


def _passengers(value):
    if isinstance(value, list):
        for item in value:
            yield from _passengers(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"passengers", "passenger_names"} and isinstance(item, list):
                yield from (name for name in item if isinstance(name, str) and 1 < len(name) <= 50)
            elif key in {"passenger_name", "name_on_ticket"} and isinstance(item, str) and 1 < len(item) <= 50:
                yield item
            else:
                yield from _passengers(item)


def private_evidence(value):
    names = sorted(set(_passengers(value)), key=lambda name: (-len(name), name))

    def walk(item):
        if isinstance(item, dict):
            return {key: "[已脱敏]" if key.lower() in PRIVATE_KEYS else walk(data) for key, data in item.items()}
        if isinstance(item, list):
            return [walk(data) for data in item]
        if isinstance(item, str):
            for name in names:
                item = item.replace(name, "[乘车人]")
            for pattern in TEXT_PRIVATE:
                item = pattern.sub("[已脱敏]", item)
            return item
        return item

    return walk(sanitize(value))


def _event_row(event):
    return {key: event[key] for key in IDENTITY_FIELDS if key in event}


def retrieval_documents(event):
    if event.get('event_type') == 'rag_result' and isinstance(event.get('documents'), list):
        return event['documents']
    output = event.get('output')
    if (event.get('event_type') == 'tool_result' and event.get('tool') == 'search_policy'
            and event.get('executed') is True and isinstance(output, dict) and isinstance(output.get('hits'), list)):
        return output['hits']
    return None


def snapshot_conversation(session):
    from web.evidence import session_execution_events
    sid = session.sid
    if session.mode != "user":
        raise ValueError("USER_SESSION_REQUIRED")
    history = [row for row in session.history if isinstance(row, dict) and row.get("session_id") == sid]
    history = history[-MAX_TURNS:]
    if not history:
        raise ValueError("USER_CONVERSATION_REQUIRED")
    audits = [row for row in session.audits if isinstance(row, dict)
              and isinstance(row.get("public_trace"), dict) and row["public_trace"].get("session_id") == sid]
    events, read = session_execution_events(session.trace_dir, sid)
    turns = []
    for index, row in enumerate(history, 1):
        identity = digest(row)
        matches = [audit for audit in audits if audit.get("public_trace_sha256") == identity or audit["public_trace"] == row]
        # Multiple copies of one run are harmless. Distinct matching runs are ambiguous.
        run_ids = {audit["trace_id"] for audit in matches if isinstance(audit.get("trace_id"), str)}
        run_id = next(iter(run_ids)) if len(run_ids) == 1 else None
        related = [_event_row(event) for event in events if event.get("run_id") == run_id
                   and event.get("event_type") in TOOL_EVENTS | BOUNDARY_EVENTS | {"rag_result"}] if run_id else []
        # A public tool proposal/result preview remains labelled as such.
        calls = [call for step in row.get("steps", []) if isinstance(step, dict)
                 for call in step.get("calls", []) if isinstance(call, dict)]
        turns.append(dict(turn_id=f"turn-{index:03d}", run_id=run_id, user=row.get("user_msg", ""),
                          reply=row.get("reply", ""), public_tool_calls=calls, execution_events=related,
                          execution_evidence="available" if related else "missing"))
    known = {turn["run_id"] for turn in turns if turn["run_id"]}
    receipts = [r for r in getattr(session, "business_receipts", []) if isinstance(r, dict)
                and r.get("session_id") == sid and r.get("source_run_id") in known]
    operation_ids = {r["operation_id"] for r in receipts if isinstance(r.get("operation_id"), str)}
    operation_events = [_event_row(event) for event in events if event.get("event_type") in BOUNDARY_EVENTS
                        and (event.get("run_id") in operation_ids or event.get("operation_id") in operation_ids)]
    return private_evidence(dict(session_id=sid, engine=session.engine, subject_provider=(
        session.live_provider if session.live else "mock"), turns=turns, receipts=receipts,
        operation_events=operation_events, trace_read_status=read,
        omitted_prior_turns=max(0, len(session.history) - len(turns)),
        trace_file="run_events.jsonl"))

