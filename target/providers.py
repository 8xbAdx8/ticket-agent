# -*- coding: utf-8 -*-
"""模型提供者：同一接口，两种实现。

  MockProvider   —— 零依赖离线，按剧本返回 tool_call，第一天就能跑通全链路、录屏、验证测试脚本
  OpenAIProvider —— 真实模型（任何 OpenAI 兼容端点），拿到 key 后改 config 即可切换

成员 A 拿到 key 后需要做的唯一一件事：设置环境变量 AGENT_PROVIDER=openai
"""
import json
import uuid
import re
from datetime import date, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

CITIES = ["北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "西安", "长沙", "厦门"]
SEATS = ["二等座", "一等座", "商务座", "经济舱", "公务舱"]
POLICY_WORDS = ["退票", "改签", "手续费", "儿童票", "行李", "报销", "学生票", "候补", "实名", "规则", "政策", "怎么算"]
ACTION_WORDS = ["抢", "买", "订", "下单", "购", "来一张", "要一张"]

# 变异开关：成员 B 做变异测试时打开，用来验证测试集能否抓到缺陷
MUTATIONS = {}


def set_mutation(name, value=True):
    MUTATIONS[name] = value


def clear_mutations():
    MUTATIONS.clear()


def _parse_date(text):
    today = date.today()
    if "今天" in text:
        d = today
    elif "明天" in text:
        d = today + timedelta(days=1)
    elif "后天" in text:
        d = today + timedelta(days=2)
    else:
        m = re.search(r"(\d{1,2})月(\d{1,2})[日号]", text)
        if m:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
        else:
            m = re.search(r"(\d+)\s*天后", text)
            d = today + timedelta(days=int(m.group(1))) if m else today + timedelta(days=1)
    if MUTATIONS.get("date_offset"):
        d = d + timedelta(days=int(MUTATIONS["date_offset"]))
    return d.isoformat()


def _extract(text, words):
    for w in words:
        if w in text:
            return w
    return None


def _called(messages):
    """按调用顺序返回历史里已经调用过的工具名。"""
    return [m.get("name") for m in messages if m.get("role") == "tool" and m.get("name")]


def _last_tool_result(messages, name):
    for m in reversed(messages):
        if m.get("role") == "tool" and m.get("name") == name:
            try:
                return json.loads(m.get("content", "{}"))
            except Exception:
                return {}
    return {}


class MockProvider:
    """按剧本扮演大模型：把自然语言翻译成 tool_call。

    能力边界：只能处理预设意图，测不出真实模型的幻觉。
    用途是跑通工程、离线演示、以及给成员 B 提供可注入缺陷的被测对象。
    """

    def __init__(self):
        self.name = "mock"

    def chat(self, messages, tools):
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break
        history = _called(messages)
        last = history[-1] if history else None
        is_action = any(w in user_msg for w in ACTION_WORDS)
        is_policy_act = any(k in user_msg for k in ["退了", "退掉", "帮我退", "取消订单"])
        is_policy_q = any(w in user_msg for w in POLICY_WORDS) and not is_policy_act

        # 0) 死循环缺陷注入：持续监控不退出（用于验证 R6 能否捕获）
        if last == "monitor_seat" and MUTATIONS.get("infinite_loop"):
            prev = _last_tool_result(messages, "monitor_seat")
            return _as_msg(None, [("monitor_seat", {
                "train_no": prev.get("train_no", "G101"),
                "date": prev.get("date", _parse_date(user_msg)),
                "seat_type": prev.get("seat_type", "二等座"),
                "duration_min": 30})])

        # 1) 工具已执行完，本轮只做总结
        if last in ("search_policy", "pay_order", "cancel_order", "query_order"):
            return _as_msg(self._summarize(last, messages), [])

        # 2) 订单已创建：看用户下一步是支付还是退票
        if last == "create_order":
            order = _last_tool_result(messages, "create_order")
            if any(w in user_msg for w in ["支付", "付款", "付钱"]):
                return _as_msg(None, [("pay_order", {"order_id": order.get("order_id", ""),
                                                     "pay_type": "alipay"})])
            if is_policy_act:
                return _as_msg(None, [("cancel_order", {"order_id": order.get("order_id", ""),
                                                        "reason": "行程有变"})])
            return _as_msg(self._summarize("create_order", messages), [])

        # 3) 查过票且用户要买：有票才锁座，无票只能候补
        if last == "query_tickets" and is_action:
            trains = [t for t in _last_tool_result(messages, "query_tickets").get("trains", [])
                      if t.get("seats_left", 0) > 0]
            if trains and not MUTATIONS.get("skip_lock"):
                t = trains[0]
                return _as_msg(None, [("lock_seat", {
                    "train_no": t.get("train_no"), "date": t.get("date"),
                    "seat_type": t.get("seat_type"), "passengers": ["张三"]})])
            if MUTATIONS.get("infinite_loop") or not trains:
                return _as_msg(None, [("monitor_seat", {
                    "train_no": "G101", "date": _parse_date(user_msg),
                    "seat_type": "二等座", "duration_min": 30})])
            return _as_msg(self._summarize("no_seat", messages), [])

        # 4) 已锁座：下单（可注入"跳过锁座"缺陷，直接给不存在的 lock_id）
        if last == "lock_seat":
            lock = _last_tool_result(messages, "lock_seat")
            return _as_msg(None, [("create_order", {
                "lock_id": lock.get("lock_id", ""),
                "passenger_ids": lock.get("passengers", ["张三"]),
                "contact": config.CURRENT_USER_PHONE})])

        # 5) 纯查询：总结车次
        if last == "query_tickets":
            return _as_msg(self._summarize("query_tickets", messages), [])

        # 6) 规则类问题走 RAG（可注入"路由错误"缺陷）
        if is_policy_q:
            if MUTATIONS.get("route_error"):
                return _as_msg(None, [("query_tickets", {
                    "from_city": _extract(user_msg, CITIES) or "北京",
                    "to_city": "上海", "date": _parse_date(user_msg)})])
            return _as_msg(None, [("search_policy", {"question": user_msg})])

        # 7) 查询订单
        if "订单" in user_msg and any(w in user_msg for w in ["查", "看", "我的", "有没有"]):
            phone = config.OTHER_USER_PHONE if MUTATIONS.get("ask_other_user") else config.CURRENT_USER_PHONE
            return _as_msg(None, [("query_order", {"phone": phone})])

        # 8) 默认：查票（可注入"重复调用"与"日期偏移"缺陷）
        cities = [c for c in CITIES if c in user_msg]
        args = {"from_city": cities[0] if cities else "北京",
                "to_city": cities[1] if len(cities) > 1 else "上海",
                "date": _parse_date(user_msg),
                "seat_type": _extract(user_msg, SEATS) or "二等座"}
        calls = [("query_tickets", args)]
        if MUTATIONS.get("repeat_call"):
            calls.append(("query_tickets", args))
        return _as_msg(None, calls)

    # ---------- 生成最终回复 ----------
    def _summarize(self, kind, messages):
        r = _last_tool_result(messages, kind if kind != "no_seat" else "monitor_seat")
        if r.get("error"):
            return f"操作未完成：{r['error']}。"
        if kind == "search_policy":
            hits = r.get("hits", [])
            if not hits:
                return "知识库中没有相关政策，我不便作答。（未检索到依据）"
            body = " ".join(h["content"] for h in hits[:2])
            cite = "" if MUTATIONS.get("no_citation") else "（依据 " + ", ".join(h["doc_id"] for h in hits[:2]) + "）"
            return f"{body}{cite}"
        if kind == "query_tickets":
            trains = r.get("trains", [])[:3]
            if not trains:
                return f"抱歉，{r.get('date','')} 没有查到符合条件的车次。"
            lines = [f"{t['train_no']} {t['from_city']}→{t['to_city']} {t['depart']} 开，"
                     f"{t['seat_type']} ¥{t['price']}，余票 {t['seats_left']}" for t in trains]
            return "为您查到以下车次：" + "；".join(lines) + "。"
        if kind == "no_seat":
            return "该车次当前无票，我已为您开启余票监控（候补）。" if r.get("task_id") else "该车次当前无票。"
        if kind == "create_order":
            return (f"订单已创建：{r.get('order_id','')}，金额 ¥{r.get('amount','')}，"
                    f"车次 {r.get('train_no','')} {r.get('date','')}，请在锁座有效期内完成支付。")
        if kind == "pay_order":
            return f"支付成功，订单 {r.get('order_id','')} 已完成，祝您旅途愉快。"
        if kind == "cancel_order":
            return (f"退票成功，订单 {r.get('order_id','')}，手续费 ¥{r.get('fee','')}"
                    f"（{r.get('fee_rate','')}），退款 ¥{r.get('refund','')}。依据政策 {r.get('policy_ref','P01')}。")
        if kind == "query_order":
            orders = r.get("orders", [])
            if not orders:
                return "您当前没有订单。"
            return "您的订单：" + "；".join(
                f"{o['order_id']} {o['train_no']} {o['date']} ¥{o['amount']} {o['status']}" for o in orders[:5])
        return "好的。"


class OpenAIProvider:
    """真实模型：任何 OpenAI 兼容端点（智谱 GLM-Flash / DeepSeek / 通义 / 硅基流动）。"""

    def __init__(self):
        from openai import OpenAI            # 延迟导入，mock 模式不需要装
        self.client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)
        self.name = "openai"

    def chat(self, messages, tools):
        resp = self.client.chat.completions.create(
            model=config.MODEL_NAME, messages=_to_api(messages), tools=tools, tool_choice="auto"
        )
        msg = resp.choices[0].message
        calls = []
        if msg.tool_calls:
            for c in msg.tool_calls:
                calls.append((c.function.name, json.loads(c.function.arguments or "{}")))
        return _as_msg(msg.content, calls)


def _as_msg(content, calls):
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [{"id": "call_" + uuid.uuid4().hex[:8], "name": n, "arguments": a}
                       for n, a in calls],
    }


def _to_api(messages):
    """内部格式 -> OpenAI API 格式。"""
    out = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            out.append({
                "role": "assistant",
                "content": m.get("content") or "",
                "tool_calls": [{"id": c["id"], "type": "function",
                                "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                               for c in m["tool_calls"]],
            })
        elif m.get("role") == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id", ""),
                        "content": m.get("content", "")})
        else:
            out.append({"role": m["role"], "content": m.get("content", "")})
    return out


def get_provider():
    return OpenAIProvider() if config.PROVIDER == "openai" else MockProvider()
