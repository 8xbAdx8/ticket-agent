"""显式、逐轮隔离的故障定义及审计；不生成模型响应，不修改业务数据库。"""
import copy
import json
import re
import uuid
from contextvars import ContextVar
from datetime import date, timedelta, datetime, timezone

MUTATION_NAMES = ("date_offset", "skip_lock", "repeat_call", "infinite_loop", "route_error", "no_citation")
LEGACY_MUTATION_NAMES = MUTATION_NAMES
MUTATION_NAMES += ("hallucinated_train","concurrent_duplicate_order")
STAGES = {"date_offset":"tool_arguments", "route_error":"tool_routing", "no_citation":"tool_result",
          "repeat_call":"tool_execution", "infinite_loop":"execution_strategy", "skip_lock":"tool_routing"}
STAGES.update(hallucinated_train="tool_result",concurrent_duplicate_order="sandbox_concurrent_backend")
ACTIVE_LEGACY_RUN = ContextVar("ticket_legacy_fault_run", default=None)


def normalize(values=None):
    if values is None:
        return {}
    if not isinstance(values, dict) or set(values) - set(MUTATION_NAMES):
        raise ValueError("变异必须是八种已知标识组成的JSON对象")
    result = {}
    for name, value in values.items():
        if value is False or value == 0:
            continue
        if name == "date_offset":
            if type(value) is not int or value != 1:
                raise ValueError("date_offset仅支持整数1")
        elif value is not True:
            raise ValueError(f"{name}仅支持true/false")
        result[name] = value
    return result


def from_env():
    import os
    try:
        return normalize(json.loads(os.getenv("AGENT_MUTATIONS", "{}")))
    except json.JSONDecodeError as exc:
        raise ValueError("AGENT_MUTATIONS必须是JSON对象") from exc


class FaultRun:
    def __init__(self, values, session_id, mode, trace_id=None):
        self.config = normalize(values)
        self.run_id = trace_id or uuid.uuid4().hex
        self.session_id, self.mode = session_id, mode
        self.events = []
        self.executions = []
        self.model_requests = []

    def emit(self, name, original=None, mutated=None, *, status="applied", reason=None, **extra):
        event = {"mutation":name,"stage":STAGES[name],"status":status,
                 "original":copy.deepcopy(original),"mutated":copy.deepcopy(mutated),
                 "reason":reason,"event_id":uuid.uuid4().hex,"timestamp":datetime.now(timezone.utc).isoformat(),**copy.deepcopy(extra)}
        self.events.append(event)
        return event

    def arguments(self, call, user_message):
        call = copy.deepcopy(call)
        if self.config.get("route_error") and call["name"] == "search_policy":
            import config
            from target.providers import CITIES
            original = copy.deepcopy(call)
            call.update(name="query_tickets", args={"from_city":next((c for c in CITIES if c in user_message),"北京"),
                        "to_city":"上海","date":(config.today()+timedelta(days=1)).isoformat()})
            self.emit("route_error", original, call, status="prepared", call_id=call["id"])
        if self.config.get("skip_lock") and call["name"] == "lock_seat":
            import config
            original = copy.deepcopy(call)
            call.update(name="create_order",args={"lock_id":"LK_INJECTED_MISSING",
                        "passenger_ids":call["args"].get("passengers",["张三"]),"contact":config.CURRENT_USER_PHONE})
            self.emit("skip_lock",original,call,status="prepared",call_id=call["id"])
        if self.config.get("date_offset") and call["name"] == "query_tickets":
            original = copy.deepcopy(call["args"])
            try:
                call["args"]["date"] = (date.fromisoformat(original["date"])+timedelta(days=1)).isoformat()
            except (KeyError, ValueError, TypeError):
                self.emit("date_offset",original,original,status="failed",reason="查询日期缺失或无效",call_id=call["id"])
                raise ValueError("故障注入需要有效查询日期") from None
            self.emit("date_offset",original,call["args"],status="prepared",call_id=call["id"])
        return call

    def result(self, name, result, call_id):
        if self.config.get("hallucinated_train") and name == "query_tickets":
            from target.diagnostics import authority_snapshot
            import config
            authority=authority_snapshot(config.DB_PATH)
            if not authority["available"] or "G9999" in authority["trains"]:
                self.emit("hallucinated_train",result,result,status="blocked",reason="权威库不可读或G9999已存在",call_id=call_id)
            elif not isinstance(result,dict) or not result.get("trains"):
                self.emit("hallucinated_train",result,result,status="not_applicable",reason="无可作为字段模板的真实车次结果",call_id=call_id)
            else:
                changed=copy.deepcopy(result)
                fake=copy.deepcopy(changed["trains"][0]);fake["train_no"]="G9999"
                changed["trains"].insert(0,fake);changed["count"]=len(changed["trains"])
                self.emit("hallucinated_train",result,changed,call_id=call_id,target="query_tickets.trains",
                          authority_absent=True,test_only=True)
                result=changed
        if not self.config.get("no_citation") or name != "search_policy":
            return result
        if not isinstance(result,dict) or not result.get("hits"):
            self.emit("no_citation",result,result,status="not_applicable",reason="检索无政策片段",call_id=call_id)
            return result
        changed = copy.deepcopy(result)
        for hit in changed["hits"]:
            hit.pop("doc_id",None)
            hit.pop("source",None)
            for key in ("title","content"):
                if isinstance(hit.get(key),str):
                    hit[key] = re.sub(r"\bP\d+\b","",hit[key])
        changed["citation_status"] = "unavailable"
        self.emit("no_citation",result,changed,call_id=call_id)
        return changed

    def report(self, *, finish_reason=None, error=None):
        events = copy.deepcopy(self.events)
        for event in events:
            if event["status"] == "prepared":
                event.update(status="failed",reason="参数或路由已准备，但未到达实际工具执行")
        for name in self.config:
            if not any(e["mutation"] == name for e in events):
                events.append({"mutation":name,"stage":STAGES[name],"status":"not_applicable" if name=="concurrent_duplicate_order" else "not_triggered",
                               "original":None,"mutated":None,"reason":"M8使用独立并发测试执行器，不由模型随机触发" if name=="concurrent_duplicate_order" else "本轮没有到达适用的工具调用点",
                               "event_id":uuid.uuid4().hex,"timestamp":datetime.now(timezone.utc).isoformat()})
        return {"run_id":self.run_id,"session_id":self.session_id,"mode":self.mode,
                "mutations":self.config,"injection_events":events,"executions":copy.deepcopy(self.executions),
                "model_requests":copy.deepcopy(self.model_requests),"finish_reason":finish_reason,"error":error,
                "assessment":{"agent_defect_detected":None,"agent_recovered":None,
                              "note":"由B根据原始轨迹和预先定义的期望独立判定，不等同于注入成功"}}

    def save(self, trace, *, error=None):
        import config
        from target.deepseek_runtime import safe_text
        report = self.report(finish_reason=trace.finish_reason,error=error)
        report["user_msg"] = trace.user_msg
        report["agent_reply"] = trace.reply
        report["tool_sequence"] = trace.tool_names
        report["tokens"] = trace.tokens if not error else None
        report["trace_latency_ms"] = trace.total_latency_ms
        path = config.TRACE_DIR / "mutation_runs.jsonl"
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("a",encoding="utf-8") as out:
            out.write(safe_text(json.dumps(report,ensure_ascii=False))+"\n")
        return json.loads(safe_text(json.dumps(report,ensure_ascii=False)))


def legacy_event(name, original, mutated, **extra):
    run = ACTIVE_LEGACY_RUN.get()
    if run is not None:
        run.emit(name, original, mutated, **extra)


def summarize(reports):
    """按run×变异计数；缺陷检出/恢复只汇总外部明确判定，未知不填0%。"""
    counts = {k:0 for k in ("requested","applied","failed","blocked","not_triggered","not_applicable")}
    assessed = {"agent_defect_detected":[],"agent_recovered":[]}
    for report in reports:
        for name in report["mutations"]:
            states = {e["status"] for e in report["injection_events"] if e["mutation"] == name}
            state = next((s for s in ("failed","blocked","applied","not_applicable","not_triggered") if s in states),"not_triggered")
            counts["requested"] += 1
            counts[state] += 1
        for key in assessed:
            value = report.get("assessment",{}).get(key)
            if type(value) is bool:
                assessed[key].append(value)
    triggered = counts["applied"]+counts["failed"]+counts["blocked"]
    return {"counts":counts,"injection_success_rate":counts["applied"]/triggered if triggered else None,
            "injection_success_denominator":"applied + failed + blocked；未触发/不适用单列",
            "agent_defect_detection_rate":sum(assessed["agent_defect_detected"])/len(assessed["agent_defect_detected"]) if assessed["agent_defect_detected"] else None,
            "agent_recovery_rate":sum(assessed["agent_recovered"])/len(assessed["agent_recovered"]) if assessed["agent_recovered"] else None,
            "explicit_agent_judgements":{k:len(v) for k,v in assessed.items()}}
