"""真正的 create_agent 执行器；适配团队 Trace，原生循环不在本模块执行。"""
import copy
import json
import time
from dataclasses import dataclass, field
from typing import Any
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langsmith import tracing_context
import config
from target import tools, providers
from target.trace import Trace
from target.langchain_model import LangChainMockModel

READ_ONLY_TOOLS = ("query_tickets", "search_policy")


class ModelStepLimit(Exception):
    """限制模型实际调用轮数，与 V2 MAX_STEPS 同口径。"""


@dataclass
class TurnContext:
    trace: Trace
    user_message: str
    max_steps: int
    model_calls: int = 0
    current_step: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)


class ContractMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        ctx = request.runtime.context
        if ctx.model_calls >= ctx.max_steps:
            raise ModelStepLimit()
        ctx.current_step = ctx.model_calls
        ctx.model_calls += 1
        ctx.events.append({"event":"model_start", "model_step":ctx.model_calls})
        response = handler(request)
        for m in response.result:
            usage = getattr(m,"usage_metadata",None) or {}
            ctx.trace.tokens["prompt"] += usage.get("input_tokens",0)
            ctx.trace.tokens["completion"] += usage.get("output_tokens",0)
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
            response = handler(request)  # LangChain 真正调度注册的 StructuredTool。
            try:
                result = json.loads(response.content)
            except (ValueError, TypeError):
                result = {"error":response.content} if response.status == "error" else {"result":response.content}
            ok = response.status != "error" and not (isinstance(result,dict) and "error" in result)
            if not ok:
                response = response.model_copy(update={"status":"error"})
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
        return tools.dispatch(name,args)[0]
    return StructuredTool.from_function(execute,name=name,description=definition["description"],
                                        args_schema=copy.deepcopy(definition["parameters"]))


class LangChainAgent:
    def __init__(self, system_prompt: str, *, provider=None, model=None, tool_names=None):
        if config.PROVIDER not in ("mock","openai"):
            raise ValueError("AGENT_PROVIDER 只支持 mock/openai")
        if providers.MUTATIONS or getattr(provider,"mutations",{}):
            raise ValueError("六变异目前仅适用于 legacy 模式，请先清除开关")
        names = tuple(tool_names) if tool_names is not None else READ_ONLY_TOOLS
        if not names or len(set(names)) != len(names) or set(names)-set(READ_ONLY_TOOLS):
            raise ValueError("当前 LangChain 原型只开放 query_tickets/search_policy")
        self.tool_names = names
        if model is not None:
            self.model = model
        elif config.PROVIDER == "mock":
            self.model = LangChainMockModel(decision_provider=provider or providers.MockProvider(mutations={}))
        else:
            if not config.API_KEY:
                raise ValueError("LangChain Live 需要 AGENT_API_KEY；真实大模型尚未联网实测")
            from langchain_openai import ChatOpenAI
            self.model = ChatOpenAI(model=config.MODEL_NAME,api_key=config.API_KEY,base_url=config.BASE_URL,
                                    timeout=30,max_retries=0)
        self.provider_name = "langchain_mock" if config.PROVIDER == "mock" else "langchain_live"
        self.checkpointer = InMemorySaver()
        self.graph = create_agent(model=self.model, tools=[adapt_tool(n) for n in names],
                                  system_prompt=system_prompt+f"\n当前北京时间日期 {config.today().isoformat()}；业务全部虚构。",
                                  middleware=[ContractMiddleware()],context_schema=TurnContext,
                                  checkpointer=self.checkpointer)
        self.threads: set[str] = set()
        self.last_events: list[dict[str,Any]] = []

    def chat(self, session_id: str, message: str, *, save_trace=True) -> dict[str,Any]:
        trace = Trace(session_id,message)
        trace.provider = self.provider_name
        context = TurnContext(trace,message,config.MAX_STEPS)
        run_config = {"configurable":{"thread_id":session_id},"max_concurrency":1,
                      "recursion_limit":4*config.MAX_STEPS+10}
        self.threads.add(session_id)
        try:
            with tracing_context(enabled=False):  # 默认不把本地会话上传到外部观测服务。
                output = self.graph.invoke({"messages":[HumanMessage(content=message)]},config=run_config,context=context)
            reply = output["messages"][-1].text or "抱歉，我没能完成这次操作。"
            trace.finish(reply,"stop")
        except (ModelStepLimit,GraphRecursionError):
            reply = "达到最大执行步数，操作尚未完成；请查看工具轨迹。"
            trace.abort(reply,"max_steps_exceeded")
            self.graph.update_state(run_config,{"messages":[AIMessage(content=reply)]},as_node="model")
        except Exception as exc:
            reply = f"模型调用未完成 ({type(exc).__name__})，请检查配置或重试。"
            trace.finish(reply,"stop")
            self.graph.update_state(run_config,{"messages":[AIMessage(content=reply)]},as_node="model")
        self.last_events = context.events
        result = trace.to_dict()
        if save_trace:
            trace.save(record=result)
        return result

    def reset(self, session_id=None) -> None:
        targets = [session_id] if session_id else list(self.threads)
        for thread in targets:
            self.checkpointer.delete_thread(thread)
            self.threads.discard(thread)
