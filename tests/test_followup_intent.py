"""Intent-aware follow-ups: a policy turn must not inherit ticket rows."""
import json
import tempfile
import unittest
from pathlib import Path

from target import followups
from target.intent import detect_intent
from target.run_events import bind, capture, emit
from target.trace import Trace

TRAINS = [
    {'train_no': 'G7303', 'date': '2026-10-31', 'seat_type': '二等座', 'from_city': '上海',
     'to_city': '杭州', 'depart': '12:34', 'arrive': '13:34', 'price': 73.0, 'seats_left': 51},
    {'train_no': 'G7302', 'date': '2026-10-31', 'seat_type': '二等座', 'from_city': '上海',
     'to_city': '杭州', 'depart': '09:17', 'arrive': '10:17', 'price': 73.0, 'seats_left': 47},
]
DOCS = [
    {'doc_id': 'P11', 'title': '锁座有效期', 'version': 'v1', 'source': 'data/policies.md#P11',
     'chunk_id': 'P11-0000-abc123', 'score': 1.5, 'rank': 1, 'content': '锁座后 15 分钟内必须完成支付，超时自动释放。'},
    {'doc_id': 'P12', 'title': '取消订单', 'version': 'v1', 'source': 'data/policies.md#P12',
     'chunk_id': 'P12-0000-def456', 'score': 1.2, 'rank': 2, 'content': '未支付订单取消不收取手续费。'},
]


def trace_for(sid, question, reply):
    trace = Trace(sid, question)
    trace.finish(reply)
    return trace


class IntentDetectionTests(unittest.TestCase):
    def test_families(self):
        self.assertEqual('ticket_query', detect_intent('查明天上海到杭州的高铁二等座')['intent'])
        self.assertEqual('policy_consult', detect_intent('儿童票怎么买？')['intent'])
        self.assertEqual('refund_change', detect_intent('退票手续费怎么算？')['intent'])
        self.assertEqual('lock_pay', detect_intent('锁座后多久必须完成支付？')['intent'])
        self.assertEqual('order_query', detect_intent('我的订单到哪了？')['intent'])

    def test_bare_policy_request_needs_clarification(self):
        intent = detect_intent('检索政策')
        self.assertEqual('policy_consult', intent['intent'])
        self.assertTrue(intent['needs_clarification'])

    def test_policy_request_with_evidence_is_not_clarification(self):
        events = [{'event_type': 'rag_result', 'status': 'succeeded', 'documents': DOCS}]
        self.assertFalse(detect_intent('儿童票怎么买？', '', events)['needs_clarification'])


class CandidateGroundingTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.path = self.directory / 'run_events.jsonl'
        self.sid = 'web-intent-test'

    def generate(self, trace, prior=(), asked=(), events=()):
        with capture(self.path):
            bind(trace)
            for kind, status, fields in events:
                emit(kind, status, **fields)
            return followups.generate_and_save(trace.to_dict(), {'trace_id': trace.trace_id}, self.directory,
                                               asked=list(asked), prior_run_ids=list(prior), authorized=False)

    def ticket_round(self):
        trace = trace_for(self.sid, '查明天上海到杭州的高铁二等座', '查到 G7303、G7302 两班。')
        row = self.generate(trace, events=[
            ('tool_result', 'succeeded', {'tool': 'query_tickets', 'executed': True, 'output': {'trains': TRAINS}})])
        return trace, row

    def test_ticket_turn_offers_ticket_questions(self):
        trace, row = self.ticket_round()
        self.assertEqual('ticket_query', row['intent'])
        self.assertTrue(any('班次' in q or 'G7303' in q for q in row['suggestions']))

    def test_policy_turn_never_inherits_ticket_rows(self):
        ticket, _ = self.ticket_round()
        trace = trace_for(self.sid, '检索政策', '您想了解哪类政策？退改签、儿童票、行李规定、报销凭证？')
        row = self.generate(trace, prior=[ticket.trace_id], asked=['查明天上海到杭州的高铁二等座'])
        self.assertEqual('policy_consult', row['intent'])
        self.assertTrue(row['needs_clarification'])
        self.assertTrue(row['suggestions'])
        self.assertFalse([q for q in row['suggestions'] if 'G73' in q or '班次' in q])
        self.assertEqual([], row['doc_ids'])

    def test_policy_turn_uses_this_turns_rag_evidence(self):
        trace = trace_for(self.sid, '锁座后多久必须完成支付？', '依据 P11：锁座后 15 分钟内必须完成支付。')
        row = self.generate(trace, asked=['检索政策'], events=[
            ('rag_result', 'succeeded', {'retrieval_id': 'ret-1', 'mode': 'keyword', 'documents': DOCS})])
        self.assertEqual('lock_pay', row['intent'])
        self.assertIn('P11', row['doc_ids'])  # selected suggestions cite this turn's docs
        self.assertEqual(['P11-0000-abc123', 'P12-0000-def456'], row['chunk_ids'])
        self.assertEqual(trace.trace_id, row['evidence_run_id'])
        self.assertTrue(row['suggestions'])

    def test_policy_turn_without_retrieval_only_clarifies(self):
        trace = trace_for(self.sid, '紫砂壶怎么养？', '没有检索到相关依据。')
        row = self.generate(trace)
        self.assertEqual([], row['doc_ids'])
        self.assertTrue(row['suggestions'])
        self.assertEqual({'clarify'}, {g['kind'] for g in row['grounding']})

    def test_empty_retrieval_is_not_padded_with_ticket_questions(self):
        ticket, _ = self.ticket_round()
        trace = trace_for(self.sid, '行李超重怎么收费？', '没有检索到相关依据。')
        row = self.generate(trace, prior=[ticket.trace_id], events=[
            ('rag_result', 'insufficient_evidence', {'retrieval_id': 'ret-empty', 'mode': 'keyword', 'documents': []})])
        self.assertEqual({'clarify'}, {g['kind'] for g in row['grounding']})
        self.assertFalse([q for q in row['suggestions'] if 'G73' in q])

    def test_sessions_do_not_share_followup_records(self):
        other = Path(tempfile.mkdtemp())
        trace = trace_for(self.sid, '锁座后多久必须完成支付？', '依据 P11。')
        row = self.generate(trace, events=[
            ('rag_result', 'succeeded', {'retrieval_id': 'ret-1', 'mode': 'keyword', 'documents': DOCS})])
        self.assertEqual(self.sid, row['session_id'])
        from target.followups import read_record
        self.assertIsNone(read_record(other, self.sid, trace.trace_id, trace.to_dict()))
        self.assertIsNone(read_record(self.directory, 'web-other', trace.trace_id, trace.to_dict()))
        self.assertIsNotNone(read_record(self.directory, self.sid, trace.trace_id, trace.to_dict()))


if __name__ == '__main__':
    unittest.main()
