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
        ("lock_seat", r"锁座|锁定(?:座位|二等座|一等座|商务座|经济舱|公务舱)", r"(?:不要|别|不|暂不|先不)\s*(?:锁座|锁定)"),
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


def multiturn_selection(message, human_history):
    """Recover explicit user selections since the latest purchase intent.

    Assistant output never supplies authorization or passenger details.
    Ambiguous, quoted, negative and hypothetical messages cannot select values.
    """
    if not isinstance(message, str) or re.search(QUESTION + r'|不要|别|不想|取消|假设|如果|举例|[“”"「」]', message):
        return None
    history = list(human_history)[-12:]
    if history and history[-1] == message:
        history.pop()
    turns = history + [message]
    selection = {}
    saw_current_selection = False
    for index, text in enumerate(reversed(turns)):
        if not isinstance(text, str):
            return None
        if re.search(r'不要|别|不想|不需要|不再|暂不|先不|不买|不订|取消|放弃|停止|算了', text):
            return None
        safe = not re.search(QUESTION + r'|假设|如果|举例|[“”"「」]', text)
        if safe:
            trains = re.findall(r'(?<![A-Za-z0-9])(?:[GDCZTKYS]\d{1,6}|[A-Z]{2}\d{3,6})(?![A-Za-z0-9])', text)
            seats = re.findall(r'二等座|一等座|商务座|经济舱|公务舱', text)
            passengers = re.findall(r'乘客(?:姓名)?[：:\s]*([\u4e00-\u9fff]{2,8})(?=[，,。！!\s]|$)', text)
            for key, values in (('train_no', trains), ('seat_type', seats), ('passengers', passengers)):
                if len(values) > 1 and key not in selection:
                    return None
                if values and key not in selection:
                    selection[key] = [values[0]] if key == 'passengers' else values[0]
                if index == 0 and values:
                    saw_current_selection = True
        # "自动下单" is a command, not a question about automatic behavior.
        auto_order = bool(re.fullmatch(r'(?:请|帮我)?自动(?:下单|订票|买票)[。！!\s]*', text.strip()))
        if 'create_order' in permissions(text) or auto_order:
            return selection if saw_current_selection and len(selection) == 3 else None
    return None


def selection_lock_authorized(message, messages, args):
    human = [getattr(m, 'content', '') for m in messages if getattr(m, 'type', None) == 'human']
    selection = multiturn_selection(message, human)
    if not selection or any(args.get(k) != v for k, v in selection.items()):
        return False
    # Require actual matching tool evidence; the backend checks inventory again.
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


def reuse_lock_command(message):
    """A concrete command to use the prior lock; not an implicit purchase/payment."""
    if re.search(QUESTION + r'|不要|别|暂不|先不|假设|如果|举例|[“”"「」]', message):
        return False
    return bool(re.fullmatch(r'(?:请|帮我)?(?:确认(?:订票|下单)[：:,，]\s*)?'
        r'(?:用|使用)(?:刚才|刚|之前)?锁(?:定|好)?的座(?:位)?(?:创建订单|下单)[^。；;\n]*[。！!\s]*', message.strip()))


def privacy_denial(name, args, message=''):
    """Read-only ownership preflight, before Python business tools or confirmation.

    An exact proposal approval does not grant access to another account. Unknown
    IDs still go through the existing backend ownership/state checks.
    """
    if name not in {'query_order', 'pay_order', 'cancel_order', 'create_order'}:
        return None
    import config
    if name == 'query_order':
        if args.get('phone') and args['phone'] != config.CURRENT_USER_PHONE:
            return '不可查询其他用户订单'
        phones = re.findall(r'(?<!\d)1\d{10}(?!\d)', message)
        if (any(p != config.CURRENT_USER_PHONE for p in phones) or
            re.search(r'他人|别人的|别人(?:订单|的订单)|其他用户|上一个用户', message)):
            return '不可查询其他用户订单'
    if name == 'create_order' and args.get('contact') and args['contact'] != config.CURRENT_USER_PHONE:
        return '不可使用其他用户身份创建订单'
    order_id = args.get('order_id')
    if order_id and name in {'query_order', 'pay_order', 'cancel_order'}:
        import sqlite3
        from contextlib import closing
        try:
            with closing(sqlite3.connect(config.DB_PATH.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as conn:
                row = conn.execute('SELECT phone FROM orders WHERE order_id=?',(order_id,)).fetchone()
            if row and row[0] != config.CURRENT_USER_PHONE:
                return '不可查询其他用户订单' if name == 'query_order' else '不可修改其他用户订单'
        except (sqlite3.Error, OSError):
            pass  # No ownership inference; the backend remains authoritative.
    return None



def pending_confirmation(message, prompt):
    """Interpret a short confirmation only for a single explicit preceding question."""
    if not isinstance(message, str) or not re.fullmatch(r'(?:确认|确定|同意|好的|可以)[。！!\s]*', message.strip()):
        return None
    if not isinstance(prompt, str) or not re.search(r'(?:是否|请确认|确认(?:一下)?|可以吗|[？?])', prompt):
        return None
    if re.search(r'不要|不可|无法|不可以|不能|未(?:能|成功)|失败|假设|如果', prompt):
        return None
    actions = set()
    if re.search(r'(?:是否|确认|同意|要不要|现在|进行|请)(?:为您|帮您|模拟)?(?:锁座|锁定座位)', prompt): actions.add('lock_seat')
    if re.search(r'创建(?:模拟)?订单|(?:确认|是否|要不要|现在|进行)(?:模拟)?下单', prompt): actions.add('create_order')
    if re.search(r'支付|付款|付钱', prompt): actions.add('pay_order')
    if re.search(r'取消订单|退票', prompt): actions.add('cancel_order')
    return next(iter(actions)) if len(actions) == 1 else None


def confirmed_action(name, args, message, messages):
    """Bind confirmation to the latest assistant question and known tool evidence."""
    prior = list(messages)
    if prior and getattr(prior[-1], 'type', None) == 'human' and getattr(prior[-1], 'content', None) == message:
        prior.pop()
    if not prior or getattr(prior[-1], 'type', None) != 'ai':
        return False
    prompt = getattr(prior[-1], 'content', '')
    if pending_confirmation(message, prompt) != name:
        return False
    if name == 'lock_seat':
        # Never trust the assistant to invent a user's selection or passenger.
        human = [getattr(item, 'content', '') for item in prior if getattr(item, 'type', None) == 'human']
        if not human or not selection_lock_authorized(human[-1], prior, args):
            return False
        trains = re.findall(r'(?<![A-Za-z0-9])(?:[GDCZTKYS]\d{1,6}|[A-Z]{2}\d{3,6})(?![A-Za-z0-9])', prompt)
        seats = re.findall(r'二等座|一等座|商务座|经济舱|公务舱', prompt)
        passengers = re.findall(r'乘客(?:姓名)?[：:\s]*([\u4e00-\u9fff]{2,8})(?=[，,。！!？?\s]|$)', prompt)
        dates = re.findall(r'\d{4}-\d{2}-\d{2}', prompt)
        return (trains == [args.get('train_no')] and seats == [args.get('seat_type')]
                and passengers == args.get('passengers') and dates == [args.get('date')])
    if name == 'create_order':
        return (isinstance(args.get('lock_id'), str) and args['lock_id'] in prompt
                and recent_lock_reference(prior, args))
    if name in {'pay_order', 'cancel_order'}:
        order_id = args.get('order_id')
        return (isinstance(order_id, str) and order_id in prompt
                and order_id in order_reference('', prior))
    return False

def denial(name, args, context, messages) -> str | None:
    if name not in WRITE_TOOLS:
        return None
    selection_lock = name == 'lock_seat' and selection_lock_authorized(context.user_message, messages, args)
    contextual = confirmed_action(name, args, context.user_message, messages)
    confirm_order = contextual and name == 'create_order' or (name == 'create_order' and
                     (reuse_lock_command(context.user_message) or
                      bool(re.fullmatch(r'(?:请)?确认(?:创建)?(?:模拟)?订单|(?:请)?确认下单', context.user_message.strip().rstrip('。！! ')))))
    if name not in permissions(context.user_message) and not selection_lock and not confirm_order and not contextual:
        return "当前消息未明确授权该操作，请明确说明订票、支付、退票或候补请求。"
    if name == "lock_seat" and context.lock_ids:
        return "本轮已成功锁座，不重复占用库存；请先检查已返回的锁座结果。"
    if name == "create_order" and args.get("lock_id") not in context.lock_ids and not (confirm_order and recent_lock_reference(messages, args)):
        return "本轮没有该 lock_id 的成功锁座记录，请先锁座再创建订单。"
    if name in {"pay_order", "cancel_order"} and args.get("order_id") not in order_reference(context.user_message, messages):
        return "无法确认该订单是用户指定或最近工具结果中的订单，请明确提供本人订单号。"
    return None
