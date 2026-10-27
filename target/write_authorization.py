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


def purchase_clarification(message: str) -> str | None:
    """完整工具模式的前置澄清；购买意图不能覆盖明确的锁座否定。"""
    if "create_order" in permissions(message) and re.search(r"(?:不要|别|不|暂不|先不)\s*(?:锁座|锁定)", message):
        return "已了解您的购买意图。当前流程必须先锁座才能下单；本轮未锁座、未下单。您是否同意先锁座？"
    if re.fullmatch(r"(?:请)?(?:不要|别|暂不|先不)(?:买|订票|购票|下单)(?:了|啦)?[。！!\s]*", message.strip()):
        return "已停止本次购买流程，本轮未执行锁座或下单。"
    return None


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


def selection_details(message: str):
    """A bounded selection is not by itself permission to buy or pay."""
    if re.search(QUESTION + r'|不要|别|不想|取消|假设|如果|举例|[“”"「」]', message):
        return None
    trains = re.findall(r'(?<![A-Za-z0-9])(?:[GDCZTKYS]\d{1,6}|[A-Z]{2}\d{3,6})(?![A-Za-z0-9])', message)
    seats = re.findall(r'二等座|一等座|商务座|经济舱|公务舱', message)
    passenger = re.search(r'乘客(?:姓名)?[：:\s]*([\u4e00-\u9fff]{2,8})(?:[，,。！!\s]|$)', message)
    if len(trains) != 1 or len(seats) != 1 or not passenger:
        return None
    return {'train_no': trains[0], 'seat_type': seats[0], 'passengers': [passenger.group(1)]}


def selection_lock_authorized(message, messages, args):
    selection = selection_details(message)
    if not selection or any(args.get(k) != v for k, v in selection.items()):
        return False
    # The model must use an actual prior query result rather than inventing a
    # train or date; backend inventory remains the final authority for stock.
    matching_query = False
    for item in reversed(messages):
        if getattr(item, 'type', None) != 'tool' or getattr(item, 'name', None) != 'query_tickets':
            continue
        try:
            result = json.loads(item.content)
        except (ValueError, TypeError):
            continue
        if not isinstance(result, dict) or not isinstance(result.get('trains'), list):
            continue
        if any(isinstance(row, dict) and row.get('train_no') == selection['train_no']
               and row.get('seat_type') == selection['seat_type'] and row.get('date') == args.get('date')
               for row in result['trains']):
            matching_query = True
            break
    if not matching_query:
        return False
    human = [getattr(m, 'content', '') for m in messages if getattr(m, 'type', None) == 'human']
    if human and human[-1] == message:
        human.pop()
    # A recent explicit user intention is required, and any subsequent user
    # cancellation or refusal invalidates it. Assistant text grants no authority.
    for text in reversed(human[-8:]):
        if not isinstance(text, str):
            return False
        if re.search(r'不要|别|不想|不需要|不再|暂不|先不|不买|不订|取消|放弃|停止|算了', text):
            return False
        if 'create_order' in permissions(text):
            return True
    return False


def recent_lock_reference(messages, args):
    """Only the latest successful real tool result may supply a prior lock."""
    for item in reversed(messages):
        if getattr(item, 'type', None) != 'tool' or getattr(item, 'name', None) != 'lock_seat':
            continue
        try:
            result = json.loads(item.content)
        except (ValueError, TypeError):
            continue
        if isinstance(result, dict) and result.get('lock_id') and not result.get('error'):
            return (args.get('lock_id') == result['lock_id'] and
                    args.get('passenger_ids') == result.get('passengers'))
    return False


def denial(name, args, context, messages) -> str | None:
    if name not in WRITE_TOOLS:
        return None
    selection_lock = name == 'lock_seat' and selection_lock_authorized(context.user_message, messages, args)
    confirm_order = (name == 'create_order' and
                     bool(re.fullmatch(r'(?:请)?确认(?:创建)?(?:模拟)?订单|(?:请)?确认下单', context.user_message.strip().rstrip('。！! '))))
    if name not in permissions(context.user_message) and not selection_lock and not confirm_order:
        return "当前消息未明确授权该操作，请明确说明订票、支付、退票或候补请求。"
    if name == "lock_seat" and context.lock_ids:
        return "本轮已成功锁座，不重复占用库存；请先检查已返回的锁座结果。"
    if name == "create_order" and args.get("lock_id") not in context.lock_ids and not (confirm_order and recent_lock_reference(messages, args)):
        return "本轮没有该 lock_id 的成功锁座记录，请先锁座再创建订单。"
    if name in {"pay_order", "cancel_order"} and args.get("order_id") not in order_reference(context.user_message, messages):
        return "无法确认该订单是用户指定或最近工具结果中的订单，请明确提供本人订单号。"
    return None
