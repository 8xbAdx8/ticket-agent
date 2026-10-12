# -*- coding: utf-8 -*-
"""工具定义（OpenAI function calling schema）与分发执行。

成员 A 职责：schema 的 description 写得越清楚，模型调用越准，
同时也是成员 B 做"参数是否符合规范"判定的依据。
"""
import json
import time
import urllib.request

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from target import mock_core, rag

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
            "description": "当目标车次无余票时，订阅该车次的余票监控（候补），返回监控任务 ID。",
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
        data=json.dumps(args).encode("utf-8"),
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


def dispatch(name, args):
    """真正执行工具的地方。返回 (result, ok, latency_ms)。"""
    t0 = time.time()
    try:
        result = _call_http(name, args) if config.USE_HTTP_MOCK else _call_local(name, args)
        ok = not (isinstance(result, dict) and "error" in result)
    except Exception as e:                       # 超时、注入故障、参数不合法
        result = {"error": f"{type(e).__name__}: {e}"}
        ok = False
    return result, ok, int((time.time() - t0) * 1000)
