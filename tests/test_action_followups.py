"""Action follow-ups must match the business state produced by real tool results."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from target import business_state, followups
from target.run_events import bind, capture, emit
from target.trace import Trace

SID = 'web-action-test'
NOW = datetime.now(timezone.utc)


def tool_event(tool, output, *, executed=True, run_id='run-1', event_id=None):
    return {'event_type': 'tool_result', 'tool': tool, 'executed': executed,
            'output': output, 'run_id': run_id, 'event_id': event_id or tool + '-evt'}


def lock_result(expired=False):
    expire = (NOW - timedelta(minutes=1)) if expired else (NOW + timedelta(minutes=14))
    return {'lock_id': 'LK12345678', 'train_no': 'G7303', 'date': '2026-10-31',
            'seat_type': '二等座', 'unit_price': 73.0, 'count': 1,
            'expire_at': expire.isoformat(), 'ttl_seconds': 900}


def order_result(status='pending'):
    return {'order_id': 'OD1234567890', 'phone': '13800000000', 'train_no': 'G7303',
            'date': '2026-10-31', 'seat_type': '二等座', 'amount': 73.0,
            'status': status, 'lock_id': 'LK12345678', 'idempotent_hit': False}


PAID = {'order_id': 'OD1', 'status': 'paid', 'pay_type': 'alipay', 'amount': 73.0, 'duplicate_pay': False}


class DetectionTests(unittest.TestCase):
    def test_lock_states(self):
        self.assertEqual('locked', business_state.detect([tool_event('lock_seat', lock_result())])['state'])
        self.assertEqual('lock_expired',
                         business_state.detect([tool_event('lock_seat', lock_result(expired=True))])['state'])

    def test_order_and_payment_states(self):
        self.assertEqual('order_pending', business_state.detect([tool_event('create_order', order_result())])['state'])
        self.assertEqual('paid', business_state.detect([tool_event('pay_order', PAID)])['state'])
        self.assertEqual('payment_failed',
                         business_state.detect([tool_event('pay_order', {'error': '渠道异常'})])['state'])

    def test_latest_result_wins(self):
        events = [tool_event('lock_seat', lock_result(), event_id='e1'),
                  tool_event('create_order', order_result(), event_id='e2'),
                  tool_event('pay_order', PAID, event_id='e3')]
        state = business_state.detect(events)
        self.assertEqual('paid', state['state'])
        self.assertEqual('e3', state['event_id'])

    def test_unexecuted_result_is_ignored(self):
        self.assertIsNone(business_state.detect([tool_event('lock_seat', lock_result(), executed=False)]))


class ActionRuleTests(unittest.TestCase):
    def test_paid_never_offers_payment(self):
        actions = business_state.actions({'state': 'paid'})
        self.assertFalse([a for a in actions if a['action'] in ('pay_alipay', 'pay_wechat', 'pay_retry')])

    def test_expired_lock_never_offers_create_order(self):
        actions = business_state.actions({'state': 'lock_expired'})
        self.assertNotIn('create_order', [a['action'] for a in actions])

    def test_pending_order_offers_two_channels_with_confirmation(self):
        actions = {a['question']: a for a in business_state.actions({'state': 'order_pending'})}
        self.assertIn('使用支付宝支付', actions)
        self.assertIn('使用微信支付', actions)
        self.assertTrue(actions['使用支付宝支付']['requires_confirm'])

    def test_paid_keeps_after_sale_only(self):
        self.assertEqual(['查看订单详情', '查询退票规则', '查询改签规则'],
                         [a['question'] for a in business_state.actions({'state': 'paid'})])


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.path = self.directory / 'run_events.jsonl'

    def round(self, question, events):
        trace = Trace(SID, question)
        trace.finish('已处理。')
        run_id = trace.trace_id
        with capture(self.path):
            bind(trace)
            for event in events:
                emit('tool_result', event.pop('status', 'succeeded'), **event)
            self.last_trace = trace.to_dict()
            return followups.generate_and_save(self.last_trace, {'trace_id': run_id}, self.directory,
                                               asked=[], authorized=False)

    def test_lock_success_offers_confirm_create(self):
        row = self.round('帮我锁座', [{'tool': 'lock_seat', 'executed': True, 'output': lock_result()}])
        self.assertEqual('action', row['followup_type'])
        self.assertEqual('locked', row['business_state'])
        self.assertEqual(['确认创建订单', '暂不创建订单', '查看锁座剩余有效时间'], row['suggestions'])
        self.assertEqual('action_rule', row['generation_source'])
        self.assertEqual(0, row['model_invocations'])

    def test_lock_expired_has_no_create_order(self):
        row = self.round('帮我锁座', [{'tool': 'lock_seat', 'executed': True,
                                       'output': lock_result(expired=True)}])
        self.assertEqual('lock_expired', row['business_state'])
        self.assertNotIn('确认创建订单', row['suggestions'])
        self.assertTrue(row['suggestions'])

    def test_order_created_offers_payment_choices(self):
        row = self.round('创建订单', [{'tool': 'create_order', 'executed': True, 'output': order_result()}])
        self.assertEqual('order_pending', row['business_state'])
        for text in ('使用支付宝支付', '使用微信支付', '查看订单详情', '查询支付截止时间'):
            self.assertIn(text, row['suggestions'])
        self.assertNotIn('确认创建订单', row['suggestions'])

    def test_paid_hides_payment_and_keeps_after_sale(self):
        row = self.round('支付', [{'tool': 'pay_order', 'executed': True, 'output': PAID}])
        self.assertEqual('paid', row['business_state'])
        self.assertFalse([q for q in row['suggestions'] if '支付' in q])
        self.assertIn('查看订单详情', row['suggestions'])
        self.assertIn('查询退票规则', row['suggestions'])

    def test_payment_failure_offers_retry(self):
        row = self.round('支付', [{'tool': 'pay_order', 'executed': True, 'output': {'error': '渠道超时'}}])
        self.assertEqual('payment_failed', row['business_state'])
        self.assertTrue(any('重新发起支付' in q for q in row['suggestions']))
        self.assertNotIn('使用支付宝支付', row['suggestions'])

    def test_consecutive_rounds_follow_state(self):
        first = self.round('锁座', [{'tool': 'lock_seat', 'executed': True, 'output': lock_result()}])
        self.assertEqual('locked', first['business_state'])
        second = self.round('创建订单', [{'tool': 'create_order', 'executed': True, 'output': order_result()}])
        self.assertEqual('order_pending', second['business_state'])
        third = self.round('支付', [{'tool': 'pay_order', 'executed': True, 'output': PAID}])
        self.assertEqual('paid', third['business_state'])
        self.assertNotIn('使用支付宝支付', third['suggestions'])

    def test_saved_rows_are_bound_to_session_and_run(self):
        row = self.round('锁座', [{'tool': 'lock_seat', 'executed': True, 'output': lock_result()}])
        other = Path(tempfile.mkdtemp())
        trace = self.last_trace
        self.assertIsNotNone(followups.read_record(self.directory, SID, row['run_id'], trace))
        self.assertIsNone(followups.read_record(other, SID, row['run_id'], trace))
        self.assertIsNone(followups.read_record(self.directory, 'web-other', row['run_id'], trace))


if __name__ == '__main__':
    unittest.main()
