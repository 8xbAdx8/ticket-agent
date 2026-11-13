
"""Compare structured, identity-bound observations without inferring a transaction from prose."""
from collections import Counter

LAYERS = ("Agent", "Business", "Runtime", "UI")
STATES = {"PENDING_PAYMENT", "PAID", "PAYMENT_FAILED", "EXPIRED", "CHANGED", "CANCELLED"}
IDENTITY = ("session_id", "operation_id", "order_id", "proposal_id")


def _identity(row):
    return tuple(row.get(key) for key in IDENTITY)


def audit_operation(identity, observations):
    """Only compare order states captured for this exact operation."""
    key = _identity(identity)
    evidence = {layer: [] for layer in LAYERS}
    if all(isinstance(value, str) and value for value in key):
        for row in observations:
            if (_identity(row) == key and row.get("layer") in evidence
                    and row.get("order_status") in STATES and row.get("evidence_ref")):
                evidence[row["layer"]].append({"status": row["order_status"], "ref": row["evidence_ref"]})
    states = {item["status"] for rows in evidence.values() for item in rows}
    missing = [layer for layer, rows in evidence.items() if not rows]
    verdict = "failed" if len(states) > 1 else "indeterminate" if missing else "passed"
    return dict(identity=identity, status=verdict, missing_layers=missing, layers=evidence)


def audit_conversation(snapshot):
    """Use trusted read-back receipts and explicit Agent/UI observations if available."""
    sid = snapshot["session_id"]
    events = snapshot["operation_events"]
    source_runs = {turn["run_id"] for turn in snapshot["turns"] if turn.get("run_id")}
    counts = Counter(event.get("event_id") for event in events)
    results = []
    for index, receipt in enumerate(snapshot["receipts"]):
        identity = {key: receipt.get(key) for key in IDENTITY}
        if identity["session_id"] != sid or receipt.get("source_run_id") not in source_runs:
            continue
        op_id = identity["operation_id"]
        observations = []
        after = receipt.get("after")
        if (receipt.get("database_verified") is True and isinstance(after, dict)
                and after.get("order_id") == identity["order_id"]):
            observations.append(dict(identity, layer="Business", order_status=after.get("order_status"),
                                     evidence_ref=f"conversation.json#/receipts/{index}/after"))
        for i, event in enumerate(events):
            event_id = event.get("event_id")
            if (not isinstance(event_id, str) or not event_id or counts[event_id] != 1
                    or event.get("session_id") != sid):
                continue
            kind = event.get("event_type")
            stored = event.get("business_receipt")
            if (kind == "business_operation_completed" and event.get("run_id") == op_id
                    and isinstance(stored, dict) and _identity(stored) == _identity(identity)
                    and stored.get("source_run_id") == receipt.get("source_run_id")):
                actual = stored.get("actual_result")
                if isinstance(actual, dict) and actual.get("order_id") == identity["order_id"]:
                    observations.append(dict(identity, layer="Runtime", order_status=actual.get("status"),
                                             evidence_ref=f"conversation.json#/operation_events/{i}/business_receipt/actual_result"))
            layer = {"agent_order_state_declared": "Agent", "ui_order_state_rendered": "UI"}.get(kind)
            agent_run_ok = (layer == "Agent" and event.get("run_id") in source_runs
                            and event.get("source") == "agent_returned_reply")
            ui_run_ok = (layer == "UI" and event.get("run_id") == op_id
                         and event.get("rendered_from_run_id") in source_runs
                         and event.get("source") == "streamlit_info_widget")
            finished, timestamp = receipt.get("finished_at"), event.get("timestamp")
            if ((agent_run_ok or ui_run_ok) and _identity(event) == _identity(identity)
                    and event.get("source_run_id") == receipt.get("source_run_id")
                    and isinstance(finished, str) and isinstance(timestamp, str) and timestamp >= finished):
                observations.append(dict(identity, layer=layer, order_status=event.get("order_status"),
                                         evidence_ref=f"conversation.json#/operation_events/{i}"))
        results.append(audit_operation(identity, observations))
    return results

