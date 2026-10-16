"""真正的 create_agent 执行器；适配团队 Trace，原生循环不在本模块执行。"""
import copy
import json
import time
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
            raise ModelStepLimit()
        ctx.current_step = ctx.model_calls
        ctx.model_calls += 1
        ctx.events.append({"event":"model_start", "model_step":ctx.model_calls})
        if ctx.deepseek_settings:
            from target.deepseek_runtime import DeepSeekError
            if sum(ctx.trace.tokens.values()) + ctx.deepseek_settings.max_output_tokens > ctx.deepseek_settings.turn_token_budget:
                raise DeepSeekError("observed_token_budget_exhausted")
        response = handler(request)
        for m in response.result:
            usage = getattr(m,"usage_metadata",None) or {}
            if ctx.deepseek_settings:
                from target.deepseek_runtime import DeepSeekError, safe_text
                # 仅保存最终文字、结构化调用和元数据，不保存 reasoning_content。
                ctx.events.append({"event":"model_response","model_step":ctx.model_calls,
                    "response_model":m.response_metadata.get("model_name"),"usage":usage,
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
        call = request.tool_call
        name, args = call["name"], call["args"]
        started = time.perf_counter()
        ctx.events.append({"event":"tool_start", "model_step":ctx.current_step+1,
                           "tool":name, "args":args, "call_id":call["id"]})
        try:
            ctx.tool_calls += 1
            blocked = ("DeepSeek 当前仅开放两个只读工具" if ctx.deepseek_settings and name not in READ_ONLY_TOOLS else
                       "达到工具调用次数上限" if ctx.deepseek_settings and ctx.tool_calls > ctx.deepseek_settings.max_tool_calls else
                       denial(name, args, ctx, request.state["messages"]))
            if blocked:
                response = ToolMessage(content=json.dumps({"error":blocked},ensure_ascii=False),
                                       tool_call_id=call["id"],name=name,status="error")
            else:
                response = handler(request)  # LangChain 调度；复用 V2 后端校验/状态机。
            try:
                result = json.loads(response.content)
            except (ValueError, TypeError):
                result = {"error":response.content} if response.status == "error" else {"result":response.content}
            ok = response.status != "error" and not (isinstance(result,dict) and "error" in result)
            if not ok:
                response = response.model_copy(update={"status":"error"})
            elif name == "lock_seat":
                ctx.lock_ids.add(result["lock_id"])
        except BackendToolFailure as exc:
            result = exc.result if isinstance(exc.result,dict) and "error" in exc.result else {"error":"后端报告工具执行失败","result":exc.result}
            ok = False
            response = ToolMessage(content=json.dumps(result,ensure_ascii=False),tool_call_id=call["id"],name=name,status="error")
        except Exception as exc:
            result, ok = {"error":f"工具执行失败 ({type(exc).__name__})"}, False
            response = ToolMessage(content=json.dumps(result,ensure_ascii=False),tool_call_id=call["id"],name=name,status="error")
        latency = int((time.perf_counter()-started)*1000)
        ctx.trace.record_call(ctx.current_step,name,args,result,ok,latency)
        ctx.events.append({"event":"tool_end", "tool":name,"call_id":call["id"],
                           "ok":ok,"latency_ms":latency,"result":result})
        return response


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
    def __init__(self, system_prompt: str, *, provider=None, model=None, tool_names=None):
        if config.PROVIDER not in ("mock","openai","deepseek"):
            raise ValueError("AGENT_PROVIDER 只支持 mock/openai/deepseek")
        if providers.MUTATIONS or getattr(provider,"mutations",{}):
            raise ValueError("六变异目前仅适用于 legacy 模式，请先清除开关")
        if config.LC_TOOLSET not in ("read_only","all"):
            raise ValueError("AGENT_LC_TOOLSET 只支持 read_only/all")
        names = tuple(tool_names) if tool_names is not None else (
            tuple(tools.TOOL_NAMES) if config.LC_TOOLSET == "all" else READ_ONLY_TOOLS)
        if not names or len(set(names)) != len(names) or set(names)-set(tools.TOOL_NAMES):
            raise ValueError("LangChain 工具必须是现有八个工具的非空、不重复子集")
        self.tool_names = names
        self.deepseek_settings = None
        if config.PROVIDER == "deepseek":
            from target.deepseek_runtime import Settings, DeepSeekError
            if config.LC_TOOLSET != "read_only" or not set(names) <= set(READ_ONLY_TOOLS) or provider is not None:
                raise DeepSeekError("read_only_tools_required")
            self.deepseek_settings = Settings.from_env()
        if model is not None:
            self.model = model
        elif config.PROVIDER == "mock":
            self.model = LangChainMockModel(decision_provider=provider or providers.MockProvider(mutations={}))
        elif config.PROVIDER == "deepseek":
            from target.deepseek_runtime import make_model
            self.model = make_model(self.deepseek_settings)
        else:
            if not config.API_KEY:
                raise ValueError("OpenAI 风格 LangChain Live 需要 AGENT_API_KEY；DeepSeek 使用独立 DEEPSEEK_API_KEY")
            from langchain_openai import ChatOpenAI
            self.model = ChatOpenAI(model=config.MODEL_NAME,api_key=config.API_KEY,base_url=config.BASE_URL,
                                    timeout=30,max_retries=0)
        self.provider_name = "deepseek_live" if config.PROVIDER == "deepseek" else (
            "langchain_mock" if config.PROVIDER == "mock" else "langchain_live")
        if self.deepseek_settings:
            from target.deepseek_runtime import READ_ONLY_PROMPT
            # 不继承通用订票/支付指令，避免与只读能力冲突。
            system_prompt = READ_ONLY_PROMPT
        self.checkpointer = InMemorySaver()
        self.graph = create_agent(model=self.model, tools=[adapt_tool(n) for n in names],
                                  system_prompt=system_prompt+f"\n当前北京时间日期 {config.today().isoformat()}；业务全部虚构。"
                                  + ("" if self.deepseek_settings else
                                  "\n写操作必须获得本轮明确授权；订票不包含支付。锁座一轮至多一次成功，下单必须用本轮成功 lock_id。"
                                  "支付/退票使用用户指定或最近工具结果订单；不明确时先澄清。"),
                                  middleware=[ContractMiddleware()],context_schema=TurnContext,
                                  checkpointer=self.checkpointer)
        self.threads: set[str] = set()
        self.last_events: list[dict[str,Any]] = []

    def chat(self, session_id: str, message: str, *, save_trace=True) -> dict[str,Any]:
        trace = Trace(session_id,message)
        trace.provider = self.provider_name
        limit = min(config.MAX_STEPS,self.deepseek_settings.max_model_calls) if self.deepseek_settings else config.MAX_STEPS
        context = TurnContext(trace,message,limit,deepseek_settings=self.deepseek_settings,
                              purchase_tools_available={"lock_seat","create_order"} <= set(self.tool_names))
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
                validate_read_only_reply(reply)
            trace.finish(reply,"stop")
        except (ModelStepLimit,GraphRecursionError):
            reply = "达到最大执行步数，操作尚未完成；请查看工具轨迹。"
            trace.abort(reply,"max_steps_exceeded")
            self.graph.update_state(run_config,{"messages":[AIMessage(content=reply)]},as_node="model")
        except Exception as exc:
            if self.deepseek_settings:
                from target.deepseek_runtime import DeepSeekError, safe_error, save_run_evidence
                error = safe_error(exc)
                trace.finish("请求未完成；本轮真实 Token 用量可能未知。","stop")
                self.last_events = context.events
                if save_trace:
                    save_run_evidence(trace,context.events,error)
                # 失败轮可能残留未配对 tool_call，不能污染下一轮协议；历史 JSONL 不删除。
                try:
                    self.reset(session_id)
                except Exception:
                    # 不用检查点清理异常覆盖原始脱敏错误。
                    pass
                # 不把未知用量伪装成契约内的数值 0；失败明细单独保存。
                raise DeepSeekError(error["category"],error["http_status"]) from None
            reply = f"模型调用未完成 ({type(exc).__name__})，请检查配置或重试。"
            trace.finish(reply,"stop")
            self.graph.update_state(run_config,{"messages":[AIMessage(content=reply)]},as_node="model")
        self.last_events = context.events
        result = trace.to_dict()
        if self.deepseek_settings:
            from target.deepseek_runtime import safe_text
            # 仅DeepSeek公开Trace脱敏，覆盖user_msg/工具参数/结果预览；Mock原样返回。
            result = json.loads(safe_text(json.dumps(result, ensure_ascii=False)))
        if save_trace:
            trace.save(record=result)
            if self.deepseek_settings:
                from target.deepseek_runtime import save_run_evidence
                save_run_evidence(trace,context.events)
        return result

    def reset(self, session_id=None) -> None:
        targets = [session_id] if session_id else list(self.threads)
        for thread in targets:
            self.checkpointer.delete_thread(thread)
            self.threads.discard(thread)
