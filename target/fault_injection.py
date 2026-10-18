"""显式、逐轮隔离的故障定义及审计；不生成模型响应，不修改业务数据库。"""
import copy
import json
import re
import uuid
from contextvars import ContextVar
from datetime import date, timedelta

MUTATION_NAMES = ("date_offset", "skip_lock", "repeat_call", "infinite_loop", "route_error", "no_citation")
STAGES = {"date_offset":"tool_arguments", "route_error":"tool_routing", "no_citation":"tool_result",
          "repeat_call":"tool_execution", "infinite_loop":"execution_strategy", "skip_lock":"tool_routing"}
ACTIVE_LEGACY_RUN = ContextVar("ticket_legacy_fault_run", default=None)


def normalize(values=None):
    if values is None:
        return {}
    if not isinstance(values, dict) or set(values) - set(MUTATION_NAMES):
        raise ValueError("变异必须是六种已知标识组成的JSON对象")
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
    def __init__(self, values, session_id, mode):
        self.config = normalize(values)
        self.run_id = uuid.uuid4().hex
        self.session_id, self.mode = session_id, mode
        self.events = []
        self.executions = []
        self.model_requests = []

    def emit(self, name, original=None, mutated=None, *, status="applied", reason=None, **extra):
        event = {"mutation":name,"stage":STAGES[name],"status":status,
                 "original":copy.deepcopy(original),"mutated":copy.deepcopy(mutated),
                 "reason":reason,**copy.deepcopy(extra)}
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
            self.emit("route_error", original, call, call_id=call["id"])
        if self.config.get("skip_lock") and call["name"] == "lock_seat":
            import config
            original = copy.deepcopy(call)
            call.update(name="create_order",args={"lock_id":"LK_INJECTED_MISSING",
                        "passenger_ids":call["args"].get("passengers",["张三"]),"contact":config.CURRENT_USER_PHONE})
            self.emit("skip_lock",original,call,call_id=call["id"])
        if self.config.get("date_offset") and call["name"] == "query_tickets":
            original = copy.deepcopy(call["args"])
            try:
                call["args"]["date"] = (date.fromisoformat(original["date"])+timedelta(days=1)).isoformat()
            except (KeyError, ValueError, TypeError):
                self.emit("date_offset",original,original,status="failed",reason="查询日期缺失或无效",call_id=call["id"])
                raise ValueError("故障注入需要有效查询日期") from None
            self.emit("date_offset",original,call["args"],call_id=call["id"])
        return call

    def result(self, name, result, call_id):
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
        for name in self.config:
            if not any(e["mutation"] == name for e in events):
                events.append({"mutation":name,"stage":STAGES[name],"status":"not_triggered",
                               "original":None,"mutated":None,"reason":"本轮没有到达适用的工具调用点"})
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
