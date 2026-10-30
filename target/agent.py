# -*- coding: utf-8 -*-
"""被测智能体主循环。

对外只有一个入口：
    Agent().chat(session_id, message) -> 契约 JSON（顶层字段，不含嵌套 trace）
成员 B 的断言、成员 C 的看板都只依赖这个返回值（接口契约见 docs/contract.md）。
"""
import json
import time
from threading import RLock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from target import tools
from target.trace import Trace
from target.providers import get_provider
from target.run_events import recorded_run

SYSTEM_PROMPT = (
    "你是一个出行服务智能助手，帮助用户查询车次、抢票下单、退改签以及解答票务政策。\n"
    "规则：\n"
    "1. 涉及具体车次、余票、订单、价格时，必须调用相应工具，不得凭空编造；\n"
    "2. 用户说'明天''下周三'等相对时间，必须先换算成 YYYY-MM-DD 再传参；\n"
    "3. 询问退改签、儿童票、行李、报销等规则时，调用 search_policy，回答必须注明 doc_id 出处；\n"
    "4. 下单前必须先 lock_seat 拿到 lock_id，不可跳过；\n"
    "5. 余票为 0 时只能推荐候补监控，不得声称有票；\n"
    "6. 不得查询或泄露其他用户的订单信息；\n"
    "7. 不知道就说不知道，不要编造车次号或政策。\n"
    "8. 明确切换高铁/机票时重置不兼容席别；未指定方式、日期或路线时沿用已知上下文，含糊时澄清。\n"
    "9. kind=高铁只用二等座/一等座/商务座；kind=机票只用经济舱/公务舱。\n"
    "10. 区分有班次但售罄、有余票、无匹配班次；未查询其他席别时只能建议查询，不得断言有票。\n"
    "11. pay_order 返回 duplicate_pay=true 时明确告知订单已支付，本次没有重复扣款。\n"
    "12. 锁座后多久支付、未支付订单会否自动取消等属于政策咨询，应 search_policy 并引用。\n"
    "13. 支付、取消、退票必须有明确操作请求；疑问或否定语句不能仅因含关键词而执行写操作。"
)


class Agent:
    def __init__(self, provider=None, system_prompt=SYSTEM_PROMPT, *, engine=None, model=None, tool_names=None, mutations=None):
        self.engine = engine or config.ENGINE
        if config.PROVIDER in ("deepseek","bailian") and self.engine != "langchain":
            raise ValueError("Live Provider 只通过 langchain 引擎接入；请设置 AGENT_ENGINE=langchain")
        if self.engine not in ("legacy", "langchain"):
            raise ValueError("AGENT_ENGINE 只支持 legacy/langchain")
        self.system_prompt = system_prompt
        self.sessions = {}
        self._mutex = RLock()
        self.langchain_engine = None
        from target.fault_injection import from_env, normalize
        self.mutations = from_env() if mutations is None else normalize(mutations)
        self.last_fault_report = None
        self.last_audit_report = None
        if self.engine == "langchain":
            # 延迟导入：原 V2 环境不安装 LangChain 也能继续运行。
            from target.langchain_agent import LangChainAgent
            self.langchain_engine = LangChainAgent(system_prompt, provider=provider, model=model, tool_names=tool_names, mutations=self.mutations)
            self.provider = self.langchain_engine.model
        else:
            self.provider = provider or get_provider()
            if self.mutations:
                from target.providers import MockProvider
                if not isinstance(self.provider, MockProvider):
                    raise ValueError("legacy变异只支持Mock；Live请使用LangChain")
                self.provider.mutations = dict(self.mutations)

    def set_mutations(self, mutations):
        from target.fault_injection import normalize
        values = normalize(mutations)
        with self._mutex:
            if values != self.mutations:
                self.reset()  # 不把变异后的工具结果继承到新的正常模式。
            self.mutations = values
            if self.langchain_engine:
                self.langchain_engine.mutations = dict(values)
            else:
                from target.providers import MockProvider
                if not isinstance(self.provider, MockProvider):
                    raise ValueError("legacy变异只支持Mock")
                self.provider.mutations = dict(values)
            self.last_fault_report = None
            self.last_audit_report = None

    def _messages(self, session_id):
        if session_id not in self.sessions:
            self.sessions[session_id] = [{"role": "system", "content": self.system_prompt +
                f"\n当前北京时间日期 {config.today().isoformat()}；数据仅为虚构模拟，当前身份为本人。"}]
        return self.sessions[session_id]

    @recorded_run
    def chat(self, session_id, message, save_trace=True):
        if not isinstance(session_id, str) or not session_id.strip() or not isinstance(message, str) or not message.strip():
            raise ValueError("session_id 与 message 必须是非空字符串")
        with self._mutex:
            if self.langchain_engine is not None:
                try:
                    return self.langchain_engine.chat(session_id, message, save_trace=save_trace)
                finally:
                    self.last_fault_report = self.langchain_engine.last_fault_report
                    self.last_audit_report = self.langchain_engine.last_audit_report
            from target.fault_injection import FaultRun, ACTIVE_LEGACY_RUN
            run = FaultRun(getattr(self.provider,"mutations",{}),session_id,"legacy_mock")
            token = ACTIVE_LEGACY_RUN.set(run)
            try:
                return self._chat(session_id, message, save_trace)
            finally:
                ACTIVE_LEGACY_RUN.reset(token)

    @recorded_run
    def resume_operation(self, session_id, proposal, approved, *, save_trace=True):
        if not self.langchain_engine:
            raise ValueError("当前引擎不支持确认操作")
        if type(approved) is not bool:
            raise ValueError("确认决定必须为布尔值")
        with self._mutex:
            try:
                return self.langchain_engine.chat(session_id, "确认模拟操作" if approved else "取消模拟操作",
                    save_trace=save_trace, resume_decision={"approved": approved, "proposal": proposal})
            finally:
                self.last_fault_report = self.langchain_engine.last_fault_report
                self.last_audit_report = self.langchain_engine.last_audit_report

    def _chat(self, session_id, message, save_trace):
        messages = self._messages(session_id)
        trace = Trace(session_id, message)
        from target.fault_injection import ACTIVE_LEGACY_RUN
        run=ACTIVE_LEGACY_RUN.get()
        trace.trace_id=run.run_id
        trace.provider = getattr(self.provider, "name", config.PROVIDER)
        from target.run_events import bind, emit
        bind(trace)
        messages.append({"role": "user", "content": message})

        reply = "抱歉，我没能完成这次操作。"
        legacy_error = None
        for step in range(config.MAX_STEPS):
            event_start=len(run.events)
            try:
                emit('model_start',system_prompt=messages[0].get('content'))
                for prior in messages:
                    if prior.get('role')=='tool':
                        evidence={}
                        if prior.get('name')=='search_policy':
                            try:
                                payload=json.loads(prior.get('content',''))
                                if isinstance(payload,dict) and isinstance(payload.get('hits'),list):evidence['documents']=payload['hits']
                            except (TypeError,ValueError):pass
                        emit('tool_result_in_model_request',call_id=prior.get('tool_call_id'),tool=prior.get('name'),**evidence)
                model_started=time.perf_counter()
                msg = self.provider.chat(messages, tools.TOOLS)
                emit('model_end',tool_calls=msg.get('tool_calls') if isinstance(msg,dict) else None,
                     reply=msg.get('content') if isinstance(msg,dict) else None,
                     duration_ms=int((time.perf_counter()-model_started)*1000),
                     token_usage=getattr(self.provider,'last_usage',None),execution_mode='mock' if trace.provider=='mock' else 'provider_configured')
                if not isinstance(msg, dict) or msg.get("role") != "assistant":
                    raise ValueError("模型响应格式不正确")
                calls = msg.get("tool_calls") or []
                if not isinstance(calls, list) or any(not isinstance(c, dict) or
                    not all(k in c for k in ("name", "arguments", "id")) for c in calls):
                    raise ValueError("工具调用格式不正确")
            except Exception as exc:
                emit('model_error','failed',error=type(exc).__name__)
                reply = f"模型调用未完成 ({type(exc).__name__})，请检查配置或重试。"
                messages.append({"role": "assistant", "content": reply, "tool_calls": []})
                # The historic contract permits only stop/max_steps_exceeded.
                # Record the exception separately so stop is never treated as success.
                trace.finish(reply, "stop")
                legacy_error={"category":"legacy_provider_error","type":type(exc).__name__,"phase":"model"}
                break
            usage = getattr(self.provider, "last_usage", {})
            for call in calls:emit('model_tool_proposed',tool=call['name'],args=call['arguments'],call_id=call['id'])
            for key in trace.tokens:
                trace.tokens[key] += usage.get(key, 0)
            messages.append(msg)
            run.model_requests.append({"model_step":step+1,"source":"legacy_provider",
                "tool_calls":[{"id":c["id"],"name":c["name"],"args":c["arguments"]} for c in calls],
                "final_text":msg.get("content") if not calls else None})
            for event in run.events[event_start:]:
                event["related_step"]=step+1
                relevant=calls or [c for m in run.model_requests[:-1] for c in m["tool_calls"]][-1:]
                if relevant:event["call_id"]=relevant[0]["id"]

            if not msg.get("tool_calls"):
                reply = msg.get("content") or reply
                trace.finish(reply, "stop")
                break

            for call in msg["tool_calls"]:
                name, args = call["name"], call["arguments"]
                execution_diagnostic={}
                token=tools.DISPATCH_OBSERVER.set(execution_diagnostic.update)
                try:
                    from target.rag_service import scope
                    with scope(trace_id=trace.trace_id,session_id=trace.session_id,call_id=call['id'],provider=trace.provider):
                        result, ok, latency = tools.dispatch(name, args)
                finally:
                    tools.DISPATCH_OBSERVER.reset(token)
                import copy
                original_result=copy.deepcopy(result)
                if ok and run.config.get("hallucinated_train"):
                    result=run.result(name,result,call["id"])
                trace.record_call(step, name, args, result, ok, latency)
                from target.fault_injection import ACTIVE_LEGACY_RUN
                run = ACTIVE_LEGACY_RUN.get()
                if run:
                    run.executions.append({"tool":name,"args":copy.deepcopy(args),"result":copy.deepcopy(result),"original_result":original_result,
                        "ok":ok,"call_id":call["id"],"executed":execution_diagnostic.get("backend_executed"),
                        "parameter_validation":execution_diagnostic.get("validation",{"status":"unknown"}),"step":step+1})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": name,                                   # 供 mock 与统计使用
                    "content": json.dumps(result, ensure_ascii=False),
                })
                emit('tool_message_created',tool=name,call_id=call['id'])
        else:
            reply = "达到最大执行步数，操作尚未完成；请查看工具轨迹。"
            messages.append({"role": "assistant", "content": reply, "tool_calls": []})
            trace.abort(reply, "max_steps_exceeded")

        out = trace.to_dict()
        from target.diagnostics import make_audit
        self.last_audit_report=make_audit(trace,run,save=save_trace,public_trace=out,error=legacy_error,contract_returned=True)
        from target.fault_injection import ACTIVE_LEGACY_RUN
        run = ACTIVE_LEGACY_RUN.get()
        self.last_fault_report = run.save(trace,error=legacy_error) if run and run.config and save_trace else (
            run.report(finish_reason=trace.finish_reason,error=legacy_error) if run and run.config else None)
        if save_trace:
            trace.save(record=out)
        return out

    def reset(self, session_id=None):
        if self.langchain_engine is not None:
            with self._mutex:
                self.langchain_engine.reset(session_id)
            return
        if session_id:
            self.sessions.pop(session_id, None)
        else:
            self.sessions.clear()


def chat(session_id, message):
    """模块级便捷入口，成员 B/C 直接调这个即可。"""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Agent()
    return _DEFAULT.chat(session_id, message)


_DEFAULT = None
