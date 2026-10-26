"""Finite relevance guard and rank fusion tests, independent of final holdout scores."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from target.rag_relevance import apply_quality,scope_requirements
from target.rag_store import documents,keyword,ROOT


class QualityGuardTests(unittest.TestCase):
    def setUp(self):self.chunks=documents(ROOT/'data/policies.md')
    def lexical(self,q):return keyword(self.chunks,q,k=20)

    def test_independent_frozen_sets_and_original_thirty_unchanged(self):
        original=ROOT/'cases/rag_quality_v35.json'
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),'375a751649d6bcebe43102dd2c80c28ec95d073375ea651d6a8674db4987b6f9')
        dev=json.loads((ROOT/'cases/rag_quality_v351_development.json').read_text(encoding='utf-8'))
        hold=json.loads((ROOT/'cases/rag_quality_v351_holdout.json').read_text(encoding='utf-8'))
        for x in (dev,hold):
            self.assertEqual(len(x['cases']),24);self.assertEqual(sum(not c['expected_doc_ids'] for c in x['cases']),16)
        self.assertFalse({c['question'] for c in dev['cases']}&{c['question'] for c in hold['cases']})

    def test_equal_weight_tie_is_resolved_by_explicit_vector_weight(self):
        def h(uid,score):return {'doc_id':uid,'content':'政策','score':score}
        lex=[h('P02',4),h('P03',3)];vec=[h('P03',0.8),h('P02',0.7)]
        r=apply_quality('高铁票改签规则',lex,vec,'hybrid')
        self.assertEqual(r['hits'][0]['doc_id'],'P03')
        self.assertAlmostEqual(r['hits'][0]['score'],0.3/62+0.7/61)
        self.assertEqual(r['hits'][0]['fusion_ranks'],{'keyword':2,'vector':1})

    def test_vector_empty_does_not_resurrect_keyword_noise(self):
        q='锁座有效期';r=apply_quality(q,self.lexical(q),[],'hybrid')
        self.assertEqual(r['hits'],[]);self.assertTrue(r['candidate_hits'])
        self.assertTrue(r['sufficiency']['abstain_recommended'])

    def test_no_topic_character_overlap_is_insufficient(self):
        q='上海明日天气温度是多少';r=apply_quality(q,self.lexical(q),[],'keyword')
        self.assertEqual(r['hits'],[]);self.assertEqual(r['sufficiency']['state'],'insufficient_evidence')

    def test_air_rail_scope_does_not_transfer_baggage_allowance(self):
        q='航空经济舱托运行李规则';r=apply_quality(q,self.lexical(q),self.lexical(q),'vector')
        self.assertEqual(r['hits'],[]);self.assertEqual(r['sufficiency']['transport_scope'],'air')

    def test_generic_supported_policy_keeps_evidence(self):
        q='锁座有效期与未支付订单取消收费'
        r=apply_quality(q,self.lexical(q),[],'keyword')
        self.assertEqual({h['doc_id'] for h in r['hits']},{'P11','P12'})
        self.assertFalse(r['sufficiency']['abstain_recommended'])

    def test_missing_personal_conditions_recommend_clarification(self):
        q='我这张票实际退多少元';r=apply_quality(q,self.lexical(q),[],'keyword')
        self.assertEqual(r['hits'],[]);self.assertTrue(r['sufficiency']['needs_clarification'])

    def test_elliptical_refund_is_not_lost_when_change_is_mentioned(self):
        r=scope_requirements('已经开车还能退吗，改签有什么时间限制？')
        self.assertTrue({'P01','P03'}.issubset(r['allowed_policy_ids']))

    def test_query_attribute_not_supplied_by_same_topic(self):
        q='锁座支付可以信用卡分期吗';r=apply_quality(q,self.lexical(q),[],'keyword')
        self.assertEqual(r['hits'],[]);self.assertIn('instalments',r['sufficiency']['unsupported_attributes'])

    def test_inputs_and_rejected_evidence_are_preserved(self):
        q='高铁行李';lex=self.lexical(q);vec=copy.deepcopy(lex);before=copy.deepcopy([lex,vec])
        r=apply_quality(q,lex,vec,'hybrid')
        self.assertEqual([lex,vec],before);self.assertTrue(r['rejections'])
        self.assertEqual({h['doc_id'] for h in r['candidate_hits']},{h['doc_id'] for h in lex})

    def test_invalid_parameters_are_not_silently_coerced(self):
        for kwargs in ({'k':0},{'vector_weight':1},{'min_keyword_score':-1}):
            with self.assertRaises(ValueError):apply_quality('锁座',[],[],'hybrid',**kwargs)

    def test_new_service_empty_result_keeps_public_tool_contract_and_sidecar(self):
        import config
        from target.rag_service import retrieve
        with tempfile.TemporaryDirectory() as folder,patch.object(config,'TRACE_DIR',Path(folder)),patch.dict(os.environ,{'AGENT_RAG_MODE':'keyword','RAG_QUALITY_PROFILE':'v351'}),patch('target.embeddings.EmbeddingProvider._request') as request:
            result=retrieve('列车晚点赔偿的最高金额是多少')
            self.assertEqual(set(result),{'question','hits','count'});self.assertEqual(result['count'],0)
            record=json.loads((Path(folder)/'rag_runs.jsonl').read_text(encoding='utf-8'))
            self.assertEqual(record['quality_profile'],'v351');self.assertTrue(record['candidate_hits'])
            self.assertEqual(record['sufficiency']['state'],'insufficient_evidence');request.assert_not_called()

    def test_explicit_v35_compatibility_profile_preserves_raw_keyword(self):
        import config
        from target.rag_service import retrieve
        q='杭州明天会不会下雨？'
        with tempfile.TemporaryDirectory() as folder,patch.object(config,'TRACE_DIR',Path(folder)),patch.dict(os.environ,{'RAG_QUALITY_PROFILE':'v35'}):
            r=retrieve(q,mode='keyword');self.assertTrue(r['hits'])

    def test_new_live_entry_defaults_are_cache_only_and_quality_profile_explicit(self):
        from target.live_providers import isolated_environment
        with patch.dict(os.environ,{'DASHSCOPE_MODEL':'qwen3.8-flash'}):
            for provider in ('deepseek','bailian'):
                env=isolated_environment(provider,ROOT/'artifacts/runtime/v351-test-entry',profile='v34')
                self.assertEqual(env['AGENT_RAG_MODE'],'hybrid');self.assertEqual(env['RAG_ALLOW_NETWORK'],'0')
                self.assertEqual(env['RAG_QUALITY_PROFILE'],'v351')
