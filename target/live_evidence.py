"""Versioned Live metadata sidecar; public ten/five-field contract stays unchanged."""
import json
import os
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
import config
from target.diagnostics import sanitize, digest


@lru_cache(maxsize=1)
def source_sha():
    try:
        return subprocess.run(["git","rev-parse","HEAD"],cwd=config.BASE_DIR,capture_output=True,
                              text=True,check=True,timeout=3).stdout.strip()
    except (OSError,subprocess.SubprocessError):
        return None


def record_run(trace, events, *, error=None, public_trace=None, save=True, local_trace_saved=False):
    responses=[e for e in events if e.get("event")=="model_response"]
    complete=bool(responses) and all(all(type(e.get("usage",{}).get(k)) is int and e["usage"][k]>=0
                                   for k in ("input_tokens","output_tokens")) for e in responses)
    tools=[e for e in events if e.get("event")=="tool_end"]
    record=sanitize({"schema":"ticket-live-run/1","trace_id":trace.trace_id,"session_id":trace.session_id,
        "provider":trace.provider,"requested_model":trace.model,
        "actual_models":list(dict.fromkeys(e["response_model"] for e in responses if e.get("response_model"))),
        "mode":"live","case_id":os.getenv("TICKET_CASE_ID"),"git_sha":source_sha(),
        "requested_at":getattr(trace,"requested_at",None),
        "recorded_at":datetime.now(timezone.utc).isoformat(),"user_msg":trace.user_msg,
        "reply":trace.reply if not error else None,"finish_reason":trace.finish_reason,
        "total_latency_ms":trace.total_latency_ms,"tokens":trace.tokens if complete and not error else None,
        "observed_tokens":trace.tokens if responses else None,"token_usage_status":"complete" if complete and not error else "partial" if responses else "unknown",
        "agent_completed":error is None and trace.finish_reason=="stop",
        "model_response_received":bool(responses),"tool_execution_success":all(e.get("ok") and e.get("executed") is True for e in tools) if tools else None,
        "business_success":None,"error":error,"local_trace_saved":local_trace_saved,
        "local_sidecar_saved":save,
        "public_trace":public_trace,"public_trace_sha256":digest(public_trace) if public_trace else None,
        "events":events,"remote_status":"not_attempted"})
    if save:
        path=config.TRACE_DIR/"provider_runs.jsonl"
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("a",encoding="utf-8") as f: f.write(json.dumps(record,ensure_ascii=False)+"\n")
    return record
