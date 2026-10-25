"""Explicit, filtered LangSmith REST export. Never a framework auto-tracing callback.

Two synchronous HTTP operations per attempt: create one completed run, read it back.
No background batching, retry, project auto-provisioning, or automatic full-audit upload.
"""
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from target.diagnostics import sanitize, digest

UPLOAD_SCOPE = ("本轮用户输入、固定只读系统提示、最终回复、两个只读工具的白名单参数及模拟结果、"
                "模型/用量/耗时/错误类别和本地 Trace ID；不上传完整会话、认证信息、原始思维链、订单或旁证全文。")


def _setting(old, new, default=""):
    left, right = os.getenv(old, "").strip(), os.getenv(new, "").strip()
    if left and right and left != right:
        raise ValueError("conflicting_langsmith_configuration")
    return left or right or default


def settings():
    key = _setting("LANGCHAIN_API_KEY", "LANGSMITH_API_KEY")
    endpoint = _setting("LANGCHAIN_ENDPOINT", "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    project = _setting("LANGCHAIN_PROJECT", "LANGSMITH_PROJECT", "ticket-agent-v33")
    enabled = _setting("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "false").lower() == "true"
    address = urlsplit(endpoint)
    if (address.scheme != "https" or not address.hostname or address.username or address.password
            or address.query or address.fragment or address.path not in ("", "/")):
        raise ValueError("invalid_langsmith_endpoint")
    return key, endpoint.rstrip("/"), project, enabled


def configuration_status():
    try:
        key, endpoint, project, enabled = settings()
        return {"state":"not_configured" if not key else "user_disabled" if not enabled else "configured_unverified",
                "key_configured":bool(key), "enabled":enabled, "endpoint":endpoint, "project":project,
                "scope":UPLOAD_SCOPE,"automatic_framework_export":False}
    except ValueError:
        return {"state":"configuration_error","enabled":False,"key_configured":False,"automatic_framework_export":False}


def export_payload(record):
    """Explicit field allowlist; unknown event fields never escape into the upload."""
    from target.deepseek_runtime import READ_ONLY_PROMPT
    selections=[]
    executions=[]
    allowed_args={"from_city","to_city","date","kind","seat_type","question"}
    def clean_result(result):
        if not isinstance(result,dict): return None
        out={k:result[k] for k in ("count","citation_status") if k in result}
        for group,fields in (("trains",{"train_no","from_city","to_city","date","depart","arrive","kind","seat_type","price","seats_left"}),
                             ("hits",{"doc_id","title","content","text","score","source"})):
            if isinstance(result.get(group),list):
                out[group]=[{k:v for k,v in row.items() if k in fields} for row in result[group][:20] if isinstance(row,dict)]
        return out
    for event in record.get("events",[]):
        if event.get("event")=="model_response":
            selections.append({"model":event.get("response_model"),"usage":event.get("usage"),
                               "finish_reason":event.get("finish_reason"),"latency_ms":event.get("latency_ms"),
                               "tool_calls":[{"name":c.get("name"),"id":c.get("id"),
                                   "args":{k:v for k,v in c.get("args",{}).items() if k in allowed_args}}
                                   for c in event.get("tool_calls",[]) if c.get("name") in ("query_tickets","search_policy")]})
        if event.get("event")=="tool_end" and event.get("tool") in ("query_tickets","search_policy"):
            result=event.get("result")
            executions.append({"tool":event["tool"],"args":{k:v for k,v in event.get("args",{}).items() if k in allowed_args},
                "ok":event.get("ok"),"executed":event.get("executed"),"latency_ms":event.get("latency_ms"),
                "result":clean_result(result)})
    safe=sanitize({"inputs":{"user_message":record.get("user_msg"),"system_prompt":READ_ONLY_PROMPT},
        "outputs":{"reply":record.get("reply"),"models":selections,"tools":executions,
                   "finish_reason":record.get("finish_reason"),"tokens":record.get("tokens"),"error":record.get("error")},
        "metadata":{k:record.get(k) for k in ("trace_id","provider","requested_model","actual_models","mode","case_id","git_sha","public_trace_sha256","total_latency_ms")}})
    def scrub(value):
        if isinstance(value,dict): return {k:scrub(v) for k,v in value.items()}
        if isinstance(value,list): return [scrub(v) for v in value]
        if isinstance(value,str):
            value=re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}","<email-redacted>",value)
            return re.sub(r"(?<![A-Za-z0-9])\d{17}[\dXx](?![A-Za-z0-9])","<identity-redacted>",value)
        return value
    return scrub(safe)


def export_run(record, *, consent=False, trace_dir=None, transport=None):
    """Returns a separate receipt. Never edits record or the Agent's public business result."""
    receipt={"local_trace_id":record.get("trace_id"),"local_trace_saved":record.get("local_trace_saved",False),
             "local_sidecar_saved":record.get("local_sidecar_saved",False),
             "provider":record.get("provider"),
             "remote_status":"not_attempted","remote_verified":False,"http_requests":0,
             "generation_requests":0,"timestamp":datetime.now(timezone.utc).isoformat()}
    receipt["verification_origin"]="offline_transport_fixture" if transport is not None else "remote_http"
    try:
        key, endpoint, project, enabled=settings()
        if not enabled:
            receipt["remote_status"]="user_disabled"
        elif not consent:
            receipt["remote_status"]="consent_required"
        elif not key:
            receipt["remote_status"]="not_configured"
        elif not (record.get("local_trace_saved") or record.get("local_sidecar_saved")):
            receipt["remote_status"]="local_trace_required"
        else:
            payload=export_payload(record)
            if len(json.dumps(payload,ensure_ascii=False).encode())>64000:
                raise ValueError("filtered_export_too_large")
            import httpx
            run_id=str(uuid.uuid4())
            receipt.update(remote_run_id=run_id,project=project,endpoint=endpoint,payload_sha256=digest(payload))
            end=datetime.now(timezone.utc)
            start=end-timedelta(milliseconds=record.get("total_latency_ms") or 0)
            body={"id":run_id,"name":"Ticket Agent filtered Live run","run_type":"chain",
                "session_name":project,"start_time":start.isoformat(),"end_time":end.isoformat(),
                "inputs":payload["inputs"],"outputs":payload["outputs"],
                "extra":{"metadata":{**payload["metadata"],"payload_sha256":digest(payload)}}}
            # No SDK/global tracing: prevent implicit /info probes, callbacks, retry or batching.
            with httpx.Client(timeout=5,follow_redirects=False,transport=transport) as client:
                headers={"x-api-key":key}
                workspace=_setting("LANGCHAIN_WORKSPACE_ID","LANGSMITH_WORKSPACE_ID")
                if workspace: headers["x-tenant-id"]=workspace
                receipt["http_requests"]+=1
                response=client.post(endpoint+"/runs",headers=headers,json=body)
                receipt["post_http_status"]=response.status_code
                response.raise_for_status()
                receipt["remote_status"]="accepted_unverified"
                receipt["http_requests"]+=1
                response=client.get(endpoint+"/runs/"+run_id,headers=headers)
                receipt["get_http_status"]=response.status_code
                response.raise_for_status()
                remote=response.json()
                if (str(remote.get("id"))!=run_id or remote.get("inputs")!=body["inputs"]
                        or remote.get("outputs")!=body["outputs"]
                        or (remote.get("extra") or {}).get("metadata",{}).get("payload_sha256")!=digest(payload)):
                    raise ValueError("remote_readback_mismatch")
                receipt.update(remote_status="verified",remote_verified=True)
    except Exception as exc:
        from target.deepseek_runtime import safe_error
        receipt.update(remote_status="failed",error=safe_error(exc))
    receipt=sanitize(receipt)
    if trace_dir:
        try:
            path=Path(trace_dir)/"langsmith_exports.jsonl"
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("a",encoding="utf-8") as f: f.write(json.dumps(receipt,ensure_ascii=False)+"\n")
        except OSError:
            receipt["receipt_saved"]=False
    return receipt
