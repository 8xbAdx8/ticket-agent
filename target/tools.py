# -*- coding: utf-8 -*-
"""工具定义（OpenAI function calling schema）与分发执行。

成员 A 职责：schema 的 description 写得越清楚，模型调用越准，
同时也是成员 B 做"参数是否符合规范"判定的依据。
"""
import json
import time
import copy
from contextvars import ContextVar
import urllib.request
from datetime import date

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from target import mock_core, rag
DISPATCH_OBSERVER = ContextVar("ticket_dispatch_observer",default=None)

# ---------------- 工具 Schema ----------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_tickets",
            "description": "查询指定出发地、到达地、日期的车次与余票数量。date 必须是 YYYY-MM-DD 格式，"
                           "当用户说'下周三''明天'等相对时间时必须先换算成具体日期。",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_city": {"type": "string", "description": "出发城市，如 北京"},
                    "to_city": {"type": "string", "description": "到达城市，如 上海"},
                    "date": {"type": "string", "description": "乘车日期，YYYY-MM-DD"},
                    "seat_type": {"type": "string", "description": "席别，可选",
                                  "enum": ["二等座", "一等座", "商务座", "经济舱", "公务舱"]},
                    "kind": {"type": "string", "description": "交通方式，可选", "enum": ["高铁", "机票"]},
                },
                "required": ["from_city", "to_city", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "monitor_seat",
            "description": "当目标车次无余票时创建模拟候补记录并返回模拟任务 ID；不会在后台持续监控，也不会发送通知。",
            "parameters": {
                "type": "object",
                "properties": {
                    "train_no": {"type": "string", "description": "车次号，如 G101"},
                    "date": {"type": "string", "description": "乘车日期，YYYY-MM-DD"},
                    "seat_type": {"type": "string", "description": "席别"},
                    "duration_min": {"type": "integer", "description": "监控时长（分钟），默认 30"},
                },
                "required": ["train_no", "date", "seat_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lock_seat",
            "description": "锁定座位，占住库存并返回有时效的 lock_id。下单前必须先调用本工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "train_no": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "seat_type": {"type": "string"},
                    "passengers": {"type": "array", "items": {"type": "string"},
                                   "description": "乘客姓名列表"},
                },
                "required": ["train_no", "date", "seat_type", "passengers"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": "凭有效的 lock_id 创建订单。同一 lock_id 重复调用只会生成一个订单（幂等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lock_id": {"type": "string"},
                    "passenger_ids": {"type": "array", "items": {"type": "string"},
                                      "description": "乘客姓名列表"},
                    "contact": {"type": "string", "description": "联系手机号"},
                },
                "required": ["lock_id", "passenger_ids", "contact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pay_order",
            "description": "支付订单。仅修改订单状态，不涉及任何真实支付渠道。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "pay_type": {"type": "string", "enum": ["alipay", "wechat", "card"], "description": "支付方式"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "退票。手续费按知识库政策 P01 的阶梯规则计算并引用出处。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "reason": {"type": "string", "description": "退票原因，可选"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_order",
            "description": "查询订单。不传 phone 时只返回当前登录用户的订单；"
                           "不得返回其他用户的订单信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号，可选"},
                    "phone": {"type": "string", "description": "手机号，仅可查询本人，可选"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": "检索退改签、儿童票、行李、报销凭证等政策知识库。"
                           "当用户询问规则类问题而非购票操作时使用本工具，回答必须带 doc_id 出处。",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string", "description": "用户的问题原文"}},
                "required": ["question"],
            },
        },
    },
]

TOOL_NAMES = [t["function"]["name"] for t in TOOLS]


# ---------------- 分发执行 ----------------

def _call_http(name, args):
    req = urllib.request.Request(
        f"{config.MOCK_API_URL}/tool/{name}",
        data=json.dumps({"args": args}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _call_local(name, args):
    if name == "search_policy":
        return rag.search_policy(args.get("question", ""))
    fn = getattr(mock_core, name, None)
    if fn is None:
        return {"error": f"未知工具 {name}"}
    return fn(**args)


def validate(name, args):
    """零依赖 schema 校验，HTTP 与本地共用同一入口。"""
    if name not in TOOL_NAMES:
        raise ValueError("未知工具")
    schema = next(t["function"]["parameters"] for t in TOOLS if t["function"]["name"] == name)
    if not isinstance(args, dict):
        raise ValueError("参数必须是 JSON object")
    if set(args) - set(schema["properties"]):
        raise ValueError("存在未定义参数")
    for key in schema.get("required", []):
        if key not in args:
            raise ValueError(f"缺少必填参数 {key}")
    for key, value in args.items():
        prop = schema["properties"][key]
        kind = prop["type"]
        if kind == "string" and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{key} 必须是非空字符串")
        if kind == "integer" and (type(value) is not int or value <= 0 or value > 1440):
            raise ValueError(f"{key} 必须是 1..1440 的整数")
        if kind == "array" and (not isinstance(value, list) or not value or
                                any(not isinstance(x, str) or not x.strip() for x in value) or
                                len(set(value)) != len(value)):
            raise ValueError(f"{key} 必须是非空、不重复的字符串数组")
        if "enum" in prop and value not in prop["enum"]:
            raise ValueError(f"{key} 不在允许值内")
    if "date" in args:
        parsed = date.fromisoformat(args["date"])
        if parsed.isoformat() != args["date"]:
            raise ValueError("date 必须为 YYYY-MM-DD")
    if name == "query_tickets" and args.get("kind") and args.get("seat_type"):
        allowed = {"高铁": ("二等座", "一等座", "商务座"), "机票": ("经济舱", "公务舱")}
        if args["seat_type"] not in allowed[args["kind"]]:
            raise ValueError("seat_type 与 kind 不兼容")


for _tool in TOOLS:
    _tool["function"]["parameters"]["additionalProperties"] = False


def dispatch(name, args):
    """真正执行工具的地方。返回 (result, ok, latency_ms)。"""
    t0 = time.perf_counter()
    diagnostic = {"validation":{"status":"unknown"},"backend_executed":False}
    from target.run_events import emit
    emit('tool_proposed',tool=name,args=args)
    try:
        validate(name, args)
        emit('parameter_validation','passed',tool=name)
        diagnostic["validation"]={"status":"valid","validated_args":copy.deepcopy(args)}
        diagnostic["backend_executed"]=True
        emit('tool_start',tool=name,args=args)
        result = _call_http(name, args) if config.USE_HTTP_MOCK else _call_local(name, args)
        ok = not (isinstance(result, dict) and "error" in result)
    except Exception as e:
        if diagnostic["validation"]["status"] == "unknown":
            diagnostic["validation"]={"status":"invalid","reason":type(e).__name__}
        # 参数错误可以说明；其他异常不回显外部响应、密钥或本机路径。
        result = {"error": str(e) if isinstance(e, ValueError) else f"工具执行失败 ({type(e).__name__})"}
        ok = False
    duration=int((time.perf_counter()-t0)*1000)
    emit('tool_result','succeeded' if ok else 'failed' if diagnostic['backend_executed'] else 'blocked',
         tool=name,executed=diagnostic['backend_executed'],output=result,duration_ms=duration)
    if name=='search_policy' and ok:
        emit('rag_result',documents=result.get('hits',[]) if isinstance(result,dict) else [])
    observer=DISPATCH_OBSERVER.get()
    if observer is not None:
        observer(diagnostic)
    return result, ok, int((time.perf_counter() - t0) * 1000)
