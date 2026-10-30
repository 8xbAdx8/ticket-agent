"""Deterministic turn-intent detection for evidence-bound follow-ups.

No model call, no retrieval. The purpose is only to decide which evidence may
ground the NEXT suggestions, so a policy turn can never inherit stale ticket
rows from an earlier query.
"""
import re

INTENTS = ('ticket_query', 'policy_consult', 'order_query', 'refund_change', 'lock_pay', 'clarify')

# Order matters: the first matching family wins, so the more specific business
# intent is tested before the generic policy/ticket wording.
FAMILIES = (
    ('refund_change', r'退票|退款|退费|改签|改票|误车|错过.{0,4}车|手续费'),
    ('lock_pay', r'锁座|占座|支付|付款|扣款|待支付|多久.{0,6}(?:支付|付款|失效)|有效期'),
    ('order_query', r'订单|我的票|查.{0,3}单|待支付订单|已购'),
    ('policy_consult', r'政策|规定|规则|条款|报销|凭证|发票|儿童|学生|行李|携带品|宠物|能否|可以吗|是否|怎么办|怎么算'),
    ('ticket_query', r'查票|班次|车次|余票|票价|二等座|一等座|商务座|几点|出发|到达|高铁|动车|火车'),
)

POLICY_FAMILIES = ('policy_consult', 'refund_change', 'lock_pay')

# A bare request such as "检索政策" names no category, so the honest next step is
# to clarify instead of guessing.
CATEGORY_HINTS = r'退|改签|儿童|学生|行李|携带|报销|凭证|发票|宠物|锁座|支付|订单|积分|保险'


def _family(question):
    for name, pattern in FAMILIES:
        if re.search(pattern, question):
            return name
    return None


def has_ticket_evidence(events=()):
    for event in events:
        output = event.get('output')
        if (event.get('event_type') == 'tool_result' and event.get('tool') == 'query_tickets'
                and event.get('executed') is True and isinstance(output, dict)
                and isinstance(output.get('trains'), list)):
            return True
    return False


def has_policy_evidence(events=()):
    for event in events:
        if event.get('event_type') == 'rag_result' and event.get('status') in ('succeeded', 'insufficient_evidence'):
            return True
        if event.get('event_type') == 'tool_result' and event.get('tool') == 'search_policy':
            return True
    return False


def has_order_evidence(events=()):
    for event in events:
        if (event.get('event_type') == 'tool_result'
                and event.get('tool') in ('query_order', 'create_order', 'pay_order', 'cancel_order')
                and isinstance(event.get('output'), dict)):
            return True
    return False


def detect_intent(question, reply='', events=()):
    """Return the business intent of THIS turn plus the evidence it actually has.

    `events` must be the current run's events only. Prior runs are deliberately
    not accepted here: that is what made policy turns inherit ticket follow-ups.
    """
    text = str(question or '')
    family = _family(text)
    ticket = has_ticket_evidence(events)
    policy = has_policy_evidence(events)
    order = has_order_evidence(events)
    if family is None:
        # No business wording at all: fall back to what this turn actually did.
        intent = 'ticket_query' if ticket else 'policy_consult' if policy else 'clarify'
        needs_clarification = intent == 'clarify'
    elif family == 'ticket_query':
        intent, needs_clarification = 'ticket_query', False
    elif family in ('refund_change', 'lock_pay'):
        intent, needs_clarification = family, False
    elif family == 'order_query':
        intent, needs_clarification = 'order_query', not order
    else:
        intent = 'policy_consult'
        # "检索政策" names no subject: ask which policy instead of guessing.
        needs_clarification = not re.search(CATEGORY_HINTS, text) and not policy
    basis = [{'family': family, 'matched': bool(family)}]
    if needs_clarification:
        basis.append({'reason': 'no_business_category_in_question'})
    return {'intent': intent, 'needs_clarification': needs_clarification,
            'has_ticket_evidence': ticket, 'has_policy_evidence': policy,
            'has_order_evidence': order, 'basis': basis}


# When the turn has no usable evidence, only clarification questions are allowed.
CLARIFY = {
    'policy_consult': (
        '退票和改签的规则有什么区别？',
        '儿童票和成人票的规则有什么不同？',
        '行李超重怎么收费？',
        '报销凭证怎么开？',
        '锁座后多久必须完成支付？',
    ),
    'clarify': (
        '退票和改签的规则有什么区别？',
        '儿童票和成人票的规则有什么不同？',
        '行李超重怎么收费？',
        '报销凭证怎么开？',
    ),
    'order_query': (
        '这笔订单还能取消吗？',
        '未支付订单会自动释放库存吗？',
    ),
    'lock_pay': (
        '锁座后多久必须完成支付？',
        '重复支付会重复扣款吗？',
    ),
    'refund_change': (
        '退票手续费怎么算？',
        '改签后还能退票吗？',
    ),
    'ticket_query': (
        '这些班次的退改规则一样吗？',
        '儿童票和成人票票价差多少？',
    ),
}
