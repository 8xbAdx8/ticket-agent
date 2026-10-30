"""New benchmark tests; independent of B's original assertions and real APIs."""
import copy
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from target import rag_benchmark as b


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.corpus, cls.manifest = b.load()

    def test_1000_candidate_ids_and_explicit_verification_shortfall(self):
        result = b.validate(self.cases, self.corpus, self.manifest)
        self.assertEqual(1000, len(self.cases))
        self.assertEqual(1000, len({c['case_id'] for c in self.cases}))
        self.assertEqual(430, result['verified_count'])
        self.assertEqual(570, result['needs_review_count'])
        self.assertFalse(result['complete_1000_verified'])

    def test_every_category_candidate_quota(self):
        for cat, n in b.QUOTAS.items():
            self.assertEqual(n, sum(c['category'] == cat for c in self.cases))

    def test_schema_and_all_exact_evidence(self):
        result = b.validate(self.cases, self.corpus, self.manifest)
        self.assertTrue(result['valid_structure'], result['errors'][:2])

    def test_provenance_must_match_frozen_corpus(self):
        case = copy.deepcopy(self.cases[0])
        case['provenance']['policy_version'] = 'not-the-corpus-hash'
        self.assertEqual(1, b.validate([case], self.corpus)['invalid_count'])

    def test_unknown_document_fails(self):
        case = copy.deepcopy(self.cases[0])
        case['expected_doc_ids'] = ['P999']
        self.assertTrue(b.validate([case], self.corpus)['errors'])

    def test_quote_and_answer_point_must_be_grounded(self):
        for field in ('required_evidence', 'expected_answer_points'):
            case = copy.deepcopy(self.cases[0])
            if field == 'required_evidence':
                case[field][0]['quote'] = '每人赠送一百万元'
            else:
                case[field] = ['每人赠送一百万元']
            self.assertEqual(1, b.validate([case], self.corpus)['invalid_count'])

    def test_schema_missing_fields_rejected(self):
        case = copy.deepcopy(self.cases[0])
        case.pop('difficulty')
        self.assertEqual(1, b.validate([case], self.corpus)['invalid_count'])

    def test_malformed_schema_does_not_crash_the_validator(self):
        case = copy.deepcopy(self.cases[0])
        case['required_evidence'] = 123
        result = b.validate([case, 'not-an-object'], self.corpus)
        self.assertEqual(2, result['invalid_count'])
        self.assertFalse(result['valid_structure'])

    def test_duplicate_and_polite_punctuation_variant_detected(self):
        a, z = copy.deepcopy(self.cases[0]), copy.deepcopy(self.cases[0])
        z['case_id'] = 'RAG-DUP'
        z['question'] = '请问' + a['question'] + '？'
        self.assertEqual(1, b.validate([a, z], self.corpus)['invalid_count'])

    def test_local_near_duplicates_not_automatically_deleted(self):
        a, z = copy.deepcopy(self.cases[0]), copy.deepcopy(self.cases[0])
        a['question'] = '学生优惠的适用时段是否限寒暑假期间'
        z['question'] = '学生优惠的适用时段是否限寒暑假时间'
        z['case_id'], z['group_id'] = 'RAG-Z', 'different'
        self.assertTrue(b.near_duplicates([a, z]))
        self.assertEqual(2, len([a, z]))

    def test_grouped_split_and_near_duplicate_isolation(self):
        result = b.validate(self.cases, self.corpus, self.manifest)
        self.assertFalse(result['group_leakage'])
        self.assertFalse(result['near_duplicate_leakage'])
        self.assertEqual(1000, sum(result['split_counts'].values()))

    def test_split_reproducible(self):
        a = copy.deepcopy(self.cases)
        z = copy.deepcopy(self.cases)
        b.split_cases(a)
        b.split_cases(z)
        self.assertEqual([c['split'] for c in a], [c['split'] for c in z])

    def test_fixture_docs_not_normal_active_corpus(self):
        from target.rag_store import documents
        ids = {d['doc_id'] for d in documents(b.DATA/'active-policies.md')}
        self.assertEqual(57, len(ids))
        self.assertFalse(ids.intersection(('P56', 'P57', 'P58')))

    def test_legacy48_hashes_retained(self):
        for p, digest in self.manifest['legacy_48_compatibility_files'].items():
            self.assertEqual(digest, b.sha((b.ROOT/p).read_bytes()))


class MetricsTests(unittest.TestCase):
    def metrics(self, relevant, hits, category='normal_qa'):
        return b.retrieval_metrics({'expected_doc_ids': relevant, 'category': category}, [{'doc_id': d} for d in hits])

    def test_recall_and_mrr_first_relevant_rank(self):
        r = self.metrics(['P1'], ['P0', 'P1', 'P2'])
        self.assertEqual(0, r['recall_at_1'])
        self.assertEqual(1, r['recall_at_3'])
        self.assertEqual(0.5, r['mrr'])

    def test_multi_doc_not_any_hit(self):
        r = self.metrics(['P1', 'P2'], ['P1', 'P3'])
        self.assertEqual(0.5, r['recall_at_1'])
        self.assertEqual(0.5, r['multi_evidence_coverage_at_5'])
        self.assertFalse(r['evidence_complete_at_5'])

    def test_duplicates_do_not_inflate_recall_or_rank(self):
        r = self.metrics(['P2'], ['P1', 'P1', 'P2'])
        self.assertEqual(0.5, r['mrr'])

    def test_no_answer_denominator_separate(self):
        r = self.metrics([], ['P1'], 'no_answer')
        self.assertTrue(r['no_answer_false_recall'])
        self.assertIsNone(r['mrr'])
        self.assertIsNone(r['answer_correct'])
        self.assertIsNone(self.metrics([], [])['no_answer_false_recall'])

    def test_alternative_sources_vs_multiple_required_documents(self):
        alternative = b.retrieval_metrics({'expected_doc_ids': ['P16'], 'alternative_doc_ids': ['P13'],
            'category': 'normal_qa'}, [{'doc_id': 'P13'}])
        self.assertEqual(0.5, alternative['recall_at_1'])
        self.assertEqual(1, alternative['mrr'])
        self.assertTrue(alternative['evidence_complete_at_5'])
        self.assertIsNone(alternative['multi_evidence_coverage_at_5'])
        self.assertFalse(self.metrics(['P13', 'P16'], ['P13'])['evidence_complete_at_5'])

    def test_unknown_not_zero(self):
        self.assertEqual({'value': None, 'denominator': 0}, b.ratio([None, None]))

    def test_modes_share_same_formula_and_denominators(self):
        rows = []
        for mode in ('keyword', 'vector', 'hybrid'):
            rows.append({'execution_status': 'completed', 'category': 'normal_qa', 'difficulty': 'easy',
                'source_policy_ids': ['P1'], 'mode': mode, 'retrieval_metrics': self.metrics(['P1'], ['P0', 'P1'])})
        scores = [b.summarize([r])['metrics'] for r in rows]
        self.assertEqual(scores[0], scores[1])
        self.assertEqual(scores[1], scores[2])


class AnswerTests(unittest.TestCase):
    def setUp(self):
        self.case = b.load()[0][0]
        self.hits = [{'doc_id': 'P01', 'version': 'fixture', 'content': '开车前 48 小时以上退票，收取票价 5% 手续费'}]

    def sample(self, reply, **kw):
        return {'case_id': self.case['case_id'], 'question': self.case['question'], 'raw_reply': reply,
                'context': self.hits, 'context_sha256': b.sha(self.hits), 'origin': 'offline_fixture', **kw}

    def test_unbound_context_is_not_pass(self):
        result = b.assess_answer(self.case, self.hits, self.sample('P01：可以退款。', context_sha256='bad'))
        self.assertEqual('INDETERMINATE', result['verdict'])

    def test_subset_context_requires_full_retrieval_binding(self):
        sample = self.sample('无法确认。', context=[], context_sha256=b.sha([]))
        self.assertEqual('answer_context_or_question_binding_failed', b.assess_answer(self.case, self.hits, sample)['reason'])
        sample['retrieval_sha256'] = b.sha(self.hits)
        result = b.assess_answer(self.case, self.hits, sample)
        self.assertEqual('无法确认。', result['raw_reply'])
        self.assertFalse(result['real_api_evidence_verified'])

    def test_unknown_semantics_not_pass(self):
        r = b.assess_answer(self.case, self.hits, self.sample('P01：通常应该比较合理，建议考虑。'))
        self.assertEqual('INDETERMINATE', r['verdict'])

    def test_wrong_citation_and_unexecuted_action_fail(self):
        r = b.assess_answer(self.case, self.hits, self.sample('我已经退款。依据P99。'))
        self.assertEqual('FAIL', r['verdict'])

    def test_no_citation_precision_is_unknown_and_raw_preserved(self):
        raw = '您好。'
        r = b.assess_answer(self.case, self.hits, self.sample(raw))
        self.assertEqual(raw, r['raw_reply'])
        self.assertIsNone(r['citation_id_precision'])
        self.assertEqual('offline_fixture', r['origin'])
        self.assertEqual('INDETERMINATE', r['verdict'])

    def test_quote_with_correct_number_not_full_answer_success(self):
        r = b.assess_answer(self.case, self.hits, self.sample('P01：手续费为5%。'))
        self.assertNotEqual('PASS', r['verdict'])


class FakeRetriever:
    identity = {'origin': 'offline_fixture_not_real_embedding'}
    def __init__(self, *args, **kwargs):
        pass
    def retrieve(self, question, overlays=()):
        return []


class RunnerTests(unittest.TestCase):
    def test_keyword_scope_suppresses_unsupported_attribute_not_raw_evidence(self):
        query = '高铁保险理赔的免赔金额是多少？'
        raw = b.CachedRetriever(b.DATA, None, 'keyword', keyword_profile='raw')
        scoped = b.CachedRetriever(b.DATA, None, 'keyword')
        self.assertTrue(raw.retrieve(query))
        self.assertEqual([], scoped.retrieve(query))
        self.assertIn('insurance', scoped.last_filter['unsupported_attributes'])
        self.assertTrue(scoped.last_filter['candidate_hits'])

    def test_keyword_scope_retains_supported_policy_order_and_scores(self):
        query = '成人行李超重部分每千克多少钱？'
        raw = b.CachedRetriever(b.DATA, None, 'keyword', keyword_profile='raw')
        scoped = b.CachedRetriever(b.DATA, None, 'keyword')
        self.assertEqual(raw.retrieve(query), scoped.retrieve(query))
        self.assertIn('P06', [h['doc_id'] for h in scoped.retrieve(query)])

    def test_scope_uses_corpus_content_not_blacklisted_question_or_case_label(self):
        from target.rag_store import documents
        docs = documents(b.DATA/'active-policies.md')
        query = '保险理赔规则是什么？'
        self.assertTrue(b.keyword_scope(query, docs)['unsupported_attributes'])
        extended = docs + [{'doc_id': 'new', 'title': '保险理赔', 'content': '本独立测试语料新增保险理赔说明。'}]
        self.assertEqual([], b.keyword_scope(query, extended)['unsupported_attributes'])

    def test_all_verified_keyword_results_retain_order_scores_and_content(self):
        raw = b.CachedRetriever(b.DATA, None, 'keyword', keyword_profile='raw')
        scoped = b.CachedRetriever(b.DATA, None, 'keyword')
        checked = 0
        for case in b.load()[0]:
            if case['provenance']['review_status'] == 'verified':
                self.assertEqual(raw.retrieve(case['question']), scoped.retrieve(case['question']), case['case_id'])
                checked += 1
        self.assertEqual(430, checked)

    def test_abstaining_retrieval_does_not_fabricate_refusal_or_answer_pass(self):
        case = next(c for c in b.load()[0] if c['category'] == 'no_answer' and '保险' in c['question'])
        with tempfile.TemporaryDirectory() as temp:
            _, report = b.run(store=temp, split='all', case_id=case['case_id'])
            row = report['rows'][0]
            self.assertEqual([], row['hits'])
            self.assertEqual('indeterminate', row['retrieval_verdict'])
            self.assertEqual('not_evaluated', row['answer_assessment']['verdict'])
            self.assertIsNone(row['delivered_context'])
            self.assertEqual(0, report['real_api_requests'])

    def test_windows_report_replace_retries_only_local_io(self):
        original = Path.replace
        calls = []
        def temporary_lock(path, target):
            calls.append(target)
            if len(calls) < 3:
                raise PermissionError('simulated short Windows reader lock')
            return original(path, target)
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(Path, 'replace', temporary_lock), patch.object(b.time, 'sleep'):
                b.write(Path(temp)/'report.json', {'value': 'saved'})
            self.assertEqual(3, len(calls))
            self.assertEqual('saved', b.read(Path(temp)/'report.json')['value'])

    def test_history_excludes_legacy48_other_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            b.write(Path(temp)/'legacy/report.json', {'dataset': 'historical_48', 'count': 48})
            self.assertEqual([], b.history(temp))

    def test_broken_history_is_reported_not_a_success(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'broken'
            path.mkdir()
            (path/'report.json').write_text('{invalid', encoding='utf-8')
            errors = []
            self.assertEqual([], b.history(temp, errors=errors))
            self.assertEqual(1, len(errors))

    def test_comparison_does_not_hide_changed_source(self):
        a = {'dataset_sha256': 'same', 'case_set_sha256': 'same', 'source_sha256': 'old',
             'configuration': {'mode': 'keyword'}, 'state': 'completed'}
        z = {**a, 'source_sha256': 'new'}
        self.assertFalse(b.compare_runs(a, z)['same_controlled_inputs_except_retrieval_mode'])

    def test_blocked_vector_never_fallback_keyword(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, result = b.run(store=temp, mode='vector', case_id='RAG-0001', split='all')
            self.assertEqual('incomplete', result['state'])
            self.assertEqual('blocked', result['rows'][0]['execution_status'])
            self.assertEqual(0, result['real_api_requests'])
            self.assertIsNone(result['summary']['metrics']['recall_at_1']['value'])
            self.assertTrue((directory/'receipt.json').exists())

    def test_failure_is_saved_and_retry_creates_new_run(self):
        class Failure(FakeRetriever):
            def retrieve(self, *args):
                raise RuntimeError('do not expose arbitrary exception text')
        with tempfile.TemporaryDirectory() as temp:
            first, report = b.run(store=temp, split='all', case_id='RAG-0001', retriever_factory=Failure)
            digest = b.sha((first/'report.json').read_bytes())
            second, rerun = b.run(store=temp, split='all', retry=first, retriever_factory=FakeRetriever)
            self.assertNotEqual(first, second)
            self.assertEqual(digest, b.sha((first/'report.json').read_bytes()))
            self.assertEqual('error', report['rows'][0]['execution_status'])
            self.assertEqual('completed', rerun['rows'][0]['execution_status'])

    def test_cancel_saved_without_retrieval(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, result = b.run(store=temp, split='all', case_id='RAG-0001', cancel=lambda: True, retriever_factory=FakeRetriever)
            self.assertEqual('cancelled', result['rows'][0]['execution_status'])
            self.assertEqual('incomplete', result['state'])
            self.assertTrue((directory/'results.jsonl').exists())

    def test_interruption_preserves_prior_results(self):
        with tempfile.TemporaryDirectory() as temp:
            def interrupt(*args):
                raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                b.run(store=temp, split='all', case_id='RAG-0001', retriever_factory=FakeRetriever, notify=interrupt)
            report = b.history(temp)[0]
            self.assertEqual('interrupted', report['state'])
            self.assertEqual(1, len(report['rows']))

    def test_summary_equals_rows_and_receipt_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory, result = b.run(store=temp, split='all', case_id='RAG-0001', retriever_factory=FakeRetriever)
            self.assertEqual(b.summarize(result['rows']), result['summary'])
            self.assertIsNone(result['rows'][0]['delivered_context'])
            self.assertFalse(result['rows'][0]['delivered_context_verified'])
            for name, digest in b.read(directory/'receipt.json')['files'].items():
                self.assertEqual(digest, b.sha((directory/name).read_bytes()))

    def test_stub_index_rejected_as_real_vector(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index = root/'source-index'
            index.mkdir()
            b.write(index/'manifest.json', {'embedding_origin': 'offline_stub'})
            before = b.files_hash(index)
            work = root/'work'
            work.mkdir()
            with self.assertRaisesRegex(ValueError, 'offline_stub_not_allowed'):
                b.CachedRetriever(b.DATA, work, 'vector', index=index, cache=root/'cache.db')
            self.assertEqual(before, b.files_hash(index))

    def test_index_work_overlap_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, 'must_not_overlap'):
                b.CachedRetriever(b.DATA, root/'child', 'vector', index=root, cache=root/'cache.db')

    def test_vector_and_hybrid_cached_protocol_with_offline_collection_fixture(self):
        """Synthetic protocol fixture, NOT a real embedding quality measurement."""
        from target.rag_store import documents
        docs = documents(b.DATA/'active-policies.md')
        vector = [1.0] + [0.0]*63
        receipt = {'origin': 'real_api', 'model': 'text-embedding-v4', 'dimensions': 64,
                   'status': 200, 'request_id': 'offline-fixture-not-real-request',
                   'response_sha256': 'fixture-not-real-response', 'vector_hashes': [b.sha(vector)]}
        state = {'schema': 'ticket-policy-index/1', 'embedding_origin': 'real_api', 'model': 'text-embedding-v4',
                 'dimensions': 64, 'endpoint': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                 'corpus_hash': b.sha((b.DATA/'active-policies.md').read_bytes()), 'embedding_receipts': [receipt],
                 'collection': 'fixture', 'chunk_count': len(docs), 'index_version': 'offline-fixture',
                 'stored_vector_hashes': {d['chunk_id']: b.sha(vector) for d in docs}}
        class Collection:
            def get(self, **kwargs):
                return {'ids': [d['chunk_id'] for d in docs], 'documents': [d['content'] for d in docs],
                        'metadatas': docs, 'embeddings': [vector]*len(docs)}
            def query(self, **kwargs):
                self.last = kwargs
                return {'metadatas': [[docs[0]]], 'documents': [[docs[0]['content']]], 'distances': [[0.1]]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index = root/'original-index'
            b.write(index/'manifest.json', state)
            cache = root/'original-cache.db'
            with sqlite3.connect(cache) as conn:
                conn.execute('CREATE TABLE vectors(cache_key TEXT PRIMARY KEY, vector TEXT, receipt TEXT)')
                # Provider's cache key uses json default whitespace, not canonical digest.
                import hashlib
                key = hashlib.sha256(json.dumps(['text-embedding-v4', 64, state['endpoint'], '测试政策问题', 'real_api'], ensure_ascii=False).encode()).hexdigest()
                conn.execute('INSERT INTO vectors VALUES(?,?,?)', (key, json.dumps(vector), json.dumps(receipt)))
            conn.close()
            original = b.sha(cache.read_bytes()), b.files_hash(index)
            with patch('chromadb.PersistentClient') as client:
                client.return_value.get_collection.return_value = Collection()
                for mode in ('vector', 'hybrid'):
                    work = root/mode
                    work.mkdir()
                    adapter = b.CachedRetriever(b.DATA, work, mode, index=index, cache=cache)
                    hits = adapter.retrieve('测试政策问题')
                    self.assertIn('P01', [h['doc_id'] for h in hits])
                    with self.assertRaisesRegex(ValueError, 'not_cached_network_prohibited'):
                        adapter.retrieve('没有缓存的另一个问题')
                    if mode == 'hybrid':
                        self.assertIn('fusion_ranks', hits[0])
            self.assertEqual(original, (b.sha(cache.read_bytes()), b.files_hash(index)))

    def test_attack_payload_is_actually_exposed_as_fixture(self):
        class Observer(FakeRetriever):
            def retrieve(self, question, overlays=()):
                self.seen = overlays
                return list(overlays)
        with tempfile.TemporaryDirectory() as temp:
            attack = next(c for c in b.load()[0] if c['category'] == 'prompt_injection')
            _, result = b.run(store=temp, split='all', case_id=attack['case_id'], retriever_factory=Observer)
            row = result['rows'][0]
            self.assertIn(attack['attack']['payload'], row['hits'][0]['content'])
            self.assertEqual('not_evaluated', row['answer_assessment']['verdict'])

    def test_read_only_history_does_not_execute(self):
        from streamlit.testing.v1 import AppTest
        with patch.object(b, 'history', return_value=[]), patch.object(b, 'run', side_effect=AssertionError('must not execute')):
            app = AppTest.from_string('from web.rag_benchmark_view import render\nrender()').run(timeout=15)
            self.assertFalse(app.exception, str(app.exception))
            self.assertTrue(any('430' in str(x.value) for x in app.markdown))

    def test_ui_reads_saved_failed_run_and_real_case_not_constants(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as temp:
            _, report = b.run(store=temp, split='all', case_id='RAG-0001', retriever_factory=FakeRetriever)
            with patch.object(b, 'STORE', Path(temp)), patch.object(b, 'history', return_value=[report]):
                app = AppTest.from_string('from web.rag_benchmark_view import render\nrender()').run(timeout=15)
                self.assertFalse(app.exception, str(app.exception))
                self.assertTrue(any(report['run_id'] in str(x.value) for x in app.markdown))
                self.assertTrue(any('逐题证据' == x.label for x in app.selectbox))


if __name__ == '__main__':
    unittest.main()
