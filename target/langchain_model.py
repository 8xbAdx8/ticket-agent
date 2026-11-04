"""标准 BaseChatModel 的可控离线模型；只复用 Mock 决策，不执行工具或 Agent 循环。"""
from typing import Any
from pydantic import Field
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from target.providers import MockProvider
from target.write_authorization import permissions


def legacy_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """框架消息到现有 Mock 的输入；实际工具结果必须来自 LangChain ToolMessage。"""
    out, names = [], {}
    for m in messages:
        if isinstance(m, AIMessage):
            calls = [{"id":c["id"], "name":c["name"], "arguments":c["args"]} for c in m.tool_calls]
            names.update({c["id"]:c["name"] for c in calls})
            out.append({"role":"assistant", "content":m.content, "tool_calls":calls})
        elif isinstance(m, ToolMessage):
            out.append({"role":"tool", "name":m.name or names.get(m.tool_call_id),
                        "tool_call_id":m.tool_call_id, "content":m.content})
        else:
            out.append({"role":"system" if isinstance(m,SystemMessage) else "user", "content":m.content})
    return out


class LangChainMockModel(BaseChatModel):
    name: str = "langchain_mock"
    decision_provider: Any = Field(default_factory=lambda: MockProvider(mutations={}), exclude=True)
    received_messages: list[list[BaseMessage]] = Field(default_factory=list, exclude=True)
    bound_tool_names: list[str] = Field(default_factory=list, exclude=True)

    @property
    def _llm_type(self) -> str:
        return "ticket-controlled-langchain-mock"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        # create_agent 绑定工具后调用本标准模型；执行仍由框架 ToolNode 管理。
        self.bound_tool_names = [t.name if hasattr(t,"name") else t.get("function",t)["name"] for t in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.received_messages.append(list(messages))
        converted = legacy_messages(messages)
        response = self._lock_only_response(converted)
        if converted and converted[-1].get("role") == "tool" and converted[-1].get("name") == "search_policy":
            import json
            if json.loads(converted[-1]["content"]).get("citation_status") == "unavailable":
                response = {"content":"政策检索结果缺少可检查的引用，无法提供来源编号。", "tool_calls":[]}
        if response is None:
            response = self.decision_provider.chat(converted, [])
        if any(c["name"] not in self.bound_tool_names for c in response.get("tool_calls",[])):
            response = {"content":"当前 LangChain 工具集不支持这项订单操作；请使用 legacy 或启用完整工具集。", "tool_calls":[]}
        calls = [{"id":c["id"], "name":c["name"], "args":c["arguments"], "type":"tool_call"}
                 for c in response.get("tool_calls", [])]
        message = AIMessage(content=response.get("content") or "", tool_calls=calls,
                            response_metadata={"finish_reason":response.get("finish_reason",getattr(self.decision_provider,"last_finish_reason","stop"))},
                            usage_metadata={"input_tokens":0, "output_tokens":0, "total_tokens":0})
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _lock_only_response(self, messages):
        """离线模型支持单独锁座确认；不把锁座确认扩展成下单/支付授权。"""
        import json
        from target.providers import _as_msg

        index = max(i for i, m in enumerate(messages) if m["role"] == "user")
        allowed = permissions(messages[index]["content"])
        if "lock_seat" not in allowed or "create_order" in allowed:
            return None
        results = [m for m in messages[index+1:] if m["role"] == "tool"]
        if not results:
            return None  # 先沿用原 Mock 的查询/条件继承流程。
        last = results[-1]
        result = json.loads(last["content"])
        if "error" in result:
            return None  # 失败仍走原错误总结，不生成成功文字。
        if last["name"] == "lock_seat":
            return _as_msg(f"已锁座，锁座编号 {result['lock_id']}；本轮未下单、未支付。", [])
        if last["name"] == "query_tickets":
            available = [t for t in result.get("trains", []) if t.get("seats_left", 0) > 0]
            if not available:
                return _as_msg("本轮未查到可锁定的余票，未锁座、未下单。", [])
            row = available[0]
            return _as_msg(None, [("lock_seat", {**{k:row[k] for k in ("train_no","date","seat_type")},
                                                "passengers":["张三"]})])
        return None
