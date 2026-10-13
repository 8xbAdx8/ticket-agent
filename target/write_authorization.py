"""LangChain 模式的保守业务授权检查；独立于模型 Prompt 和 Mock 决策。

只支持明确中文操作命令；含糊表达先拒绝并请用户重述。不改变底层票务状态机。
"""
import json
import re

WRITE_TOOLS = {"monitor_seat", "lock_seat", "create_order", "pay_order", "cancel_order"}
QUESTION = r"多久|多长|何时|什么时候|是否|能否|可以.*吗|怎么|如何|为什么|多少|规则|政策|截止|自动|[？?]"
PURCHASE = r"^(?:我(?:要|想)|给[^，。；;\n]{1,16}?|选[^。；;\n]{1,40}?(?:给[^，。；;\n]{1,16}?)?)?(?:订票|订一张|订明天|订后天|订今天|订高铁|订机票|订购|购买|买|抢|下单|购票|来一张|要一张)"


def permissions(message: str) -> set[str]:
    if re.search(QUESTION, message) or re.search(r"假设|如果|举例|引用|他说|她说|别人说|不要执行|别执行|只咨询|仅咨询|[“”\"「」]",message):
        return set()
    command = re.sub(r"^(?:请)?(?:麻烦)?(?:帮我|替我)?(?:现在|立即|马上)?", "", message.strip().rstrip("。！! "))
    granted = set()
    for name, positive, negative in (
        ("create_order", PURCHASE, r"(?:不要|别|不|暂不|先不)\s*(?:买|订|抢|下单|购|创建订单)"),
        ("lock_seat", r"锁座|锁定座位", r"(?:不要|别|不|暂不|先不)\s*(?:锁座|锁定)"),
        ("monitor_seat", r"候补|监控余票|订阅余票", r"(?:不要|别|不|暂不|先不)\s*(?:候补|监控|订阅)"),
        ("pay_order", r"^(?:支付|付款|付钱)(?:[^\n]*?(?:订单|OD[A-Za-z0-9_]+))?$|(?:并且|并|然后|再|顺便)(?:请|帮我)?(?:支付|付款|付钱)", r"(?:不要|别|不|暂不|先不)\s*(?:支付|付款|付钱)"),
        ("cancel_order", r"^(?:取消(?:订单)?|退掉|退了|退票|退)(?:[^\n]*?(?:订单|OD[A-Za-z0-9_]+))?$", r"(?:不要|别|不|暂不|先不)\s*(?:取消|退票|退掉|退)"),
    ):
        if re.search(positive, command) and not re.search(negative, message):
            granted.add(name)
    if "create_order" in granted:
        # 订票授权包含一次锁座；没有票时允许模拟候补。不包含支付。
        granted.update({"lock_seat", "monitor_seat"})
    if re.search(r"(?:不要|别|不|暂不|先不)\s*(?:锁座|锁定)", message):
        granted.discard("lock_seat")
    if re.search(r"(?:不要|别|不|暂不|先不)\s*(?:候补|监控|订阅)", message):
        granted.discard("monitor_seat")
    return granted


def order_reference(message: str, messages) -> set[str]:
    explicit = set(re.findall(r"OD[A-Za-z0-9_]+", message))
    if explicit:
        return explicit
    # 只沿用最近一次真实工具结果中的订单，不能让模型自行挑选数据库订单。
    for item in reversed(messages):
        if getattr(item, "type", None) != "tool":
            continue
        try:
            result = json.loads(item.content)
        except (ValueError, TypeError):
            continue
        if not isinstance(result, dict) or result.get("error"):
            continue
        if result.get("order_id"):
            return {result["order_id"]}
        if "orders" in result:
            orders = result["orders"]
            return {orders[0]["order_id"]} if len(orders) == 1 else set()
    return set()


def denial(name, args, context, messages) -> str | None:
    if name not in WRITE_TOOLS:
        return None
    if name not in permissions(context.user_message):
        return "当前消息未明确授权该操作，请明确说明订票、支付、退票或候补请求。"
    if name == "lock_seat" and context.lock_ids:
        return "本轮已成功锁座，不重复占用库存；请先检查已返回的锁座结果。"
    if name == "create_order" and args.get("lock_id") not in context.lock_ids:
        return "本轮没有该 lock_id 的成功锁座记录，请先锁座再创建订单。"
    if name in {"pay_order", "cancel_order"} and args.get("order_id") not in order_reference(context.user_message, messages):
        return "无法确认该订单是用户指定或最近工具结果中的订单，请明确提供本人订单号。"
    return None
