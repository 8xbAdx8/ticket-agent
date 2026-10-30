"""Offline service-boundary RAG events; no model, real vector or HTTP request."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import config
from target import rag_service
from target.run_events import bind, capture
from target.trace import Trace


class RagStatusEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = self.root/'policy.md'
        self.policy.write_text('# 独立离线夹具\n\n## [P11] 锁座与支付\n模拟锁座有效期15分钟，过期未支付释放库存。\n', encoding='utf-8')
        self.events = self.root/'run_events.jsonl'
        env = patch.dict(os.environ, {'RAG_QUALITY_PROFILE': 'v35', 'TICKET_FROZEN_RAG_EVIDENCE': '',
                                      'RAG_TOP_K': '3', 'RAG_ALLOW_NETWORK': '0'})
        env.start()
        self.addCleanup(env.stop)
        for name, value in (('POLICY_PATH', self.policy), ('TRACE_DIR', self.root), ('PROVIDER', 'mock')):
            mocked = patch.object(config, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)

    def read_events(self):
        return [json.loads(line) for line in self.events.read_text(encoding='utf-8').splitlines()]

    def retrieval_records(self):
        return [json.loads(line) for line in (self.root/'rag_runs.jsonl').read_text(encoding='utf-8').splitlines()]

    def test_start_callback_happens_before_actual_keyword_and_result_after_sidecar(self):
        from target.rag_store import keyword as actual_keyword
        seen, observations = [], []
        def keyword(*args, **kwargs):
            observations.append(('during_retrieval', seen[-1]['event_type']))
            return actual_keyword(*args, **kwargs)
        def callback(event):
            seen.append(event)
            if event['event_type'] == 'rag_result':
                observations.append(('result_sidecar_exists', (self.root/'rag_runs.jsonl').exists()))
        trace = Trace('session-a', '锁座有效期多久？')
        with capture(self.events, callback), rag_service.scope(trace_id=trace.trace_id,
            session_id=trace.session_id, call_id='tool-call-a'):
            bind(trace)
            with patch('target.rag_store.keyword', side_effect=keyword):
                result = rag_service.retrieve(trace.user_msg, mode='keyword')
        rows = self.read_events()
        rag = [e for e in rows if e['event_type'].startswith('rag_')]
        self.assertEqual(['rag_start', 'rag_result'], [r['event_type'] for r in rag])
        self.assertEqual(('during_retrieval', 'rag_start'), observations[0])
        self.assertIn(('result_sidecar_exists', True), observations)
        self.assertEqual({trace.trace_id}, {r['run_id'] for r in rows})
        self.assertEqual({trace.session_id}, {r['session_id'] for r in rows})
        self.assertEqual(rag[0]['retrieval_id'], rag[1]['retrieval_id'])
        self.assertEqual('tool-call-a', rag[1]['call_id'])
        self.assertEqual(result['hits'], rag[1]['documents'])
        self.assertEqual('keyword', rag[1]['mode'])
        self.assertEqual(result['count'], rag[1]['hit_count'])
        self.assertEqual(self.retrieval_records()[0]['retrieval_id'], rag[1]['retrieval_id'])
        self.assertEqual('not_proven_by_retrieval_event', rag[1]['context_delivery'])
        self.assertEqual('not_verified', rag[1]['answer_support'])
        for previous, current in zip(rows, rows[1:]):
            self.assertEqual(previous['event_id'], current['previous_event_id'])

    def test_no_documents_has_explicit_insufficient_evidence_not_fake_success(self):
        with capture(self.events):
            bind(Trace('session-empty', 'ZZZ_UNRELATED'))
            result = rag_service.retrieve('ZZZ_UNRELATED', mode='keyword')
        self.assertEqual([], result['hits'])
        event = self.read_events()[-1]
        self.assertEqual('rag_result', event['event_type'])
        self.assertEqual('insufficient_evidence', event['status'])
        self.assertEqual(0, event['hit_count'])
        self.assertEqual([], event['documents'])

    def test_failure_event_preserves_error_type_without_response_or_result(self):
        with capture(self.events):
            bind(Trace('session-error', '锁座多久'))
            with patch.object(rag_service, 'configured_index', side_effect=TimeoutError('sensitive backend response')):
                with self.assertRaises(TimeoutError):
                    rag_service.retrieve('锁座多久', mode='vector')
        event = self.read_events()[-1]
        self.assertEqual('rag_error', event['event_type'])
        self.assertEqual('failed', event['status'])
        self.assertEqual('vector', event['mode'])
        self.assertEqual('TimeoutError', event['error_category'])
        self.assertNotIn('documents', event)
        self.assertNotIn('hit_count', event)
        self.assertNotIn('sensitive backend response', self.events.read_text(encoding='utf-8'))
        self.assertEqual('failed', self.retrieval_records()[-1]['status'])

    def test_invalid_configuration_is_error_without_fabricated_retrieval_start(self):
        with capture(self.events):
            bind(Trace('session-config', '锁座多久'))
            with self.assertRaisesRegex(ValueError, 'invalid_rag_mode'):
                rag_service.retrieve('锁座多久', mode='unknown-mode')
        rows = self.read_events()
        self.assertNotIn('rag_start', [r['event_type'] for r in rows])
        self.assertEqual('rag_error', rows[-1]['event_type'])
        self.assertEqual('failed', self.retrieval_records()[-1]['status'])

    def test_separate_runs_in_same_event_file_do_not_reuse_identity(self):
        traces = [Trace('session-one', '锁座多久'), Trace('session-two', '库存何时释放')]
        for trace in traces:
            with capture(self.events):
                bind(trace)
                rag_service.retrieve(trace.user_msg, mode='keyword')
        rows = self.read_events()
        for trace in traces:
            found = [r for r in rows if r['run_id'] == trace.trace_id]
            self.assertEqual({trace.session_id}, {r['session_id'] for r in found})
            self.assertEqual(1, sum(r['event_type'] == 'rag_start' for r in found))
            self.assertEqual(1, sum(r['event_type'] == 'rag_result' for r in found))
        complete = [r for r in rows if r['event_type'] == 'rag_result']
        self.assertEqual(2, len({r['retrieval_id'] for r in complete}))

    def test_direct_invocation_without_scope_keeps_captured_session(self):
        trace = Trace('captured-session', '锁座多久')
        with capture(self.events), rag_service.scope():
            bind(trace)
            result = rag_service.retrieve(trace.user_msg, mode='keyword')
        self.assertEqual({'question', 'hits', 'count'}, set(result))
        self.assertTrue(all(r['session_id'] == trace.session_id for r in self.read_events()))

    def test_risky_partial_candidates_never_become_successful_result_events(self):
        hits = [{'doc_id': 'P11', 'title': '当前', 'content': '锁座有效期15分钟', 'score': 1.0},
                {'doc_id': 'P90', 'title': '冲突测试', 'content': '锁座有效期60分钟', 'score': 0.9}]
        with capture(self.events):
            bind(Trace('session-risk', '锁座多久'))
            with patch('target.rag_store.keyword', return_value=hits):
                with self.assertRaisesRegex(RuntimeError, 'rag_evidence_risk'):
                    rag_service.retrieve('锁座多久', mode='keyword')
        rows = self.read_events()
        self.assertNotIn('rag_result', [r['event_type'] for r in rows])
        self.assertEqual('rag_error', rows[-1]['event_type'])
        self.assertNotIn('documents', rows[-1])
        self.assertEqual(hits, self.retrieval_records()[-1]['retrieval_evidence']['hits'])

    def test_evidence_write_failure_is_error_not_successful_retrieval_result(self):
        with capture(self.events):
            bind(Trace('session-write-error', '锁座多久'))
            with patch.object(rag_service, 'save', side_effect=PermissionError('local evidence file locked')):
                with self.assertRaises(PermissionError):
                    rag_service.retrieve('锁座多久', mode='keyword')
        event = self.read_events()[-1]
        self.assertEqual('rag_error', event['event_type'])
        self.assertEqual('evidence_persistence', event['stage'])
        self.assertEqual('PermissionError', event['error_category'])
        self.assertNotIn('documents', event)

    def test_stubbed_vector_metadata_is_reported_as_received_not_invented(self):
        """Protocol-only fixture, not a real Embedding/Vector quality result."""
        class IndexFixture:
            def retrieve(self, *args, **kwargs):
                return {'mode': 'vector', 'hits': [{'doc_id': 'P11', 'title': '夹具', 'content': '锁座有效期15分钟',
                    'rank': 1, 'score': 0.81, 'version': 'fixture-version', 'source': 'fixture.md#P11'}],
                    'embedding_model': 'fixture-not-real', 'index_version': 'fixture-index'}
        with capture(self.events):
            bind(Trace('session-vector-fixture', '锁座多久'))
            with patch.object(rag_service, 'configured_index', return_value=IndexFixture()):
                result = rag_service.retrieve('锁座多久', mode='vector')
        event = self.read_events()[-1]
        self.assertEqual(result['hits'], event['documents'])
        self.assertEqual(0.81, event['documents'][0]['score'])
        self.assertEqual('fixture-version', event['documents'][0]['version'])
        self.assertEqual(1, event['documents'][0]['rank'])
        self.assertIsNone(event['duration_ms'])

    def test_without_capture_does_not_create_runtime_event_file(self):
        result = rag_service.retrieve('锁座多久', mode='keyword')
        self.assertTrue(result['hits'])
        self.assertFalse(self.events.exists())
        self.assertEqual(1, len(self.retrieval_records()))


if __name__ == '__main__':
    unittest.main()
