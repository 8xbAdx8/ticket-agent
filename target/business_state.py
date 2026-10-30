"""Business-state detection and deterministic action follow-ups.

State comes ONLY from tool results actually executed in this run. Nothing here
calls a model, reads the database, or infers an order/lock/payment status from
prose. Suggestions therefore cannot claim an operation succeeded when it did not.
"""
from datetime import datetime, timezone

# Order matters for display only; detection walks the run backwards.
ACTION_RULES = {
    'locked': (
        {'question': '确认创建订单', 'action': 'create_order', 'requires_confirm': True},
        {'question': '暂不创建订单', 'action': 'decline', 'requires_confirm': False},
        {'question': '查看锁座剩余有效时间', 'action': 'query', 'requires_confirm': False},
    ),
    'lock_expired': (
        {'question': '重新查询余票', 'action': 'query', 'requires_confirm': False},
        {'question': '重新锁座（需要再次确认）', 'action': 'lock_seat', 'requires_confirm': True},
    ),
    'order_pending': (
        {'question': '使用支付宝支付', 'action': 'pay_alipay', 'requires_confirm': True},
        {'question': '使用微信支付', 'action': 'pay_wechat', 'requires_confirm': True},
        {'question': '查看订单详情', 'action': 'query', 'requires_confirm': False},
        {'question': '查询支付截止时间', 'action': 'query', 'requires_confirm': False},
    ),
    'paid': (
        {'question': '查看订单详情', 'action': 'query', 'requires_confirm': False},
        {'question': '查询退票规则', 'action': 'query', 'requires_confirm': False},
        {'question': '查询改签规则', 'action': 'query', 'requires_confirm': False},
    ),
    'payment_failed': (
        {'question': '重新发起支付（需要再次确认）', 'action': 'pay_retry', 'requires_confirm': True},
        {'question': '查看订单详情', 'action': 'query', 'requires_confirm': False},
        {'question': '取消订单（未支付不收费）', 'action': 'cancel', 'requires_confirm': True},
    ),
    'cancelled': (
        {'question': '重新查询余票', 'action': 'query', 'requires_confirm': False},
        {'question': '查询退票规则', 'action': 'query', 'requires_confirm': False},
    ),
}

# Actions that must never appear once the state moved past them.
FORBIDDEN = {
    'paid': {'create_order', 'pay_alipay', 'pay_wechat', 'pay_retry'},
    'order_pending': {'create_order', 'lock_seat'},
    'lock_expired': {'create_order'},
    'payment_failed': {'create_order'},
    'cancelled': {'create_order', 'pay_alipay', 'pay_wechat', 'pay_retry'},
}


def _parse(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def detect(events=(), now=None):
    """Return the business state produced by this run's real tool results."""
    now = now or datetime.now(timezone.utc)
    rows = [e for e in events
            if e.get('event_type') == 'tool_result' and e.get('executed') is True
            and isinstance(e.get('output'), dict)]
    for event in reversed(rows):
        tool, output = event.get('tool'), event['output']
        if tool == 'pay_order':
            if output.get('status') == 'paid':
                return _state('paid', event, order_id=output.get('order_id'),
                              pay_type=output.get('pay_type'), amount=output.get('amount'),
                              duplicate=bool(output.get('duplicate_pay')))
            if output.get('error'):
                return _state('payment_failed', event, error=str(output['error']))
            return None
        if tool == 'create_order':
            if output.get('order_id') and output.get('status') == 'pending':
                return _state('order_pending', event, order_id=output['order_id'],
                              amount=output.get('amount'), lock_id=output.get('lock_id'))
            return None
        if tool == 'cancel_order':
            if output.get('status') in ('cancelled', 'refunded'):
                return _state('cancelled', event, order_id=output.get('order_id'),
                              status=output.get('status'))
            return None
        if tool == 'lock_seat':
            if not output.get('lock_id'):
                return None
            expires = _parse(output.get('expire_at'))
            expired = bool(expires and expires <= now)
            remaining = int((expires - now).total_seconds()) if expires else None
            return _state('lock_expired' if expired else 'locked', event,
                          lock_id=output['lock_id'], train_no=output.get('train_no'),
                          expire_at=output.get('expire_at'), remaining_seconds=remaining)
    return None


def actions(state):
    """Deterministic action follow-ups for a state, with invalid ones removed."""
    if not state:
        return []
    name = state.get('state')
    banned = FORBIDDEN.get(name, set())
    return [dict(item, kind='action', state=name)
            for item in ACTION_RULES.get(name, ())
            if item.get('action') not in banned]


def _state(name, event, **fields):
    return {'state': name, 'tool': event.get('tool'),
            'event_id': event.get('event_id'), 'run_id': event.get('run_id'), **fields}
