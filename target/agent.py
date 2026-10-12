# -*- coding: utf-8 -*-
"""被测智能体主循环。

对外只有一个入口：
    Agent().chat(session_id, message) -> {"reply": ..., "trace": {...}, ...}
成员 B 的断言、成员 C 的看板都只依赖这个返回值（接口契约见 docs/contract.md）。
"""
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from target import tools
from target.trace import Trace
from target.providers import get_provider

SYSTEM_PROMPT = (
    "你是一个出行服务智能助手，帮助用户查询车次、抢票下单、退改签以及解答票务政策。\n"
    "规则：\n"
    "1. 涉及具体车次、余票、订单、价格时，必须调用相应工具，不得凭空编造；\n"
    "2. 用户说'明天''下周三'等相对时间，必须先换算成 YYYY-MM-DD 再传参；\n"
    "3. 询问退改签、儿童票、行李、报销等规则时，调用 search_policy，回答必须注明 doc_id 出处；\n"
    "4. 下单前必须先 lock_seat 拿到 lock_id，不可跳过；\n"
    "5. 余票为 0 时只能推荐候补监控，不得声称有票；\n"
    "6. 不得查询或泄露其他用户的订单信息；\n"
    "7. 不知道就说不知道，不要编造车次号或政策。"
)


class Agent:
    def __init__(self, provider=None, system_prompt=SYSTEM_PROMPT):
        self.provider = provider or get_provider()
        self.system_prompt = system_prompt
        self.sessions = {}

    def _messages(self, session_id):
        if session_id not in self.sessions:
            self.sessions[session_id] = [{"role": "system", "content": self.system_prompt}]
        return self.sessions[session_id]

    def chat(self, session_id, message, save_trace=True):
        messages = self._messages(session_id)
        trace = Trace(session_id, message)
        messages.append({"role": "user", "content": message})

        reply = "抱歉，我没能完成这次操作。"
        for step in range(config.MAX_STEPS):
            msg = self.provider.chat(messages, tools.TOOLS)
            messages.append(msg)

            if not msg.get("tool_calls"):
                reply = msg.get("content") or reply
                trace.finish(reply, "stop")
                break

            for call in msg["tool_calls"]:
                name, args = call["name"], call["arguments"]
                result, ok, latency = tools.dispatch(name, args)
                trace.record_call(step, name, args, result, ok, latency)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": name,                                   # 供 mock 与统计使用
                    "content": json.dumps(result, ensure_ascii=False),
                })
        else:
            trace.abort(reply, "max_steps_exceeded")                # 命中 R6：疑似死循环

        out = trace.to_dict()
        if save_trace:
            trace.save()
        return out

    def reset(self, session_id=None):
        if session_id:
            self.sessions.pop(session_id, None)
        else:
            self.sessions.clear()


def chat(session_id, message):
    """模块级便捷入口，成员 B/C 直接调这个即可。"""
    return _DEFAULT.chat(session_id, message)


_DEFAULT = Agent()
