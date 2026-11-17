"""Explicit local confirmation, using the original atomic payment business layer.

No public HTTP endpoint, scanner callback, token or model request. Database path
comes from the server-side Conversation, never from QR data or a client field.
"""
from target import mock_core
from target.payment_qr import yuan


def confirm(database, order_id, amount, pay_type, *, confirmed=False):
    if confirmed is not True:
        raise ValueError('请先确认本次演示支付')
    if pay_type not in ('alipay', 'wechat'):
        raise ValueError('请选择支付宝或微信演示支付')
    expected = yuan(amount)
    with mock_core.database_scope(database):
        return mock_core.pay_order(order_id, pay_type, expected_amount=expected)
