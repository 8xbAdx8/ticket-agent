"""Explicit, filtered LangSmith REST export. Never a framework auto-tracing callback.

One POST at most, then bounded readback of that same client-supplied run ID.
Only an accepted asynchronous write followed by 404 permits delayed GET polling.
No POST retry, background batching, project provisioning or automatic audit upload.
"""
import json
import hashlib
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from target.diagnostics import sanitize, digest

UPLOAD_SCOPE = ("本轮用户输入、固定只读系统提示、最终回复、两个只读工具的白名单参数及模拟结果、"
                "模型/用量/耗时/错误类别和本地 Trace ID；不上传完整会话、认证信息、原始思维链、订单或旁证全文。")
PREFERENCES=Path(__file__).resolve().parent.parent/'artifacts/runtime/ui-preferences.json'


def set_export_enabled(enabled):
    """Project-local switch only; no key, HTTP request or automatic callback."""
    if type(enabled) is not bool:raise ValueError('boolean_export_switch_required')
    PREFERENCES.parent.mkdir(parents=True,exist_ok=True)
    temp=PREFERENCES.with_name(PREFERENCES.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps({'schema':'ticket-ui-preferences/1','langsmith_export_enabled':enabled}),encoding='utf-8')
    temp.replace(PREFERENCES)
    # Let the UI toggle take effect even when the launcher inherited an explicit flag.
    os.environ['TICKET_LANGSMITH_EXPORT_ENABLED']='true' if enabled else 'false'


def export_enabled():
    explicit=os.getenv('TICKET_LANGSMITH_EXPORT_ENABLED')
    if explicit is not None:
        if explicit.lower() not in ('true','false'):raise ValueError('invalid_export_switch')
        return explicit.lower()=='true'
    if not (os.getenv('TICKET_OFFLINE_GUARD_LOG') or os.getenv('TICKET_DISABLE_LOCAL_SECRETS')=='1' or os.getenv('TICKET_WEB_OFFLINE_ONLY')=='1') and PREFERENCES.exists():
        value=json.loads(PREFERENCES.read_text(encoding='utf-8'))['langsmith_export_enabled']
        if type(value) is not bool:raise ValueError('invalid_export_preference')
        return value
    return _setting('LANGCHAIN_TRACING_V2','LANGSMITH_TRACING','false').lower()=='true'


def _setting(old, new, default=""):
    from target.api_config import alias
    return alias(old,new,default)


def settings():
    key = _setting("LANGCHAIN_API_KEY", "LANGSMITH_API_KEY")
    endpoint = _setting("LANGCHAIN_ENDPOINT", "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    project = _setting("LANGCHAIN_PROJECT", "LANGSMITH_PROJECT", "ticket-agent-v33")
    enabled = export_enabled()
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
    except (ValueError,KeyError,OSError):
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


MAX_READ_ATTEMPTS = 3
READBACK_DELAYS = (0, 1, 2)


def _error(category, status=None):
    return {"category": category, "http_status": status}


def _http_category(status):
    return {400:"invalid_request",401:"authentication_failed",403:"permission_denied",
            404:"run_not_readable",409:"conflict",422:"invalid_parameters",
            429:"rate_limited"}.get(status, "remote_server_error" if status >= 500 else "http_error")


def _exchange(client, method, url, headers, receipt, body=None):
    """Safe per-request evidence; never saves authentication or response text."""
    receipt["http_requests"] += 1
    attempt={"attempt_id":receipt["verification_id"]+":"+str(receipt["http_requests"]),
             "method":method,"path":urlsplit(url).path,"timestamp":datetime.now(timezone.utc).isoformat()}
    receipt.setdefault("http_attempts",[]).append(attempt)
    start=time.perf_counter()
    try:
        response=client.request(method,url,headers=headers,**({"json":body} if body is not None else {}))
        attempt.update(http_status=response.status_code,response_body_sha256=hashlib.sha256(response.content).hexdigest(),
            response_correlation={k:v for k,v in response.headers.items()
                if k.lower() in ("x-request-id","x-correlation-id","x-langsmith-request-id","cf-ray")
                and re.fullmatch(r"[\w.:/-]{1,200}",v)})
        try:
            data=response.json()
            attempt["response_json_type"]=type(data).__name__
            if isinstance(data,dict):
                attempt["response_fields_present"]=[k for k in ("id","message","detail","error","status","type","title") if k in data]
        except ValueError:attempt["response_json_type"]="invalid_json"
        return response
    except Exception as exc:
        from target.deepseek_runtime import safe_error
        attempt["error"]=safe_error(exc)
        receipt["error"]=attempt["error"]
        return None
    finally:
        attempt["latency_ms"]=round((time.perf_counter()-start)*1000)


def _readback(client, endpoint, run_id, headers, payload, receipt, attempts):
    """Polling is exclusively GET after 202+404; all other failures stop immediately."""
    asynchronous=receipt.get("post_http_status")==202
    for index in range(attempts):
        if index:time.sleep(READBACK_DELAYS[index])
        response=_exchange(client,"GET",endpoint+"/runs/"+run_id,headers,receipt)
        receipt["get_http_status"]=response.status_code if response is not None else None
        if response is None:
            receipt["remote_status"]="pending_verification"
            return
        status=response.status_code
        if status==404 and (asynchronous or receipt.get("upload_outcome_unknown")):
            receipt.update(remote_status="pending_verification",error=_error("run_not_readable",404))
            if asynchronous and index+1<attempts:continue
            return
        if status!=200:
            receipt.update(remote_status="pending_verification" if status==429 or status>=500 else "failed",
                           error=_error(_http_category(status),status))
            return
        try:
            remote=response.json()
            if not isinstance(remote,dict):raise ValueError("invalid_object")
            extra=remote.get("extra") or {}
            if not isinstance(extra,dict):raise ValueError("invalid_extra")
            metadata=extra.get("metadata") or {}
            if not isinstance(metadata,dict):raise ValueError("invalid_metadata")
            expected={**payload["metadata"],"payload_sha256":digest(payload)}
            matches={"id":str(remote.get("id"))==run_id,"inputs":remote.get("inputs")==payload["inputs"],
                     "outputs":remote.get("outputs")==payload["outputs"],
                     "metadata":all(k in metadata and metadata[k]==v for k,v in expected.items())}
        except (ValueError,TypeError,KeyError):
            receipt.update(remote_status="failed",error=_error("invalid_readback_response",200))
            return
        receipt["readback_matches"]=matches
        if not all(matches.values()):
            receipt.update(remote_status="failed",error=_error("remote_readback_mismatch",200))
            return
        receipt.pop("error",None)
        receipt.update(remote_status="verified",remote_verified=True)
        return


def _headers(key):
    headers={"x-api-key":key}
    workspace=_setting("LANGCHAIN_WORKSPACE_ID","LANGSMITH_WORKSPACE_ID")
    if workspace:headers["x-tenant-id"]=workspace
    return headers,hashlib.sha256(workspace.encode()).hexdigest()


def _save(receipt,trace_dir,filename):
    receipt=sanitize(receipt)
    if trace_dir:
        try:
            path=Path(trace_dir)/filename
            path.parent.mkdir(parents=True,exist_ok=True)
            receipt["receipt_saved"]=True
            with path.open("a",encoding="utf-8") as f:f.write(json.dumps(receipt,ensure_ascii=False)+"\n")
        except OSError:receipt["receipt_saved"]=False
    return receipt


def _validate_attempts(attempts):
    if type(attempts) is not int or not 1<=attempts<=MAX_READ_ATTEMPTS:
        raise ValueError("readback_attempts_must_be_between_1_and_3")


def export_run(record, *, consent=False, trace_dir=None, transport=None, max_read_attempts=MAX_READ_ATTEMPTS):
    """Returns a separate receipt. Never edits record or the Agent's public business result."""
    receipt={"local_trace_id":record.get("trace_id"),"local_trace_saved":record.get("local_trace_saved",False),
             "local_sidecar_saved":record.get("local_sidecar_saved",False),
             "provider":record.get("provider"),
             "remote_status":"not_attempted","remote_verified":False,"http_requests":0,
             "generation_requests":0,"upload_attempts":0,"verification_id":uuid.uuid4().hex,
             "timestamp":datetime.now(timezone.utc).isoformat()}
    receipt["verification_origin"]="offline_transport_fixture" if transport is not None else "remote_http"
    try:
        _validate_attempts(max_read_attempts)
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
            headers,workspace_hash=_headers(key)
            receipt.update(remote_run_id=run_id,id_source="client_supplied",project=project,endpoint=endpoint,
                           payload_sha256=digest(payload),workspace_sha256=workspace_hash)
            if trace_dir:
                frozen=Path(trace_dir)/"langsmith_payloads"/(run_id+".json")
                frozen.parent.mkdir(parents=True,exist_ok=True)
                with frozen.open("x",encoding="utf-8") as f:json.dump(payload,f,ensure_ascii=False)
                receipt["payload_file"]="langsmith_payloads/"+run_id+".json"
            end=datetime.now(timezone.utc)
            start=end-timedelta(milliseconds=record.get("total_latency_ms") or 0)
            body={"id":run_id,"name":"Ticket Agent synthetic observability check" if record.get("mode")=="synthetic" else "Ticket Agent filtered Live run","run_type":"chain",
                "session_name":project,"start_time":start.isoformat(),"end_time":end.isoformat(),
                "inputs":payload["inputs"],"outputs":payload["outputs"],
                "extra":{"metadata":{**payload["metadata"],"payload_sha256":digest(payload)}}}
            # No SDK/global tracing: prevent implicit /info probes, callbacks, retry or batching.
            with httpx.Client(timeout=5,follow_redirects=False,transport=transport) as client:
                receipt["upload_attempts"]=1
                response=_exchange(client,"POST",endpoint+"/runs",headers,receipt,body)
                if response is None:
                    receipt["remote_status"]="upload_outcome_unknown"
                else:
                    receipt["post_http_status"]=response.status_code
                    if response.status_code not in (200,201,202):
                        receipt.update(remote_status="failed",error=_error(_http_category(response.status_code),response.status_code))
                    else:
                        receipt["remote_status"]="accepted_unverified"
                        # The Run ID is supplied in the request. 202 acknowledgement has
                        # no guaranteed server-generated ID; never adopt an unrelated one.
                        try:ack=response.json()
                        except ValueError:ack=None
                        ack_id=ack.get("id") if isinstance(ack,dict) else None
                        receipt["post_response_id_present"]=ack_id is not None
                        if ack_id is not None and str(ack_id)!=run_id:
                            receipt.update(remote_status="failed",error=_error("post_response_id_mismatch",response.status_code))
                        else:
                            _readback(client,endpoint,run_id,headers,payload,receipt,
                                      max_read_attempts if response.status_code==202 else 1)
    except Exception as exc:
        from target.deepseek_runtime import safe_error
        receipt.update(remote_status="failed",error=_error(str(exc)) if type(exc) is ValueError and str(exc) in (
            "filtered_export_too_large","readback_attempts_must_be_between_1_and_3") else safe_error(exc))
    return _save(receipt,trace_dir,"langsmith_exports.jsonl")


def verify_existing(receipt,payload,*,consent=False,transport=None,max_read_attempts=1,trace_dir=None):
    """Read an existing ID, one GET by default. Explicit UI polling allows at most 3."""
    result={"action":"readback_only","remote_verified":False,"remote_status":"not_attempted",
        "http_requests":0,"upload_attempts":0,"generation_requests":0,"timestamp":datetime.now(timezone.utc).isoformat(),
        "verification_id":uuid.uuid4().hex,"remote_run_id":receipt.get("remote_run_id"),"local_trace_id":receipt.get("local_trace_id"),
        "verification_origin":"offline_transport_fixture" if transport is not None else "remote_http"}
    if not consent:return {**result,"remote_status":"consent_required"}
    try:
        _validate_attempts(max_read_attempts)
        key,endpoint,project,_=settings()
        if not key:return {**result,"remote_status":"not_configured"}
        if endpoint!=receipt.get("endpoint") or project!=receipt.get("project") or digest(payload)!=receipt.get("payload_sha256"):
            raise ValueError("original_receipt_and_preview_required")
        run_id=str(uuid.UUID(receipt["remote_run_id"]))
        accepted=receipt.get("post_http_status") in (200,201,202)
        if not accepted and receipt.get("remote_status")!="upload_outcome_unknown":raise ValueError("accepted_run_required")
        import httpx
        headers,workspace_hash=_headers(key)
        if receipt.get("workspace_sha256") and receipt["workspace_sha256"]!=workspace_hash:
            raise ValueError("original_workspace_required")
        result.update(post_http_status=receipt.get("post_http_status"),payload_sha256=digest(payload),
                      project=project,endpoint=endpoint,workspace_sha256=workspace_hash)
        if not accepted:result["upload_outcome_unknown"]=True
        if receipt.get("payload_file"):result["payload_file"]=receipt["payload_file"]
        with httpx.Client(timeout=5,follow_redirects=False,transport=transport) as client:
            _readback(client,endpoint,run_id,headers,payload,result,max_read_attempts if accepted else 1)
    except Exception as exc:
        from target.deepseek_runtime import safe_error
        category=str(exc) if type(exc) is ValueError and str(exc) in (
            "original_receipt_and_preview_required","accepted_run_required","original_workspace_required",
            "readback_attempts_must_be_between_1_and_3") else None
        result.update(remote_status="failed",error=_error(category) if category else safe_error(exc))
    return _save(result,trace_dir,"langsmith_readbacks.jsonl")
