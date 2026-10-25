"""真正的 create_agent 执行器；适配团队 Trace，原生循环不在本模块执行。"""
import copy
import json
import time
from datetime import datetime,timezone
from dataclasses import dataclass, field
from typing import Any
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langsmith import tracing_context
import config
from target import tools, providers
from target.trace import Trace
from target.langchain_model import LangChainMockModel
from target.write_authorization import denial, purchase_clarification

READ_ONLY_TOOLS = ("query_tickets", "search_policy")


class ModelStepLimit(Exception):
    """限制模型实际调用轮数，与 V2 MAX_STEPS 同口径。"""


class ForcedLoopStop(ModelStepLimit):
    """有限监控重入已达到Agent步数上限，没有伪造额外模型调用。"""


class BackendToolFailure(Exception):
    def __init__(self, result):
        self.result = result


@dataclass
class TurnContext:
    trace: Trace
    user_message: str
    max_steps: int
    model_calls: int = 0
    current_step: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    lock_ids: set[str] = field(default_factory=set)
    deepseek_settings: Any = None
    tool_calls: int = 0
    purchase_tools_available: bool = False
    fault_run: Any = None
    model_limit_reason: str = "agent_max_steps"


class ContractMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        ctx = request.runtime.context
        if ctx.model_calls == 0 and ctx.purchase_tools_available and not ctx.deepseek_settings:
            clarification = purchase_clarification(ctx.user_message)
            if clarification:
                # 在模型与工具之前完成澄清；框架仍保存真实用户消息和助手消息。
                ctx.events.append({"event":"authorization_clarification", "text":clarification})
                return ModelResponse(result=[AIMessage(content=clarification)])
        if ctx.model_calls >= ctx.max_steps:
            ctx.events.append({"event":"termination","reason":ctx.model_limit_reason})
            raise ModelStepLimit()
        ctx.current_step = ctx.model_calls
        ctx.model_calls += 1
        ctx.events.append({"event":"model_start", "model_step":ctx.model_calls})
        if ctx.deepseek_settings:
            from target.deepseek_runtime import DeepSeekError
            if sum(ctx.trace.tokens.values()) + ctx.deepseek_settings.max_output_tokens > ctx.deepseek_settings.turn_token_budget:
                raise DeepSeekError("observed_token_budget_exhausted")
        model_started = time.perf_counter()
        response = handler(request)
        for m in response.result:
            ctx.fault_run.model_requests.append({"model_step":ctx.model_calls,
                "tool_calls":copy.deepcopy(m.tool_calls),"final_text":m.text if not m.tool_calls else None})
            usage = getattr(m,"usage_metadata",None) or {}
            if ctx.deepseek_settings:
                from target.deepseek_runtime import DeepSeekError, safe_text
                # 仅保存最终文字、结构化调用和元数据，不保存 reasoning_content。
                ctx.events.append({"event":"model_response","model_step":ctx.model_calls,
                    "response_model":m.response_metadata.get("model_name"),"usage":usage,
                    "latency_ms":int((time.perf_counter()-model_started)*1000),
                    "finish_reason":m.response_metadata.get("finish_reason"),
                    "tool_calls":[{"id":c["id"],"name":c["name"],"args":c["args"]} for c in m.tool_calls]})
                if not m.tool_calls:
                    ctx.events.append({"event":"model_final","model_step":ctx.model_calls,"text":safe_text(m.text)})
                if not all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens","output_tokens")):
                    raise DeepSeekError("token_usage_unknown")
                m.content = safe_text(m.content) if isinstance(m.content,str) else m.content
            ctx.trace.tokens["prompt"] += usage.get("input_tokens",0)
            ctx.trace.tokens["completion"] += usage.get("output_tokens",0)
            if ctx.deepseek_settings and m.invalid_tool_calls:
                ctx.events.append({"event":"invalid_tool_calls","calls":m.invalid_tool_calls})
                raise DeepSeekError("invalid_tool_call")
        ctx.events.append({"event":"model_end", "model_step":ctx.model_calls})
        return response

    def wrap_tool_call(self, request, handler):
        ctx = request.runtime.context
        original = copy.deepcopy(request.tool_call)
        run = ctx.fault_run
        call = run.arguments(original,ctx.user_message) if run.config else original
        sandbox_block = None
        write_fault = "skip_lock" if original["name"] == "lock_seat" and run.config.get("skip_lock") else (
            "infinite_loop" if original["name"] == "monitor_seat" and run.config.get("infinite_loop") else None)
        if write_fault and not ctx.deepseek_settings:
            from target.deepseek_runtime import Settings, DeepSeekError
            try:
                settings = Settings.from_env()
                if settings.profile != "full_sandbox":
                    raise DeepSeekError("isolated_sandbox_required")
            except (DeepSeekError, ValueError):
                sandbox_block = "LangChain Mock的写变异同样要求显式full_sandbox隔离库"
                run.emit(write_fault,status="blocked",reason=sandbox_block,call_id=call["id"])

        def execute(index):
            name, args = call["name"], call["args"]
            started = time.perf_counter()
            ctx.events.append({"event":"tool_start", "model_step":ctx.current_step+1,
                "tool":name,"args":copy.deepcopy(args),"call_id":call["id"],"execution_index":index,
                "model_requested_tool":original["name"],"model_requested_args":original["args"]})
            ctx.tool_calls += 1
            from target.deepseek_runtime import allowed_tools
            blocked = sandbox_block or ("当前Live工具白名单禁止该工具" if ctx.deepseek_settings and (
                name not in allowed_tools(ctx.deepseek_settings) or original["name"] not in allowed_tools(ctx.deepseek_settings)) else
                "达到工具调用次数上限" if ctx.deepseek_settings and ctx.tool_calls > ctx.deepseek_settings.max_tool_calls else
                denial(name,args,ctx,request.state["messages"]))
            # skip_lock仅取消本次调用的编排前置检查，仍检查用户购买授权；
            # 原后端create_order必须实际执行并拒绝不存在的lock_id，不削弱其约束。
            if (blocked and blocked.startswith("本轮没有该 lock_id") and run.config.get("skip_lock") and original["name"] == "lock_seat"
                    and name == "create_order" and args.get("lock_id") == "LK_INJECTED_MISSING"
                    and (not ctx.deepseek_settings or ctx.deepseek_settings.profile == "full_sandbox")):
                from target.write_authorization import permissions
                if "create_order" in permissions(ctx.user_message):
                    blocked = None
            executed = False
            execution_diagnostic={}
            try:
                if blocked:
                    result,ok = {"error":blocked},False
                else:
                    executed = True
                    actual_request = request if call == original else request.override(tool_call=call,tool=adapt_tool(name))
                    token=tools.DISPATCH_OBSERVER.set(execution_diagnostic.update)
                    try:
                        response = handler(actual_request)
                    finally:
                        tools.DISPATCH_OBSERVER.reset(token)
                    try:
                        result = json.loads(response.content)
                    except (ValueError, TypeError):
                        result = {"error":response.content} if response.status == "error" else {"result":response.content}
                    ok = response.status != "error" and not (isinstance(result,dict) and "error" in result)
                    if ok and name == "lock_seat":
                        ctx.lock_ids.add(result["lock_id"])
            except BackendToolFailure as exc:
                result = exc.result if isinstance(exc.result,dict) and "error" in exc.result else {
                    "error":"后端报告工具执行失败","result":exc.result}
                ok = False
            except Exception as exc:
                result,ok = {"error":f"工具执行失败 ({type(exc).__name__})"},False
            original_result = copy.deepcopy(result)
            if ok and run.config:
                result = run.result(name,result,call["id"])
            latency = int((time.perf_counter()-started)*1000)
            confirmed_execution=execution_diagnostic.get("backend_executed") if executed else False
            ctx.trace.record_call(ctx.current_step,name,args,result,ok,latency)
            entry = {"event":"tool_end","tool":name,"args":copy.deepcopy(args),"call_id":call["id"],
                     "ok":ok,"executed":confirmed_execution,"execution_index":index,"latency_ms":latency,
                     "result":copy.deepcopy(result),"parameter_validation":execution_diagnostic.get("validation",{"status":"unknown"}),
                     "timestamp":datetime.now(timezone.utc).isoformat(),"step":ctx.current_step+1}
            ctx.events.append(entry)
            run.executions.append({**entry,"original_result":original_result})
            if run.config:
                for event in run.events:
                    if event.get("call_id") == call["id"] and event["mutation"] in ("date_offset","route_error","skip_lock"):
                        event["execution"] = {"executed":executed,"ok":ok}
                        event["related_step"]=ctx.current_step+1
                        event["status"] = "applied" if executed else "blocked"
                        if not executed:
                            event["reason"] = blocked or "执行器拒绝调用"
            return ToolMessage(content=json.dumps(result,ensure_ascii=False),tool_call_id=call["id"],name=name,
                               status="success" if ok else "error"),ok,blocked

        first,ok,blocked = execute(1)
        if run.config.get("repeat_call") and call["name"] == "query_tickets":
            second,ok2,blocked2 = execute(2)
            run.emit("repeat_call",1,2 if not blocked2 else 1,status="blocked" if blocked2 else "applied",
                     reason=blocked2,call_id=call["id"],second_ok=ok2)
            if not ok2:
                return second
        if run.config.get("infinite_loop") and call["name"] == "monitor_seat" and ok:
            count = 1
            if config.MAX_STEPS < 2:
                run.emit("infinite_loop",1,1,status="blocked",reason="Agent步数上限不允许再次执行",call_id=call["id"])
                ctx.events.append({"event":"termination","reason":"agent_max_steps","actual_tool_executions":1})
                raise ForcedLoopStop()
            while count < config.MAX_STEPS:
                _,success,guard = execute(count+1)
                if guard or not success:
                    run.emit("infinite_loop",1,count,status="blocked",reason=guard or "监控工具失败",call_id=call["id"])
                    from target.deepseek_runtime import DeepSeekError
                    ctx.events.append({"event":"termination","reason":"tool_call_limit" if guard else "tool_failure"})
                    raise DeepSeekError("tool_call_limit_exceeded" if guard else "tool_execution_failed")
                count += 1
            run.emit("infinite_loop",1,count,call_id=call["id"],reason="有限模拟到达Agent max_steps")
            ctx.events.append({"event":"termination","reason":"agent_max_steps","actual_tool_executions":count})
            raise ForcedLoopStop()
        return first


def adapt_tool(name: str) -> StructuredTool:
    definition = next(t["function"] for t in tools.TOOLS if t["function"]["name"] == name)
    def execute(**args):
        result, ok, _ = tools.dispatch(name,args)
        if not ok:
            raise BackendToolFailure(result)
        return result
    return StructuredTool.from_function(execute,name=name,description=definition["description"],
                                        args_schema=copy.deepcopy(definition["parameters"]))


class LangChainAgent:
    def __init__(self, system_prompt: str, *, provider=None, model=None, tool_names=None, mutations=None):
        if config.PROVIDER not in ("mock","openai","deepseek","bailian"):
            raise ValueError("AGENT_PROVIDER 只支持 mock/openai/deepseek/bailian")
        if providers.MUTATIONS or getattr(provider,"mutations",{}):
            raise ValueError("六变异目前仅适用于 legacy 模式，请先清除开关")
        if config.LC_TOOLSET not in ("read_only","all"):
            raise ValueError("AGENT_LC_TOOLSET 只支持 read_only/all")
        names = tuple(tool_names) if tool_names is not None else (
            tuple(tools.TOOL_NAMES) if config.LC_TOOLSET == "all" else READ_ONLY_TOOLS)
        if not names or len(set(names)) != len(names) or set(names)-set(tools.TOOL_NAMES):
            raise ValueError("LangChain 工具必须是现有八个工具的非空、不重复子集")
        self.tool_names = names
        from target.fault_injection import normalize
        self.mutations = normalize(mutations)
        self.last_fault_report = None
        self.last_audit_report = None
        self.last_live_run = None
        self.live_runtime = None
        self.deepseek_settings = None
        if config.PROVIDER in ("deepseek","bailian"):
            from target import deepseek_runtime, bailian_runtime
            from target.deepseek_runtime import DeepSeekError
            self.live_runtime = bailian_runtime if config.PROVIDER == "bailian" else deepseek_runtime
            self.deepseek_settings = self.live_runtime.Settings.from_env()
            from target.deepseek_runtime import allowed_tools
            expected = "all" if self.deepseek_settings.profile == "full_sandbox" else "read_only"
            if config.LC_TOOLSET != expected or not set(names) <= allowed_tools(self.deepseek_settings) or provider is not None:
                raise DeepSeekError("read_only_tools_required")
        if model is not None:
            self.model = model
        elif config.PROVIDER == "mock":
            self.model = LangChainMockModel(decision_provider=provider or providers.MockProvider(mutations={}))
        elif self.live_runtime:
            self.model = self.live_runtime.make_model(self.deepseek_settings)
        else:
            if not config.API_KEY:
                raise ValueError("OpenAI 风格 LangChain Live 需要 AGENT_API_KEY；DeepSeek 使用独立 DEEPSEEK_API_KEY")
            from langchain_openai import ChatOpenAI
            self.model = ChatOpenAI(model=config.MODEL_NAME,api_key=config.API_KEY,base_url=config.BASE_URL,
                                    timeout=30,max_retries=0)
        self.provider_name = config.PROVIDER+"_live" if self.live_runtime else (
            "langchain_mock" if config.PROVIDER == "mock" else "langchain_live")
        if self.deepseek_settings and self.deepseek_settings.profile == "read_only":
            from target.deepseek_runtime import READ_ONLY_PROMPT
            # 不继承通用订票/支付指令，避免与只读能力冲突。
            system_prompt = READ_ONLY_PROMPT
        self.checkpointer = InMemorySaver()
        self.graph = create_agent(model=self.model, tools=[adapt_tool(n) for n in names],
                                  system_prompt=system_prompt+f"\n当前北京时间日期 {config.today().isoformat()}；业务全部虚构。"
                                  + ("" if self.deepseek_settings and self.deepseek_settings.profile == "read_only" else
                                  "\n写操作必须获得本轮明确授权；订票不包含支付。锁座一轮至多一次成功，下单必须用本轮成功 lock_id。"
                                  "支付/退票使用用户指定或最近工具结果订单；不明确时先澄清。"),
                                  middleware=[ContractMiddleware()],context_schema=TurnContext,
                                  checkpointer=self.checkpointer)
        self.threads: set[str] = set()
        self.last_events: list[dict[str,Any]] = []

    def chat(self, session_id: str, message: str, *, save_trace=True) -> dict[str,Any]:
        trace = Trace(session_id,message)
        self.last_live_run = None
        trace.provider = self.provider_name
        limit = min(config.MAX_STEPS,self.deepseek_settings.max_model_calls) if self.deepseek_settings else config.MAX_STEPS
        context = TurnContext(trace,message,limit,deepseek_settings=self.deepseek_settings,
                              purchase_tools_available={"lock_seat","create_order"} <= set(self.tool_names))
        from target.fault_injection import FaultRun
        context.fault_run = FaultRun(self.mutations,session_id,self.provider_name,trace_id=trace.trace_id)
        if self.deepseek_settings and config.MAX_STEPS > self.deepseek_settings.max_model_calls:
            context.model_limit_reason = "model_call_limit"
        if self.mutations:
            context.events.append({"event":"fault_run","run_id":context.fault_run.run_id,"mutations":self.mutations})
            for name,tool in (("skip_lock","lock_seat"),("infinite_loop","monitor_seat")):
                if self.mutations.get(name) and tool not in self.tool_names:
                    context.fault_run.emit(name,status="not_applicable",reason="当前工具集未开放"+tool)
        run_config = {"configurable":{"thread_id":session_id},"max_concurrency":1,
                      "recursion_limit":4*config.MAX_STEPS+10}
        self.threads.add(session_id)
        try:
            with tracing_context(enabled=False):  # 默认不把本地会话上传到外部观测服务。
                output = self.graph.invoke({"messages":[HumanMessage(content=message)]},config=run_config,context=context)
            reply = output["messages"][-1].text or "抱歉，我没能完成这次操作。"
            if self.deepseek_settings:
                from target.deepseek_runtime import DeepSeekError, validate_read_only_reply
                if any(not c["ok"] for s in trace.steps for c in s["calls"]):
                    raise DeepSeekError("tool_execution_failed")
                if self.deepseek_settings.profile == "read_only":
                    validate_read_only_reply(reply)
                if self.mutations.get("no_citation") and any(e["mutation"] == "no_citation" and e["status"] == "applied" for e in context.fault_run.events):
                    import re
                    if re.search(r"\bP\d+\b",reply):
                        raise DeepSeekError("unavailable_policy_citation")
            trace.finish(reply,"stop")
        except (ModelStepLimit,GraphRecursionError) as exc:
            reply = "达到最大执行步数，操作尚未完成；请查看工具轨迹。"
            trace.abort(reply,"max_steps_exceeded")
            if isinstance(exc,ForcedLoopStop):
                self.reset(session_id)
            else:
                self.graph.update_state(run_config,{"messages":[AIMessage(content=reply)]},as_node="model")
        except Exception as exc:
            if self.deepseek_settings:
                from target.deepseek_runtime import DeepSeekError, safe_error, save_run_evidence
                error = safe_error(exc)
                trace.finish("请求未完成；本轮真实 Token 用量可能未知。","stop")
                self.last_events = context.events
                if save_trace and config.PROVIDER == "deepseek":
                    save_run_evidence(trace,context.events,error)
                self.last_fault_report = context.fault_run.save(trace,error=error) if self.mutations and save_trace else (
                    context.fault_run.report(error=error) if self.mutations else None)
                from target.diagnostics import make_audit
                self.last_audit_report=make_audit(trace,context.fault_run,events=context.events,error=error,save=save_trace)
                from target.live_evidence import record_run
                self.last_live_run = record_run(trace,context.events,error=error,save=save_trace,local_trace_saved=False)
                # 失败轮可能残留未配对 tool_call，不能污染下一轮协议；历史 JSONL 不删除。
                try:
                    self.reset(session_id)
                except Exception:
                    # 不用检查点清理异常覆盖原始脱敏错误。
                    pass
                # 不把未知用量伪装成契约内的数值 0；失败明细单独保存。
                error_type = self.live_runtime.BailianError if config.PROVIDER == "bailian" else DeepSeekError
                raise error_type(error["category"],error["http_status"]) from None
            reply = f"模型调用未完成 ({type(exc).__name__})，请检查配置或重试。"
            trace.finish(reply,"stop")
            self.graph.update_state(run_config,{"messages":[AIMessage(content=reply)]},as_node="model")
        self.last_events = context.events
        self.last_fault_report = context.fault_run.save(trace) if self.mutations and save_trace else (
            context.fault_run.report(finish_reason=trace.finish_reason) if self.mutations else None)
        result = trace.to_dict()
        if self.deepseek_settings:
            from target.deepseek_runtime import safe_text
            # 仅DeepSeek公开Trace脱敏，覆盖user_msg/工具参数/结果预览；Mock原样返回。
            result = json.loads(safe_text(json.dumps(result, ensure_ascii=False)))
        from target.diagnostics import make_audit
        self.last_audit_report=make_audit(trace,context.fault_run,events=context.events,save=save_trace,public_trace=result)
        if save_trace:
            trace.save(record=result)
            if self.deepseek_settings and config.PROVIDER == "deepseek":
                from target.deepseek_runtime import save_run_evidence
                save_run_evidence(trace,context.events)
        if self.deepseek_settings:
            from target.live_evidence import record_run
            self.last_live_run = record_run(trace,context.events,public_trace=result,save=save_trace,local_trace_saved=save_trace)
        return result

    def reset(self, session_id=None) -> None:
        targets = [session_id] if session_id else list(self.threads)
        for thread in targets:
            self.checkpointer.delete_thread(thread)
            self.threads.discard(thread)
