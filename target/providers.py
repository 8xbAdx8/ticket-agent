# -*- coding: utf-8 -*-
"""模型提供者：同一接口，两种实现。

  MockProvider   —— 零依赖离线，按剧本返回 tool_call，第一天就能跑通全链路、录屏、验证测试脚本
  OpenAIProvider —— 真实模型（任何 OpenAI 兼容端点），拿到 key 后改 config 即可切换

真实模式必须配置 provider、key、base URL 与端点支持的 model；各端点兼容性待实测。
"""
import json
import uuid
import re
from datetime import date, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

CITIES = ["北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "西安", "长沙", "厦门",
          "重庆", "福州", "合肥", "天津", "济南", "郑州", "南昌", "南宁", "贵阳", "昆明"]
SEATS = ["二等座", "一等座", "商务座", "经济舱", "公务舱"]
KIND_SEATS = {"高铁": ("二等座", "一等座", "商务座"), "机票": ("经济舱", "公务舱")}
POLICY_WORDS = ["退票", "改签", "手续费", "儿童票", "行李", "报销", "学生票", "候补", "实名", "规则", "政策", "怎么算"]
ACTION_WORDS = ["抢", "买", "订", "下单", "购", "来一张", "要一张"]

# 变异开关：成员 B 做变异测试时打开，用来验证测试集能否抓到缺陷
MUTATIONS = {}
from target.fault_injection import LEGACY_MUTATION_NAMES as MUTATION_NAMES, legacy_event


def set_mutation(name, value=True):
    if name not in MUTATION_NAMES:
        raise ValueError("未知变异开关")
    MUTATIONS[name] = value


def clear_mutations():
    MUTATIONS.clear()


def _parse_date(text, mutations=None):
    today = config.today()
    explicit = re.search(r"\d{4}-\d{2}-\d{2}", text)
    weekday = re.search(r"(下周|本周|这周|周|星期)([一二三四五六日天])", text)
    if explicit:
        d = date.fromisoformat(explicit.group())
    elif weekday:
        wd = "一二三四五六日".index(weekday[2].replace("天", "日"))
        d = today - timedelta(days=today.weekday()) + timedelta(days=wd)
        if weekday[1] == "下周":
            d += timedelta(days=7)
        elif weekday[1] in ("周", "星期") and d < today:
            d += timedelta(days=7)
    elif "今天" in text:
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
    mutations = MUTATIONS if mutations is None else mutations
    if mutations.get("date_offset"):
        original = d.isoformat()
        d = d + timedelta(days=int(mutations["date_offset"]))
        legacy_event("date_offset",original,d.isoformat(),stage="legacy_date_parser")
    return d.isoformat()


def _extract(text, words):
    for w in words:
        if w in text:
            return w
    return None


def _seat_for_kind(kind, explicit, inherited):
    """显式席别不兼容时澄清；隐式旧席别不兼容时重置默认值。"""
    allowed = KIND_SEATS[kind]
    if explicit:
        return explicit if explicit in allowed else None
    return inherited if inherited in allowed else allowed[0]


def _transport_kind(text, inherited):
    """显式选择优先；省略方式则继承；多选/目标不明则返回 None 要求澄清。"""
    clean, negated = re.subn(r"(?:不要|别|不坐|不选|不查|不考虑)\s*(?:高铁|动车|火车|车票|机票|飞机|航班)", "", text)
    rail = any(w in clean for w in ("高铁", "动车", "火车", "列车", "车票"))
    flight = any(w in clean for w in ("机票", "飞机", "航班"))
    if rail and flight:
        return None
    if rail:
        return "高铁"
    if flight:
        return "机票"
    if negated or any(w in clean for w in ("换个交通方式", "换一种交通方式", "换种交通方式", "换个方式", "换一种出行方式", "另一种交通方式", "换个吧")):
        return None
    return inherited if inherited in KIND_SEATS else "高铁"


def _write_intents(text):
    """Mock 的保守操作识别：关键词出现不等于授权写操作。"""
    command = text.strip().rstrip("。！! ")
    command = re.sub(r"^(?:请)?(?:麻烦)?(?:帮我|替我)?(?:现在|立即|马上)?", "", command)
    question = bool(re.search(r"多久|多长|何时|什么时候|有效期|预售期|是否|会.*吗|可以.*吗|怎么|如何|为什么|多少|规则|政策|截止|自动|[？?]", text))
    negative = bool(re.search(r"(?:不要|别|不|暂不|先不)\s*(?:支付|付款|付钱|取消|退票|退掉)", text))
    if question or negative:
        return False, False
    pay = bool(re.fullmatch(r"(?:支付|付款|付钱)(?:[^\n]*?(?:订单|OD[A-Za-z0-9_]+))?", command))
    pay = pay or bool(re.search(r"(?:并且|并|然后|再|顺便)(?:请|帮我)?(?:支付|付款|付钱)", command))
    cancel = bool(re.fullmatch(r"(?:取消(?:订单)?|退掉|退了|退票|退)(?:[^\n]*?(?:订单|OD[A-Za-z0-9_]+))?", command))
    return pay, cancel


def _policy_question(text, pay, cancel):
    if pay or cancel:
        return False
    if any(w in text for w in POLICY_WORDS):
        return True
    domain = any(w in text for w in ("支付", "付款", "锁座", "订单", "取消", "有效期", "预售期"))
    question = bool(re.search(r"多久|多长|何时|什么时候|有效期|预售期|是否|会.*吗|可以.*吗|怎么|如何|为什么|多少|截止|自动|[？?]", text))
    return domain and question


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

    def __init__(self, mutations=None):
        self.name = "mock"
        self.mutations = MUTATIONS if mutations is None else mutations
        self.last_usage = {"prompt": 0, "completion": 0}

    def chat(self, messages, tools):
        index = max(i for i, m in enumerate(messages) if m.get("role") == "user")
        user_msg = messages[index].get("content", "")
        history = _called(messages[index + 1:])
        last = history[-1] if history else None
        mut = self.mutations
        is_action = any(w in user_msg for w in ACTION_WORDS) and "订单" not in user_msg
        is_pay_act, is_policy_act = _write_intents(user_msg)
        is_policy_q = _policy_question(user_msg, is_pay_act, is_policy_act)

        if last and _last_tool_result(messages, last).get("error"):
            return _as_msg(self._summarize(last, messages), [])

        # 0) 死循环缺陷注入：持续监控不退出（用于验证 R6 能否捕获）
        if last == "monitor_seat" and mut.get("infinite_loop"):
            legacy_event("infinite_loop","stop after monitor_seat","monitor_seat again",stage="legacy_decision")
            prev = _last_tool_result(messages, "monitor_seat")
            return _as_msg(None, [("monitor_seat", {
                "train_no": prev.get("train_no", "G101"),
                "date": prev.get("date", _parse_date(user_msg, mut)),
                "seat_type": prev.get("seat_type", "二等座"),
                "duration_min": 30})])
        if last == "monitor_seat":
            return _as_msg(self._summarize("no_seat", messages), [])

        # 1) 工具已执行完，本轮只做总结
        if last in ("search_policy", "pay_order", "cancel_order", "query_order"):
            return _as_msg(self._summarize(last, messages), [])

        # 2) 订单已创建：看用户下一步是支付还是退票
        if last == "create_order":
            order = _last_tool_result(messages, "create_order")
            if is_pay_act:
                return _as_msg(None, [("pay_order", {"order_id": order.get("order_id", ""),
                                                     "pay_type": "alipay"})])
            if is_policy_act:
                return _as_msg(None, [("cancel_order", {"order_id": order.get("order_id", ""),
                                                        "reason": "行程有变"})])
            return _as_msg(self._summarize("create_order", messages), [])

        # 3) 查过票且用户要买：有票才锁座，无票只能候补
        if last == "query_tickets" and is_action:
            if _last_tool_result(messages,'query_tickets').get('data_source',{}).get('mode') in ('snapshot','live'):
                return _as_msg('该查询来源仅供查看。请先切回固定演示数据并重新查询，演示操作不会真实锁座、出票或扣款。',[])
            trains = [t for t in _last_tool_result(messages, "query_tickets").get("trains", [])
                      if t.get("seats_left", 0) > 0]
            if trains and mut.get("skip_lock"):
                legacy_event("skip_lock","lock_seat","create_order with LK_INJECTED_MISSING",stage="legacy_decision")
                return _as_msg(None, [("create_order", {"lock_id": "LK_INJECTED_MISSING", "passenger_ids": ["张三"], "contact": config.CURRENT_USER_PHONE})])
            if trains:
                t = trains[0]
                names = re.search(r"乘客[：:]?\s*([\u4e00-\u9fff、,， ]+)", user_msg)
                passengers = re.split(r"[、,， ]+", names[1].strip()) if names else ["张三"]
                return _as_msg(None, [("lock_seat", {
                    "train_no": t.get("train_no"), "date": t.get("date"),
                    "seat_type": t.get("seat_type"), "passengers": passengers})])
            all_trains = _last_tool_result(messages, "query_tickets").get("trains", [])
            if all_trains:
                t = all_trains[0]
                return _as_msg(None, [("monitor_seat", {
                    "train_no": t["train_no"], "date": t["date"],
                    "seat_type": t["seat_type"], "duration_min": 30})])
            return _as_msg("未查到该日期与路线的班次；请确认日期在模拟预售范围内，无法锁座或候补。", [])

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
            if mut.get("route_error"):
                legacy_event("route_error","search_policy","query_tickets",stage="legacy_decision")
                return _as_msg(None, [("query_tickets", {
                    "from_city": _extract(user_msg, CITIES) or "北京",
                    "to_city": "上海", "date": _parse_date(user_msg, mut)})])
            return _as_msg(None, [("search_policy", {"question": user_msg})])

        if any(w in user_msg for w in ["他人", "上一个用户", "别人的"]):
            return _as_msg("不能查询或泄露其他用户订单。", [])

        # 7) 查询订单
        if "订单" in user_msg and not (is_pay_act or is_policy_act) and any(w in user_msg for w in ["查", "看", "我的", "有没有"]):
            phone_match = re.search(r"1\d{10}", user_msg)
            phone = phone_match.group() if phone_match else config.CURRENT_USER_PHONE
            return _as_msg(None, [("query_order", {"phone": phone})])

        # 新一轮使用历史数据作为上下文，但不能把旧工具当作本轮已执行。
        order_match = re.search(r"OD[a-zA-Z0-9_]+", user_msg)
        previous_order = _last_tool_result(messages[:index], "create_order")
        if is_policy_act or (is_pay_act and not is_action):
            order_id = order_match.group() if order_match else previous_order.get("order_id")
            if not order_id:
                return _as_msg("请提供自己的订单号，或先查询并创建订单。", [])
            return _as_msg(None, [("cancel_order" if is_policy_act else "pay_order", {"order_id": order_id})])
        if not is_action and any(w in user_msg for w in ("支付", "付款", "付钱", "取消", "退掉")):
            return _as_msg("请确认是咨询政策还是执行订单操作；执行支付或取消需要明确的操作请求。", [])
        # 8) 默认：查票（可注入"重复调用"与"日期偏移"缺陷）
        cities = sorted([c for c in CITIES if c in user_msg], key=user_msg.index)
        previous_query = next((m["tool_calls"][0]["arguments"] for m in reversed(messages[:index])
                               if m.get("tool_calls") and m["tool_calls"][0]["name"] == "query_tickets"), {})
        if len(cities) < 2 and not previous_query:
            return _as_msg("请说明出发地、目的地和日期，例如：帮我查明天上海到杭州的高铁。", [])
        args = dict(previous_query)
        if len(cities) > 2:
            return _as_msg("请确认唯一的出发地和目的地。", [])
        if len(cities) == 2:
            args.update(from_city=cities[0], to_city=cities[1])
        elif len(cities) == 1:
            city = cities[0]
            if re.search(r"(?:从|出发地.*|起点.*)" + re.escape(city), user_msg) or city + "出发" in user_msg:
                args["from_city"] = city
            elif re.search(r"(?:到|去|目的地.*|终点.*)" + re.escape(city), user_msg):
                args["to_city"] = city
            else:
                return _as_msg(f"请确认{city}是出发地还是目的地。", [])
        has_date = re.search(r"今天|明天|后天|周|星期|\d+\s*天后|\d+月|\d{4}-", user_msg)
        if has_date or "date" not in args:
            args["date"] = _parse_date(user_msg, mut)
        kind = _transport_kind(user_msg, args.get("kind"))
        if kind is None:
            return _as_msg("请明确选择高铁还是机票，我会保留已知路线和日期。", [])
        args["kind"] = kind
        seat = _seat_for_kind(kind, _extract(user_msg, SEATS), args.get("seat_type"))
        if seat is None:
            return _as_msg(f"{kind}可选{'、'.join(KIND_SEATS[kind])}，请确认席别。", [])
        args["seat_type"] = seat
        calls = [("query_tickets", args)]
        if mut.get("repeat_call"):
            calls.append(("query_tickets", args))
            legacy_event("repeat_call",1,2,stage="legacy_decision")
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
            cite = "" if self.mutations.get("no_citation") else "（依据 " + ", ".join(h["doc_id"] for h in hits[:2]) + "）"
            if self.mutations.get("no_citation"):
                legacy_event("no_citation",[h["doc_id"] for h in hits[:2]],[],stage="legacy_reply")
            return f"{body}{cite}"
        if kind == "query_tickets":
            if r.get('data_source'):
                from target.train_source import summary
                return summary(r)
            trains = r.get("trains", [])
            if not trains:
                return "没有符合条件的车次或航班；请确认路线、日期和席别，或换席别查询。空结果不能用于判断库存是否耗尽。"
            available = [t for t in trains if t.get("seats_left", 0) > 0]
            sold_out = [t for t in trains if t.get("seats_left", 0) <= 0]
            if not available:
                seat = trains[0]["seat_type"]
                mode = trains[0]["kind"]
                alternatives = [s for s in KIND_SEATS[mode] if s != seat]
                suggestion = f"也可查询{'、'.join(alternatives)}的余票；其他席别尚未查询，不能保证有票。" if alternatives else ""
                return f"查询到符合条件的班次，但{seat}已售罄（余票 0，不可售），可以考虑候补。{suggestion}"
            lines = [f"{t['train_no']} {t['from_city']}→{t['to_city']} {t['depart']} 开，"
                     f"{t['seat_type']} ¥{t['price']}，余票 {t['seats_left']}" for t in available[:3]]
            note = f"另有 {len(sold_out)} 个返回班次当前余票 0（不可售）。" if sold_out else ""
            return "为您查到以下有余票的班次：" + "；".join(lines) + "。" + note
        if kind == "no_seat":
            return "该车次当前无票，我已为您开启余票监控（候补）。" if r.get("task_id") else "该车次当前无票。"
        if kind == "create_order":
            return (f"订单已创建：{r.get('order_id','')}，金额 ¥{r.get('amount','')}，"
                    f"车次 {r.get('train_no','')} {r.get('date','')}，请在锁座有效期内完成支付。")
        if kind == "pay_order":
            if r.get("duplicate_pay"):
                return f"订单已支付，本次没有重复扣款。订单 {r.get('order_id','')}。"
            return f"支付成功，订单 {r.get('order_id','')} 已完成，祝您旅途愉快。"
        if kind == "cancel_order":
            if r.get("status") == "cancelled":
                return f"未支付订单 {r.get('order_id')} 已取消，未收取手续费。依据 P12。"
            return (f"退票成功，订单 {r.get('order_id','')}，手续费 ¥{r.get('fee','')}"
                    f"（{r.get('fee_rate','')}），退款 ¥{r.get('refund','')}。依据政策 {r.get('policy_ref','P01')}。")
        if kind == "query_order":
            orders = r.get("orders", [r] if r.get("order_id") else [])
            if not orders:
                return "您当前没有订单。"
            return "您的订单：" + "；".join(
                f"{o['order_id']} {o['train_no']} {o['date']} ¥{o['amount']} {o['status']}" for o in orders[:5])
        return "好的。"


class OpenAIProvider:
    """OpenAI 风格 Chat Completions 适配器；第三方端点兼容性需分别实测。"""

    def __init__(self):
        if not config.API_KEY:
            raise ValueError("真实模型需要 AGENT_API_KEY；离线运行请设置 AGENT_PROVIDER=mock")
        from openai import OpenAI            # 延迟导入，mock 模式不需要装
        from target.model_network import client as model_client
        # Never let the SDK silently inherit a dead Windows/env proxy.
        self.client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL,
                             timeout=30, max_retries=0,
                             http_client=model_client(timeout=30))
        self.name = "openai"
        self.last_usage = {"prompt": 0, "completion": 0}

    def chat(self, messages, tools):
        resp = self.client.chat.completions.create(
            model=config.MODEL_NAME, messages=_to_api(messages), tools=tools, tool_choice="auto"
        )
        self.last_finish_reason = getattr(resp.choices[0],"finish_reason",None)
        msg = resp.choices[0].message
        usage = resp.usage
        self.last_usage = {"prompt": usage.prompt_tokens if usage else 0, "completion": usage.completion_tokens if usage else 0}
        calls = []
        if msg.tool_calls:
            for c in msg.tool_calls:
                try:
                    args = json.loads(c.function.arguments or "{}")
                except (ValueError, TypeError):
                    args = c.function.arguments  # dispatch 返回参数错误，供模型下一轮纠正
                calls.append({"id": c.id, "name": c.function.name, "arguments": args})
        return {"role": "assistant", "content": msg.content, "tool_calls": calls}


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
                                "function": {"name": c["name"], "arguments": c["arguments"] if isinstance(c["arguments"], str) else json.dumps(c["arguments"], ensure_ascii=False)}}
                               for c in m["tool_calls"]],
            })
        elif m.get("role") == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id", ""),
                        "content": m.get("content", "")})
        else:
            out.append({"role": m["role"], "content": m.get("content", "")})
    return out


def get_provider():
    if config.PROVIDER not in ("openai", "mock"):
        raise ValueError("AGENT_PROVIDER 只支持 mock/openai")
    return OpenAIProvider() if config.PROVIDER == "openai" else MockProvider()
