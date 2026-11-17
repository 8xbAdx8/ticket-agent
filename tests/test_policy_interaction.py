"""Offline policy UI projections: sources/delivery/recommendations stay distinct."""
import copy
import unittest

from web.policy_interaction import policy_view, followup_questions


HIT = {'doc_id': 'P11', 'title': '锁座与支付有效期', 'version': 'version-from-source',
       'source': 'data/policies.md#P11', 'score': 1.5, 'rank': 1,
       'content': '模拟锁座有效期 15 分钟，过期未支付自动释放库存；下单必须提供与锁座一致的乘客列表；重复支付不重复扣减库存。'}


def event(kind, **values):
    return {'event_type': kind, 'run_id': 'run-1', 'session_id': 'session-1',
            'event_id': 'event-' + kind, 'status': 'recorded', **values}


def audit(hits=None, call_id='call-1'):
    return {'trace_id': 'run-1', 'public_trace': {'session_id': 'session-1', 'reply': '这里提及P99，不能凭回复造来源。'},
            'fault_report': {'executions': [{'tool': 'search_policy', 'ok': True, 'executed': True,
                'call_id': call_id, 'result': {'hits': [HIT] if hits is None else hits}}]}}


def view(events=(), records=(), evidence=None):
    return policy_view('session-1', 'run-1', events, records, audit() if evidence is None else evidence)


class PolicyProjectionTests(unittest.TestCase):
    def test_no_record_stays_unsearched(self):
        result = view()
        self.assertEqual('not_searched', result['status'])
        self.assertEqual([], result['evidence'])

    def test_actual_start_and_tool_start_show_searching(self):
        for started in (event('rag_start'), event('tool_start', tool='search_policy')):
            self.assertEqual('searching', view([started])['status'])
        self.assertEqual('not_searched', view([event('model_tool_proposed', tool='search_policy')])['status'])

    def test_actual_hit_identity_and_missing_fields_not_inferred(self):
        hit = {'doc_id': 'actual-P', 'content': '实际原文'}
        result = view([event('rag_result', documents=[hit])])
        self.assertEqual('retrieved', result['status'])
        row = result['evidence'][0]
        self.assertEqual('actual-P', row['doc_id'])
        self.assertIsNone(row['score'])
        self.assertIsNone(row['version'])
        self.assertIsNone(row['rank'])
        self.assertIsNone(row['mode'])
        self.assertIsNone(row['entered_context'])
        self.assertEqual('尚未验证', row['support_status'])
        self.assertNotIn('P99', [r['doc_id'] for r in result['evidence']])

    def test_empty_and_failure_are_distinct(self):
        self.assertEqual('insufficient_evidence', view([event('rag_result', documents=[])])['status'])
        failed = view([event('rag_start'), event('rag_error', status='failed', error='RagError')])
        self.assertEqual('failed', failed['status'])
        self.assertEqual('RagError', failed['reason'])

    def test_failed_later_retrieval_keeps_earlier_evidence_but_failed_status(self):
        result = view([event('rag_result', retrieval_id='first', documents=[HIT]),
                       event('rag_start', retrieval_id='second'),
                       event('rag_error', retrieval_id='second', status='failed', error='RagError')])
        self.assertEqual('failed', result['status'])
        self.assertEqual('first', result['evidence'][0]['retrieval_id'])

    def test_other_session_events_and_records_never_mix(self):
        events = [event('rag_result', session_id='other', documents=[HIT])]
        records = [{'session_id': 'other', 'trace_id': 'run-1', 'status': 'retrieved', 'hits': [HIT]}]
        self.assertEqual([], view(events, records)['evidence'])
        self.assertEqual('not_searched', view(events, records)['status'])

    def test_other_run_events_and_records_never_mix(self):
        records = [{'session_id': 'session-1', 'trace_id': 'other', 'status': 'retrieved', 'hits': [HIT]}]
        self.assertEqual([], view([event('rag_result', run_id='other', documents=[HIT])], records)['evidence'])

    def test_old_missing_session_needs_matching_audit(self):
        old = event('rag_result', documents=[HIT])
        old.pop('session_id')
        self.assertEqual(1, view([old])['count'])
        wrong = audit()
        wrong['public_trace']['session_id'] = 'other'
        self.assertEqual(0, view([old], evidence=wrong)['count'])

    def test_duplicate_dispatch_and_service_evidence_not_counted_twice(self):
        events = [event('rag_result', retrieval_id='retrieval-1', mode='keyword', documents=[HIT]),
                  event('tool_result', tool='search_policy', status='succeeded', executed=True,
                        event_id='dispatch-result', output={'hits': [HIT]}),
                  event('rag_result', event_id='generic-rag-result', documents=[HIT])]
        records = [{'schema': 'ticket-rag-retrieval/1', 'trace_id': 'run-1', 'session_id': 'session-1',
                    'retrieval_id': 'retrieval-1', 'mode': 'keyword', 'status': 'retrieved', 'hits': [HIT]}]
        result = view(events, records)
        self.assertEqual(1, result['count'])
        self.assertEqual('keyword', result['evidence'][0]['mode'])
        self.assertIn('generic-rag-result', result['evidence'][0]['event_ids'])

    def test_retrieval_modes_or_scores_have_separate_provenance(self):
        events = [event('rag_result', retrieval_id='one', mode='keyword', documents=[HIT]),
                  event('rag_result', retrieval_id='two', mode='vector', event_id='vector-event', documents=[{**HIT, 'score': 0.8}])]
        result = view(events)
        self.assertEqual(2, result['count'])
        self.assertEqual(['keyword', 'vector'], [r['mode'] for r in result['evidence']])
        self.assertEqual([1.5, 0.8], [r['score'] for r in result['evidence']])

    def test_two_distinct_retrievals_with_same_document_keep_ids(self):
        result = view([event('rag_result', retrieval_id='one', documents=[HIT]),
                       event('rag_result', retrieval_id='two', documents=[HIT])])
        self.assertEqual(2, result['count'])
        self.assertEqual(['one', 'two'], [r['retrieval_id'] for r in result['evidence']])

    def test_entered_context_requires_actual_message_content_and_current_call(self):
        result = view([event('rag_result', documents=[HIT]), event('tool_result_in_model_request',
                      tool='search_policy', call_id='call-1', documents=[HIT])])
        row = result['evidence'][0]
        self.assertIs(row['entered_context'], True)
        self.assertEqual('尚未验证', row['support_status'])

    def test_call_id_alone_does_not_prove_context(self):
        result = view([event('rag_result', documents=[HIT]),
                       event('tool_result_in_model_request', tool='search_policy', call_id='call-1')])
        self.assertIsNone(result['evidence'][0]['entered_context'])

    def test_message_created_alone_does_not_prove_model_received(self):
        result = view([event('rag_result', documents=[HIT]),
                       event('tool_message_created', tool='search_policy', call_id='call-1')])
        self.assertIsNone(result['evidence'][0]['entered_context'])

    def test_mutated_context_not_proven_by_shared_document_id(self):
        result = view([event('rag_result', documents=[HIT]), event('tool_result_in_model_request',
                       call_id='call-1', documents=[{**HIT, 'content': '被改过的内容'}])])
        self.assertIsNone(result['evidence'][0]['entered_context'])

    def test_previous_call_repeated_in_context_does_not_prove_new_run_evidence(self):
        result = view([event('rag_result', documents=[HIT]),
                       event('tool_result_in_model_request', call_id='previous-turn-call', documents=[HIT])])
        self.assertIsNone(result['evidence'][0]['entered_context'])

    def test_failed_or_unexecuted_tool_cannot_prove_delivery(self):
        for field, value in (('ok', False), ('executed', False), ('executed', None)):
            record = audit()
            record['fault_report']['executions'][0][field] = value
            result = view([event('rag_result', documents=[HIT]), event('tool_result_in_model_request',
                           call_id='call-1', documents=[HIT])], evidence=record)
            self.assertIsNone(result['evidence'][0]['entered_context'])

    def test_sidecar_fallback_uses_stored_mode_rank_score(self):
        records = [{'schema': 'ticket-rag-retrieval/1', 'trace_id': 'run-1', 'session_id': 'session-1',
                    'retrieval_id': 'ret', 'mode': 'hybrid', 'status': 'retrieved', 'hits': [HIT]}]
        result = view(records=records)
        self.assertEqual('retrieved', result['status'])
        self.assertEqual('hybrid', result['evidence'][0]['mode'])
        self.assertEqual(1.5, result['evidence'][0]['score'])

    def test_older_sidecar_completion_does_not_override_new_live_start(self):
        records = [{'trace_id': 'run-1', 'session_id': 'session-1', 'status': 'retrieved', 'hits': [HIT]}]
        self.assertEqual('searching', view([event('rag_start', retrieval_id='new')], records)['status'])

    def test_failed_raw_sidecar_hits_not_promoted_to_valid_evidence(self):
        records = [{'trace_id': 'run-1', 'session_id': 'session-1', 'status': 'failed',
                    'retrieval_evidence': {'hits': [HIT]}, 'error_category': 'risk'}]
        result = view(records=records)
        self.assertEqual('failed', result['status'])
        self.assertEqual([], result['evidence'])

    def test_projection_does_not_modify_source(self):
        events = [event('rag_result', documents=[HIT])]
        original = copy.deepcopy(events)
        view(events)
        self.assertEqual(original, events)


class FollowupTests(unittest.TestCase):
    def test_lock_questions_grounded_and_repeatable(self):
        query, reply = '锁座后多久必须完成支付？', '本轮模拟锁座有效期15分钟。'
        result = followup_questions(query, reply, [HIT])
        self.assertEqual(3, len(result))
        self.assertEqual(result, followup_questions(query, reply, [HIT]))
        self.assertFalse(any('有效期有多长' in q for q in result))
        self.assertIn('重复支付会重复扣减库存吗？', result)
        self.assertFalse(any('扣款' in q for q in result))

    def test_refund_questions_do_not_invent_arrival_time(self):
        hit = {'doc_id': 'P01', 'content': '开车前48小时以上退票收取手续费；已取报销凭证或已改签的车票不退。'}
        result = followup_questions('退票手续费怎么算？', '这是模拟退票政策。', [hit])
        self.assertEqual(2, len(result))
        self.assertFalse(any('到账' in q or '多久' in q for q in result))

    def test_full_history_prevents_recommending_already_asked_facets(self):
        first = followup_questions('支付时限', '锁座政策', [HIT])
        result = followup_questions('支付时限', '锁座政策', [HIT], asked=[q.replace('？', '') for q in first])
        self.assertFalse(set(first).intersection(result))

    def test_empty_evidence_or_reply_produces_no_suggestions(self):
        self.assertEqual([], followup_questions('退票', '可以查政策', []))
        self.assertEqual([], followup_questions('锁座', '', [HIT]))

    def test_title_without_content_or_id_not_used_as_evidence(self):
        self.assertEqual([], followup_questions('锁座政策', '锁座政策', [{'title': '锁座有效期'}]))
        self.assertEqual([], followup_questions('锁座政策', '锁座政策', [{'content': HIT['content']}]))

    def test_unrelated_returned_documents_do_not_drive_questions(self):
        self.assertEqual([], followup_questions('我想了解行李规定', '这是行李查询', [HIT]))

    def test_single_supported_facet_is_not_padded_with_unknown_questions(self):
        hit = {'doc_id': 'limited', 'content': '锁座有效期15分钟。'}
        self.assertEqual([], followup_questions('锁座政策', '锁座政策', [hit]))

    def test_error_reply_not_suitable_for_policy_recommendations(self):
        self.assertEqual([], followup_questions('锁座政策', '请求未完成，请检查错误。', [HIT]))

    def test_suggestion_limit_and_input_not_mutated(self):
        original = copy.deepcopy(HIT)
        result = followup_questions('锁座政策', '锁座政策', [HIT], limit=2)
        self.assertEqual(2, len(result))
        self.assertEqual(original, HIT)
        self.assertEqual([], followup_questions('锁座政策', '锁座政策', [HIT], limit=0))


if __name__ == '__main__':
    unittest.main()
