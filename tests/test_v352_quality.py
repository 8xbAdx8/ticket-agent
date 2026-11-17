"""Frozen-dataset metrics/cache provenance and policy version checks; offline only."""
from dataclasses import replace
from contextlib import closing
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from target.v352_validation import metrics,cache_survey
from target.rag_faithfulness import check_answer


class MetricsTests(unittest.TestCase):
    def test_recall1_recall3_mrr_and_nonanswer_denominators(self):
        cases=[{'id':'a','expected_doc_ids':['P11','P12']},{'id':'b','expected_doc_ids':['P03']},{'id':'n','expected_doc_ids':[]}]
        results={'a':{'hits':[{'doc_id':'P11'},{'doc_id':'P12'}]},'b':{'hits':[{'doc_id':'P02'},{'doc_id':'P03'}]},'n':{'hits':[]}}
        r=metrics(cases,results)
        self.assertEqual(r['recall_at_1'],.25);self.assertEqual(r['recall_at_3'],1)
        self.assertEqual(r['mrr'],.75);self.assertEqual(r['no_answer_false_recall_rate'],0)
        self.assertEqual(r['not_applicable_recall_mrr_cases'],1)
        self.assertEqual(r['rows'][1]['first_correct_rank'],2)

    def test_not_run_is_unknown_not_zero_and_errors_separate(self):
        cases=[{'id':'a','expected_doc_ids':['P11']},{'id':'b','expected_doc_ids':[]}]
        r=metrics(cases,{})
        self.assertIsNone(r['recall_at_1']);self.assertIsNone(r['mrr']);self.assertEqual(r['not_run_cases'],2)
        self.assertIsNone(r['no_answer_false_recall_rate'])
        r=metrics(cases,{'a':{'error':'query_failed'}});self.assertEqual(r['indeterminate_cases'],1)

    def test_development_and_holdout_labels_unchanged(self):
        from target.v352_validation import ROOT
        expected={'development':'37645ac9faea23e8316654566fc5d75f6df3cfabcc7a31a910da81d5bf237925',
                  'holdout':'195b9f441eaaa44b4547b4e01b19f3bbe4062895f90f9258420539286ad81eb1'}
        for split,sha in expected.items():
            path=ROOT/f'cases/rag_quality_v351_{split}.json';self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),sha)

    def test_cache_survey_is_readonly_and_rejects_stub_provenance(self):
        from target.embeddings import EmbeddingProvider,EmbeddingSettings
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cache.db';settings=EmbeddingSettings(base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',dimensions=64,cache=path)
            provider=EmbeddingProvider(settings);vector=[1.0]+[0.0]*63
            with closing(sqlite3.connect(path)) as c:
                c.execute('CREATE TABLE vectors(cache_key TEXT PRIMARY KEY,vector TEXT,receipt TEXT)')
                c.execute('INSERT INTO vectors VALUES(?,?,?)',(provider.cache_key('a'),json.dumps(vector),json.dumps({'origin':'offline_stub','model':'text-embedding-v4','dimensions':64})))
                c.commit()
            before=path.read_bytes();r=cache_survey(['a','b'],settings)
            self.assertEqual(r['cached_real_queries'],0);self.assertEqual(r['new_request_upper_bound'],1)
            self.assertEqual(path.read_bytes(),before)

    @unittest.skipUnless(importlib.util.find_spec('chromadb'),'Full evaluator needs Chroma when real cache exists')
    def test_default_evaluator_has_no_network_even_with_authorization_number_only(self):
        from scripts.evaluate_v352_rag import evaluate
        from target.v352_validation import ROOT
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts/runtime') as folder,patch('target.embeddings.EmbeddingProvider._request',side_effect=AssertionError('No API')) as request:
            out=Path(folder)/'result'
            evaluate(out,run=False,authorize=5);request.assert_not_called()
            report=json.loads((out/'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['new_embedding_requests_this_command'],0)
            self.assertTrue(report['source_index_unchanged'])

    def test_real_origin_cache_also_requires_receipt_vector_hash(self):
        from target.embeddings import EmbeddingProvider,EmbeddingSettings
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cache.db';settings=EmbeddingSettings(base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',dimensions=64,cache=path)
            p=EmbeddingProvider(settings);vector=[1.0]+[0.0]*63
            receipt={'origin':'real_api','model':'text-embedding-v4','dimensions':64,'vector_hashes':['wrong-hash']}
            with closing(sqlite3.connect(path)) as c:
                c.execute('CREATE TABLE vectors(cache_key TEXT PRIMARY KEY,vector TEXT,receipt TEXT)')
                c.execute('INSERT INTO vectors VALUES(?,?,?)',(p.cache_key('a'),json.dumps(vector),json.dumps(receipt)));c.commit()
            self.assertEqual(cache_survey(['a'],settings)['cached_real_queries'],0)
            receipt['vector_hashes']=[hashlib.sha256(json.dumps(vector,separators=(',',':')).encode()).hexdigest()]
            with closing(sqlite3.connect(path)) as c:
                c.execute('UPDATE vectors SET receipt=?',(json.dumps(receipt),));c.commit()
            self.assertEqual(cache_survey(['a'],settings)['cached_real_queries'],1)


class VersionAndFidelityTests(unittest.TestCase):
    def hit(self,version='current'):
        return [{'doc_id':'P11','title':'锁座','content':'模拟锁座有效期15分钟。','version':version}]

    def test_stale_positive_citation_is_rejected(self):
        r=check_answer('锁座有效期15分钟[P11]',self.hit('old'),policy_versions={'P11':'current'})
        self.assertEqual(r['status'],'failed');self.assertEqual(r['findings'][0]['type'],'stale_policy_version')

    def test_current_version_does_not_prove_full_semantics(self):
        r=check_answer('锁座有效期15分钟[P11]',self.hit(),policy_versions={'P11':'current'})
        self.assertNotEqual(r['status'],'failed');self.assertEqual(r['full_semantic_faithfulness'],'indeterminate')

    def test_missing_version_requires_review(self):
        hits=self.hit();hits[0].pop('version')
        r=check_answer('锁座有效期15分钟[P11]',hits,policy_versions={'P11':'current'})
        self.assertIn('policy_version_metadata_missing',[x['reason'] for x in r['manual_review']])

    def test_negative_old_version_reference_is_not_an_asserted_policy(self):
        r=check_answer('无法确认，旧版P11未涉及当前规则。',self.hit('old'),policy_versions={'P11':'current'})
        self.assertFalse(any(f['type']=='stale_policy_version' for f in r['findings']))

    def test_omitted_time_condition_remains_manual_review(self):
        hits=[{'doc_id':'P01','content':'开车前48小时以上退票，收取5%手续费。'}]
        r=check_answer('退票收取5%手续费[P01]',hits)
        self.assertIn('conditional_policy_scope_omitted',[x['reason'] for x in r['manual_review']])

    def test_correct_refusal_with_empty_evidence(self):
        r=check_answer('没有相关证据，无法确认保险理赔金额。',[])
        self.assertTrue(r['no_evidence_refusal']);self.assertFalse(r['findings'])
