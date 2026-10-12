# -*- coding: utf-8 -*-
"""FastAPI 外壳：把 mock_core 的纯 Python 函数包装成 HTTP 服务。

用途：视频演示时看起来更像真实系统；成员 B 也可单独对接口做压测。
默认不启用（config.USE_HTTP_MOCK=False 时工具直接调函数，零部署）。

启动： uvicorn target.mock_api:app --port 8000
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict

from target import mock_core, tools

app = FastAPI(title="模拟出行票务服务（虚构数据）")


class ToolCall(BaseModel):
    args: Dict[str, Any] = {}


@app.get("/health")
def health():
    return {"status": "ok", "tools": mock_core.list_tools()}


@app.post("/tool/{name}")
def call_tool(name: str, body: ToolCall):
    try:
        tools.validate(name, body.args)
        return tools._call_local(name, body.args)
    except Exception as e:
        return {"error": str(e) if isinstance(e, ValueError) else f"工具执行失败 ({type(e).__name__})"}


@app.get("/inventory")
def inventory(from_city: str = None, to_city: str = None, date: str = None):
    if not all((from_city, to_city, date)):
        return {"error": "from_city,to_city,date 必填"}
    return call_tool("query_tickets", ToolCall(args={"from_city": from_city, "to_city": to_city, "date": date}))
