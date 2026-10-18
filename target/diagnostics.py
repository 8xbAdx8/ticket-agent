"""V3.2版本化旁证和确定性断言；不更改公开Trace十字段。"""
import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

IDS = {name:"M"+str(i+1) for i,name in enumerate(("date_offset","skip_lock","repeat_call","infinite_loop",
       "route_error","no_citation","hallucinated_train","concurrent_duplicate_order"))}
SAVE_LOCK = threading.RLock()


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()


def redact_credentials(value):
    """公开契约只隐藏凭据，不改正常业务参数或个人字段的原语义。"""
    import config
    secrets={v for k,v in os.environ.items() if k.endswith(("_API_KEY","_ACCESS_TOKEN")) and v}
    if config.API_KEY: secrets.add(config.API_KEY)
    def walk(obj):
        if isinstance(obj,dict):
            return {str(k):("<redacted>" if str(k).lower() in {
                "authorization","api_key","access_token","refresh_token","cookie","set-cookie"} else walk(v))
                for k,v in obj.items() if str(k).lower() not in {"reasoning_content","chain_of_thought"}}
        if isinstance(obj,(list,tuple)):return [walk(v) for v in obj]
        if isinstance(obj,str):
            for secret in sorted(secrets,key=len,reverse=True):obj=obj.replace(secret,"<redacted>")
            obj=re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+","Bearer <redacted>",obj)
            obj=re.sub(r'''(?i)(["']?(?:authorization|api_key|access_token|refresh_token)["']?\s*[:=]\s*)["'][^"'\r\n]*["']''',r'\1"<redacted>"',obj)
        return obj
    return walk(value)


def sanitize(value):
    """仅用于旁证。保留结构，隐藏认证/个人字段；不修改真实工具执行参数。"""
    import config
    secrets={v for k,v in os.environ.items() if k.endswith(("_API_KEY","_ACCESS_TOKEN")) and v}
    if config.API_KEY: secrets.add(config.API_KEY)
    def text(s):
        for secret in sorted(secrets,key=len,reverse=True): s=s.replace(secret,"<redacted>")
        s=re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+","Bearer <redacted>",s)
        s=re.sub(r"(?<!\d)1\d{10}(?!\d)","<phone-redacted>",s)
        return s
    def walk(obj,depth=0):
        if depth>40:return {"omitted":"maximum audit depth"}
        if isinstance(obj,dict):
            return {str(k):("<redacted>" if str(k).lower() in {"authorization","api_key","access_token","refresh_token","cookie","set-cookie","id_card"}
                    else [p if isinstance(p,str) and p.startswith("person#") else "person#"+hashlib.sha256(str(p).encode()).hexdigest()[:12] for p in v] if str(k) in {"passengers","passenger_ids"} and isinstance(v,list)
                    else walk(v,depth+1)) for k,v in obj.items() if str(k).lower() not in {"reasoning_content","chain_of_thought"}}
        if isinstance(obj,(list,tuple)):return [walk(v,depth+1) for v in obj]
        if isinstance(obj,str):return text(obj)
        if obj is None or isinstance(obj,(bool,int,float)):return obj
        return text(str(obj))
    return walk(redact_credentials(value))


def authority_snapshot(path):
    """只读获取权威车次及业务不变量；不执行过期回收或写事务。"""
    try:
        uri=Path(path).resolve().as_uri()+"?mode=ro"
        with closing(sqlite3.connect(uri,uri=True,timeout=5)) as conn:
            conn.row_factory=sqlite3.Row
            trains=[r[0] for r in conn.execute("SELECT DISTINCT train_no FROM inventory ORDER BY train_no")]
            orders=[dict(r) for r in conn.execute("SELECT order_id,lock_id,status FROM orders ORDER BY order_id")]
            locks=[dict(r) for r in conn.execute("SELECT lock_id,used,expire_at FROM locks ORDER BY lock_id")]
        return {"available":True,"trains":trains,"orders":orders,"locks":locks,"source":"isolated SQLite read-only snapshot"}
    except (sqlite3.Error,OSError):
        return {"available":False,"trains":[],"orders":[],"locks":[],"reason":"authority unavailable"}


def detect_hallucinated_trains(reply, authoritative_trains, *, user_message="", valid_query_trains=()):
    """有限的陈述分类规则。引语/否定不算主动声称，含糊情况单列。"""
    known=set(authoritative_trains or ())|set(valid_query_trains)
    findings=[]
    for clause in re.split(r"[。！？!?；;\n]|但是|不过|但",reply or ""):
        for match in re.finditer(r"(?<![A-Za-z0-9])([GDCZTK]\d{1,5})(?!\d)",clause):
            train=match[1]
            context=clause[max(0,match.start()-35):match.end()+45]
            if re.search(r"不存在|未找到|查无|无此|不能确认|无法确认|并不存在|不是实际|没有依据|并未查到",context):
                kind="negated"
            elif re.search(r"(?:用户|你|您)(?:输入|提到|说|写|提供|所说)|引用|原话",context):
                kind="user_quote"
            elif re.search(r"假设|如果|例如|比如|示例",context):
                kind="indeterminate"
            elif re.search(r"查到|找到|有余票|有票|票价|可售|已预订|推荐|发车|出发|到达|车次是|车次为|余票",context) or "|" in clause:
                kind="supported_claim" if train in known else "unsupported_claim" if authoritative_trains is not None else "indeterminate"
            else:
                kind="indeterminate" if train not in known else "mentioned_supported"
            findings.append({"train":train,"classification":kind,"fragment":context,
                             "in_authority":train in known,"mentioned_by_user":train in user_message,
                             "basis":"compare explicit assertion with authoritative trains and original valid query results"})
    bad=[r for r in findings if r["classification"]=="unsupported_claim"]
    uncertain=[r for r in findings if r["classification"]=="indeterminate"]
    return {"status":"detected" if bad else "indeterminate" if uncertain else "clear",
            "hallucination_detected":True if bad else None if uncertain else False,"findings":findings,
            "limits":"finite statement rules; no general semantic accuracy claim"}


def assertion(name, passed, reason, refs=()):
    return {"assertion":name,"result":"indeterminate" if passed is None else "pass" if passed else "fail",
            "passed":passed,"failure_reason":None if passed is True else reason,"evidence_refs":list(refs)}


def mutation_events(report, trace_id):
    raw=(report or {}).get("injection_events",[])
    enabled=(report or {}).get("mutations",{})
    result=[]
    for index,event in enumerate(raw):
        name=event["mutation"]
        status={"failed":"error","prepared":"error"}.get(event["status"],event["status"])
        result.append({"mutation_id":IDS[name],"event_id":event.get("event_id",uuid.uuid4().hex),"mutation_name":name,
            "enabled":True,"applicable":False if status=="not_applicable" else None if status=="not_triggered" else True,
            "status":status,"injection_stage":event["stage"],"target":event.get("target") or {
                "date_offset":"query_tickets.date","route_error":"tool.name","skip_lock":"lock_seat/create_order",
                "repeat_call":"backend execution count","infinite_loop":"monitor_seat loop",
                "no_citation":"search_policy.hits.doc_id","hallucinated_train":"query_tickets.trains",
                "concurrent_duplicate_order":"isolated orders.lock_id uniqueness"}[name],
            "before":event.get("original"),"after":event.get("mutated"),"reason":event.get("reason"),
            "related_step":event.get("related_step") or next((e.get("step") for e in (report or {}).get("executions",[]) if e.get("call_id")==event.get("call_id") and event.get("call_id")),None),
            "related_tool_call_id":event.get("call_id"),
            "timestamp":event.get("timestamp") or datetime.now(timezone.utc).isoformat(),"evidence_ref":f"audit:{trace_id}#/fault_report/injection_events/{index}"})
    for name in IDS:
        if name not in enabled:
            result.append({"mutation_id":IDS[name],"event_id":uuid.uuid4().hex,"mutation_name":name,"enabled":False,
                "applicable":None,"status":"disabled","injection_stage":None,"target":None,"before":None,"after":None,
                "reason":"explicitly disabled","related_step":None,"related_tool_call_id":None,
                "timestamp":datetime.now(timezone.utc).isoformat(),"evidence_ref":f"audit:{trace_id}"})
    return result


def evaluate(public_trace, report, authority, *, error=None, raw_model_reply=None):
    """规则证据与质量维度分开。不从模型一句自我声明推断识别或恢复。"""
    report=report or {}; executions=report.get("executions",[]); model=report.get("model_requests",[])
    enabled=report.get("mutations",{}); checks=[]
    calls=[call for m in model for call in m.get("tool_calls",[])]
    actual=[e for e in executions if e.get("executed",True)]
    original_trains={t["train_no"] for e in executions if isinstance(e.get("original_result"),dict)
                     for t in e["original_result"].get("trains",[]) if isinstance(t,dict) and "train_no" in t}
    hall=detect_hallucinated_trains(public_trace.get("reply",""),authority["trains"] if authority.get("available") else None,
                                 user_message=public_trace.get("user_msg",""),valid_query_trains=original_trains)
    checks.append(assertion("reply_train_authority",not hall["hallucination_detected"] if hall["hallucination_detected"] is not None else None,
                            "reply asserts unsupported or ambiguous trains",["authority","hallucination"]))
    expected_date=None
    if re.search(r"今天|明天|后天|星期|周|\d{4}-\d{2}-\d{2}|\d+月\d+",public_trace.get("user_msg","")):
        try:
            from target.providers import _parse_date
            expected_date=_parse_date(public_trace["user_msg"],{})
        except (ValueError,TypeError):pass
    model_dates=[c["args"].get("date") for c in calls if c["name"]=="query_tickets"]
    query_runs=[e for e in actual if e.get("tool")=="query_tickets" and e.get("ok")]
    actual_dates=[e.get("args",{}).get("date") for e in query_runs]
    if expected_date and model_dates:
        legacy=all(m.get("source")=="legacy_provider" for m in model)
        checks.append(assertion("model_original_date_matches_user",None if legacy else model_dates[0]==expected_date,
            "Legacy脚本参数已经过Provider变异，不能冒充独立的原模型参数" if legacy else "model argument error before execution",["model_requests","user_conditions"]))
    if expected_date and actual_dates:
        checks.append(assertion("executed_query_date_matches_user",actual_dates[-1]==expected_date,"actual query date differs from user requirement",["executions","user_conditions"]))
    routed=[e for e in actual if any(c.get("id")==e.get("call_id") and c["name"]=="search_policy" for c in calls)]
    if routed:
        checks.append(assertion("policy_intent_preserves_tool_route",all(e["tool"]=="search_policy" for e in routed),"policy request executed a different tool",["model_requests","executions"]))
    grouped={}
    for e in actual:grouped.setdefault((e.get("call_id"),e.get("tool")),[]).append(e)
    duplicate=[{"call_id":key[0],"tool":key[1],"count":len(items)} for key,items in grouped.items() if key[0] and len(items)>1]
    if calls:
        checks.append(assertion("no_extra_execution_per_model_call",not duplicate,"one model request caused repeated backend execution",["model_requests","executions"]))
    loop_runs=[e for e in actual if e.get("tool")=="monitor_seat"]
    if enabled.get("infinite_loop") and len(loop_runs)>1:
        checks.append(assertion("no_forced_monitor_loop",False,"injected monitor repetitions observed; inspect finite stop reason",["executions"]))
    uncited=[e for e in actual if e["tool"]=="search_policy" and isinstance(e.get("result"),dict) and e["result"].get("hits")
             and any(not h.get("doc_id") for h in e["result"]["hits"])]
    if uncited:checks.append(assertion("retrieved_policy_has_citations",False,"model-visible policy result has missing citation",["executions"]))
    unbacked=[t for e in actual if e["tool"]=="query_tickets" and isinstance(e.get("result"),dict)
              for t in e["result"].get("trains",[]) if authority.get("available") and t.get("train_no") not in authority["trains"]]
    if query_runs:checks.append(assertion("query_result_train_authority",not unbacked,"tool-visible trains not in authoritative database",["authority","executions"]))
    failed_order=[e for e in actual if e["tool"]=="create_order" and not e.get("ok")]
    for e in actual:
        if e["tool"]=="create_order":
            prior=[p for p in actual[:actual.index(e)] if p["tool"]=="lock_seat" and p.get("ok") and p.get("result",{}).get("lock_id")==e.get("args",{}).get("lock_id")]
            checks.append(assertion("create_order_requires_successful_lock",bool(prior),"actual order attempt lacks successful lock",["executions"]))
    counts={}
    for row in authority.get("orders",[]):counts[row["lock_id"]]=counts.get(row["lock_id"],0)+1
    if authority.get("available"):
        checks.append(assertion("one_order_per_lock",all(n<=1 for n in counts.values()),"duplicate independent orders for one lock",["authority/orders"]))
    defect=any(c["passed"] is False for c in checks)
    corrected=bool(expected_date and len(actual_dates)>1 and actual_dates[0]!=expected_date and actual_dates[-1]==expected_date)
    safe_stop=bool(public_trace.get("finish_reason")=="max_steps_exceeded" or error and error.get("category") in {
        "request_budget_exhausted","tool_call_limit_exceeded","unavailable_policy_citation"} or failed_order and not authority.get("orders"))
    backend_errors=any(not e.get("ok") for e in executions)
    business=None
    if actual and authority.get("available"):
        business=(not error and public_trace.get("finish_reason")=="stop" and not backend_errors and not unbacked and not uncited
                  and all(e["tool"]=="search_policy" for e in routed) and all(n<=1 for n in counts.values())
                  and hall["hallucination_detected"] is False and (not expected_date or not actual_dates or actual_dates[-1]==expected_date))
        if any(e["tool"]=="create_order" for e in actual):business=business and bool(authority["orders"])
    applied=[e for e in report.get("injection_events",[]) if e["status"]=="applied"]
    return {"case_id":public_trace.get("session_id"),"expected_behavior":"parameters, source truth, routing and order invariants hold",
        "actual_behavior":{"user_requested_date":expected_date,"model_original_dates":model_dates,"actual_query_dates":actual_dates,
                           "model_tool_requests":len(calls),"python_executions":len(actual),
                           "unknown_execution_attempts":sum(e.get("executed") is None for e in executions),"duplicate_executions":duplicate,
                           "monitor_executions":len(loop_runs),"finish_reason":public_trace.get("finish_reason")},
        "assertions":checks,"hallucination":hall,
        "dimensions":{"injection_applied":bool(applied) if any(e["status"]!="not_applicable" for e in report.get("injection_events",[])) else None,
                      "platform_defect_detected":defect if actual or hall["findings"] else None,
                      "agent_anomaly_recognized":True if corrected else None,
                      "agent_recovered":True if corrected and business else None,
                      "safe_stop":safe_stop,"business_correct":business},
        "quality_verdict":"fail" if error or defect or backend_errors else "indeterminate" if any(c["passed"] is None for c in checks) or not actual else "pass",
        "failure_reasons":[c["failure_reason"] for c in checks if c["passed"] is False],
        "scope":"deterministic tool/database/explicit-claim assertions; unknown semantic recognition/recovery remains null"}


def make_audit(trace, fault_run, *, events=(), error=None, save=True, public_trace=None):
    import config
    report=fault_run.report(finish_reason=trace.finish_reason,error=error)
    public_trace=public_trace or trace.to_dict()
    authority=authority_snapshot(config.DB_PATH)
    raw=next((m.get("final_text") for m in reversed(report["model_requests"]) if m.get("final_text") is not None),None)
    audit={"schema_version":"ticket-agent-audit/3.2","trace_id":trace.trace_id,
           "timestamp":datetime.now(timezone.utc).isoformat(),"provider":trace.provider,"model":trace.model,
           "public_trace":public_trace,"public_trace_sha256":digest(public_trace),"contract_returned":error is None,
           "fault_report":report,"mutation_events":mutation_events(report,trace.trace_id),
           "framework_events":list(events),"authority":authority,"raw_model_reply":raw,"error":error,
           "token_usage_evidence":{"status":"unknown_or_partial" if error else "reported",
                                   "reported":None if error and error.get("category")=="token_usage_unknown" else trace.tokens,
                                   "note":"Mock/SDK桩数值不是实际API用量；失败轮不得据此计算完整费用"},
           "judgement":evaluate(public_trace,report,authority,error=error,raw_model_reply=raw)}
    audit["judgement"]["case_id"]=trace.trace_id
    locations={"model_requests":"fault_report/model_requests","executions":"fault_report/executions","user_conditions":"judgement/actual_behavior/user_requested_date",
               "hallucination":"judgement/hallucination","authority":"authority","authority/orders":"authority/orders"}
    for check in audit["judgement"]["assertions"]:
        check["evidence_refs"]=[f"audit:{trace.trace_id}#/"+locations.get(ref,ref) for ref in check["evidence_refs"]]
    audit["public_trace_hash_scope"]="original public contract before sidecar personal-data masking"
    audit=sanitize(audit)
    if save:save_audit(audit)
    return audit


def save_audit(audit, directory=None):
    import config
    directory=Path(directory or config.TRACE_DIR)
    directory.mkdir(parents=True,exist_ok=True)
    audit=sanitize(audit)
    # Full sanitized evidence remains separately addressable even for large results.
    full=json.dumps(audit,ensure_ascii=False,sort_keys=True,default=str).encode()
    if len(full)>32768:
        key=hashlib.sha256(full).hexdigest()
        blob=directory/"audit_blobs"/(key+".json")
        blob.parent.mkdir(exist_ok=True)
        if len(full)<=4*1024*1024:
            blob.write_bytes(full)
            stored={k:v for k,v in audit.items() if k not in ("framework_events","fault_report","authority")}
            stored["full_evidence"]={"path":"audit_blobs/"+key+".json","sha256":key,"bytes":len(full),"available":True}
        else:
            stored={"schema_version":audit["schema_version"],"trace_id":audit["trace_id"],"timestamp":audit["timestamp"],
                    "full_evidence":{"available":False,"bytes":len(full),"sha256":key,"reason":"audit exceeds 4MiB bound"},
                    "judgement":{"quality_verdict":"indeterminate","failure_reasons":["evidence too large"]}}
    else:stored=audit
    with SAVE_LOCK, (directory/"audit_runs.jsonl").open("a",encoding="utf-8") as out:
        out.write(json.dumps(stored,ensure_ascii=False,default=str)+"\n")
    return directory/"audit_runs.jsonl"


def read_audits(directory):
    directory=Path(directory);path=directory/"audit_runs.jsonl"
    if not path.exists():return []
    result=[]
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():continue
        try:
            record=json.loads(line)
            if not isinstance(record,dict):raise ValueError("audit must be an object")
            if record.get("full_evidence",{}).get("available"):
                ref=record["full_evidence"];blob=(directory/ref["path"]).resolve()
                if not blob.is_relative_to(directory.resolve()):raise ValueError("invalid blob path")
                data=blob.read_bytes()
                if hashlib.sha256(data).hexdigest()!=ref["sha256"]:raise ValueError("blob digest mismatch")
                record=json.loads(data)
                if not isinstance(record,dict):raise ValueError("audit blob must be an object")
            result.append(record)
        except (ValueError,OSError):
            result.append({"schema_version":"unreadable","judgement":{"quality_verdict":"indeterminate","failure_reasons":["missing/corrupt evidence"]}})
    return result


def metrics(audits):
    output={}
    for name in ("injection_applied","platform_defect_detected","agent_anomaly_recognized","agent_recovered","safe_stop","business_correct"):
        values=[a.get("judgement",{}).get("dimensions",{}).get(name) if name not in {"platform_defect_detected","agent_anomaly_recognized","agent_recovered"}
                or a.get("judgement",{}).get("dimensions",{}).get("injection_applied") is True else None for a in audits]
        known=[v for v in values if type(v) is bool]
        output[name]={"numerator":sum(known),"denominator":len(known),"indeterminate_or_not_applicable":len(values)-len(known),
                      "rate":sum(known)/len(known) if known else None}
    labelled=[a for a in audits if type(a.get("test_expectations",{}).get("hallucination_should_detect")) is bool]
    confusion={k:0 for k in ("true_positive","false_positive","true_negative","false_negative","indeterminate")}
    for audit in labelled:
        expected=audit["test_expectations"]["hallucination_should_detect"]
        actual=audit.get("judgement",{}).get("hallucination",{}).get("hallucination_detected")
        key="indeterminate" if actual is None else "true_positive" if expected and actual else "false_negative" if expected else "false_positive" if actual else "true_negative"
        confusion[key]+=1
    determinate=len(labelled)-confusion["indeterminate"]
    output["hallucination_labelled_benchmark"]={**confusion,"denominator":determinate,
        "excluded_ambiguous_samples":sum("hallucination_should_detect" in a.get("test_expectations",{}) and a["test_expectations"]["hallucination_should_detect"] is None for a in audits),
        "accuracy":(confusion["true_positive"]+confusion["true_negative"])/determinate if determinate else None}
    output["note"]="Defect detection/recognition/recovery denominators require actual injection and determinate outcomes; baseline/unknown excluded. Hallucination accuracy requires separate labels."
    return output
