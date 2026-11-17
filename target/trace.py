# -*- coding: utf-8 -*-
"""trace 记录：这是整个项目的接口契约核心，成员 B/C 都依赖这里的字段。"""
import json
import time
import uuid
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


class Trace:
    """一次完整对话的执行记录。

    落盘为 JSONL，每行一个 session 的完整 trace，字段见 docs/contract.md。
    """

    def __init__(self, session_id=None, user_msg=""):
        self.trace_id = uuid.uuid4().hex  # 仅旁证使用，不加入原公开十字段。
        self.session_id = session_id or ("S" + uuid.uuid4().hex[:8])
        self.user_msg = user_msg
        self.steps = []
        self.reply = None
        self.finish_reason = None
        self.started_at = time.perf_counter()
        self.total_latency_ms = None
        self.tokens = {"prompt": 0, "completion": 0}
        self.provider = config.PROVIDER
        self.model = config.MODEL_NAME

    def _step(self, index):
        while len(self.steps) <= index:
            self.steps.append({"step": len(self.steps) + 1, "calls": []})
        return self.steps[index]

    def record_call(self, step_index, name, args, result, ok, latency_ms):
        s = self._step(step_index)
        s["calls"].append({
            "tool": name,
            "args": args,
            "ok": ok,
            "latency_ms": latency_ms,
            "result_preview": _preview(result),
        })

    def finish(self, reply, reason="stop"):
        self.reply = reply
        self.finish_reason = reason
        self.total_latency_ms = int((time.perf_counter() - self.started_at) * 1000)
        return self

    def abort(self, reply, reason="max_steps_exceeded"):
        return self.finish(reply, reason)

    @property
    def tool_names(self):
        return [c["tool"] for s in self.steps for c in s["calls"]]

    def to_dict(self):
        from target.diagnostics import redact_credentials
        return redact_credentials({
            "session_id": self.session_id,
            "provider": self.provider,
            "model": self.model,
            "user_msg": self.user_msg,
            "steps": self.steps,
            "tool_sequence": self.tool_names,
            "reply": self.reply,
            "finish_reason": self.finish_reason,
            "tokens": self.tokens,
            "total_latency_ms": self.total_latency_ms if self.total_latency_ms is not None else int((time.perf_counter() - self.started_at) * 1000),
        })

    def save(self, path=None, record=None):
        path = Path(path or (config.TRACE_DIR / "traces.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        from target.diagnostics import redact_credentials
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(redact_credentials(record if record is not None else self.to_dict()), ensure_ascii=False) + "\n")
        return path


def _preview(obj, limit=200):
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return s[:limit] + ("..." if len(s) > limit else "")
