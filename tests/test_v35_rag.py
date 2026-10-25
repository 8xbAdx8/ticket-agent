"""A-owned RAG tests. MockTransport vectors are explicitly offline_stub, never Live."""
import copy
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import httpx
    HTTP=True
except ImportError:HTTP=False
CHROMA=importlib.util.find_spec('chromadb') is not None
from target.embeddings import EmbeddingProvider,EmbeddingSettings,EmbeddingError
from target.rag_store import PolicyIndex,RagError,documents,keyword


@unittest.skipUnless(HTTP,'httpx required; no remote requests')
class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'DASHSCOPE_API_KEY':'offline-embedding-key','TICKET_DISABLE_LOCAL_SECRETS':'1'})
        self.env.start();self.calls=[]
        self.settings=EmbeddingSettings(dimensions=64,base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
                                        ledger=self.root/'requests.db',cache=self.root/'cache.db')
    def tearDown(self):self.env.stop();self.tmp.cleanup()

    def response(self,request):
        b=json.loads(request.content);self.calls.append(b);d=b['dimensions']
        data=[]
        for i,t in enumerate(b['input']):
            slot=0 if ('支付' in t or '锁座' in t) else 1 if '退票' in t else 2
            v=[0.0]*d;v[slot]=1.0
            data.append({'index':i,'embedding':v})
        return httpx.Response(200,json={'model':'text-embedding-v4','data':list(reversed(data)),
                                       'usage':{'total_tokens':11}},headers={'x-request-id':'fixture-server'})

    def provider(self,handler=None,settings=None):
        return EmbeddingProvider(settings or self.settings,transport=httpx.MockTransport(handler or self.response))

    def test_batches_cache_provenance_and_reordered_response(self):
        p=self.provider();texts=['支付'+str(i) for i in range(15)]
        vectors=p.embed_many(texts,allow_network=True)
        self.assertEqual(len(self.calls),2);self.assertEqual(len(vectors),15)
        p.embed_many(texts,allow_network=False);self.assertEqual(len(self.calls),2)
        self.assertEqual(p.budget.snapshot()['used'],2)
        self.assertTrue(all(r['origin']=='offline_stub' and r['tokens']==11 for r in p.last_receipts))

    def test_key_missing_and_explicit_network_gate(self):
        p=self.provider()
        with self.assertRaisesRegex(EmbeddingError,'explicit_network_required'):p.embed_many(['test'])
        with patch.dict(os.environ,{'DASHSCOPE_API_KEY':''}),self.assertRaisesRegex(EmbeddingError,'missing_DASHSCOPE_API_KEY'):
            p.embed_many(['test'],allow_network=True)
        self.assertEqual(p.budget.snapshot()['used'],0);self.assertEqual(self.calls,[])

    def test_failures_consumed_once_no_retry_and_no_key_in_ledger(self):
        calls=[]
        def error(req):calls.append(req);return httpx.Response(401,json={'error':{'message':'offline-embedding-key'}})
        p=self.provider(error)
        with self.assertRaisesRegex(EmbeddingError,'authentication_failed'):p.embed_many(['a'],allow_network=True)
        self.assertEqual(len(calls),1);self.assertEqual(p.budget.snapshot()['used'],1)
        self.assertNotIn('offline-embedding-key',json.dumps(p.budget.snapshot()))

    def test_budget_exhaustion_prevents_http_and_cannot_increase_cap(self):
        p=self.provider(settings=replace(self.settings,limit=1))
        p.embed_many(['a'],allow_network=True)
        with self.assertRaisesRegex(EmbeddingError,'budget_exhausted'):p.embed_many(['b'],allow_network=True)
        self.assertEqual(len(self.calls),1)
        q=self.provider()
        with self.assertRaisesRegex(EmbeddingError,'persisted_budget_limit_mismatch'):q.embed_many(['b'],allow_network=True)

    def test_unknown_usage_not_zero(self):
        def respond(req):
            r=self.response(req);d=r.json();d.pop('usage');return httpx.Response(200,json=d)
        p=self.provider(respond);p.embed_many(['x'],allow_network=True)
        self.assertIsNone(p.budget.snapshot()['requests'][0]['tokens'])

    def test_dimension_malformed_response_no_success(self):
        p=self.provider(lambda req:httpx.Response(200,json={'data':[{'index':0,'embedding':[1.0]}]}))
        with self.assertRaisesRegex(EmbeddingError,'invalid_embedding_vectors'):p.embed_many(['x'],allow_network=True)
        self.assertEqual(p.budget.snapshot()['requests'][0]['status'],200)
        self.assertEqual(p.budget.snapshot()['requests'][0]['category'],'invalid_embedding_vectors')

    def test_timeout_no_retry(self):
        calls=[]
        def timeout(req):calls.append(req);raise httpx.ReadTimeout('private response body')
        p=self.provider(timeout)
        with self.assertRaisesRegex(EmbeddingError,'timeout'):p.embed_many(['x'],allow_network=True)
        self.assertEqual(len(calls),1);self.assertEqual(p.budget.snapshot()['used'],1)

    def test_endpoint_and_input_validation_without_requests(self):
        for address in ('https://secret@dashscope.aliyuncs.com/compatible-mode/v1','http://dashscope.aliyuncs.com/compatible-mode/v1',
                        'https://attacker.invalid/compatible-mode/v1','https://dashscope.aliyuncs.com/compatible-mode/v1?key=x'):
            with self.assertRaises(EmbeddingError):self.provider(settings=replace(self.settings,base_url=address))
        with self.assertRaises(EmbeddingError):self.provider().embed_many(['x'*8001],allow_network=True)
        self.assertEqual(self.calls,[])


@unittest.skipUnless(CHROMA and HTTP,'Chroma only installed in .venv-v35')
class StoreTests(EmbeddingTests):
    # Reuse fixture helpers without duplicating inherited test methods below.
    pass


def store_test(method):
    def run(self):
        provider=self.provider();index=PolicyIndex(self.root/'index',provider=provider)
        try:method(self,index,provider)
        finally:
            try:index.client()._system.stop()
            except Exception:pass
    return run


def persistence(t,i,p):
    a=i.build(allow_network=True);t.assertEqual(a['chunk_count'],15);t.assertEqual(a['embedding_origin'],'offline_stub')
    t.assertTrue((i.path/'chroma.sqlite3').exists());before=len(t.calls)
    b=PolicyIndex(i.path,provider=p).build();t.assertTrue(b['reused']);t.assertEqual(len(t.calls),before)
    with t.assertRaisesRegex(RagError,'test_index_forbidden'):i.load(require_real=True)


def modes(t,i,p):
    i.build(allow_network=True);before=len(t.calls)
    a=i.retrieve('锁座支付',mode='vector',allow_network=True)
    b=i.retrieve('锁座支付',mode='hybrid',allow_network=False)
    t.assertEqual(a['hits'][0]['doc_id'],'P11');t.assertEqual(b['fusion'],'reciprocal_rank_fusion_k60')
    t.assertEqual(len({h['doc_id'] for h in b['hits']}),len(b['hits']))
    t.assertEqual(len(t.calls),before+1)


def dimension(t,i,p):
    i.build(allow_network=True)
    q=EmbeddingProvider(replace(p.settings,dimensions=128),transport=p.transport)
    with t.assertRaisesRegex(RagError,'incompatible_index'):PolicyIndex(i.path,provider=q).load()


def stale_incremental(t,i,p):
    corpus=t.root/'policies.md';corpus.write_text(i.policy.read_text(encoding='utf-8'),encoding='utf-8');i.policy=corpus
    i.build(allow_network=True);before=len(t.calls)
    corpus.write_text(corpus.read_text(encoding='utf-8').replace('15 分钟','16 分钟'),encoding='utf-8')
    with t.assertRaisesRegex(RagError,'rebuild_required'):i.load()
    a=i.build(allow_network=True,rebuild=True);t.assertEqual(len(t.calls),before+1);t.assertEqual(a['new_embedding_requests'],1)


def empty_corrupt(t,i,p):
    t.assertEqual(i.status()['state'],'unavailable')
    i.path.mkdir();(i.path/'manifest.json').write_text('{bad',encoding='utf-8')
    with t.assertRaisesRegex(RagError,'corrupt_index'):i.load()
    t.assertEqual(len(t.calls),0)


# Separate TestCase avoids unittest counting each inherited embedding test twice.
class ChromaStoreTests(unittest.TestCase):
    setUp=EmbeddingTests.setUp;tearDown=EmbeddingTests.tearDown
    response=EmbeddingTests.response;provider=EmbeddingTests.provider


ChromaStoreTests=unittest.skipUnless(CHROMA and HTTP,'Chroma only installed in .venv-v35')(ChromaStoreTests)
for _name,_method in [('persistence',persistence),('modes',modes),('dimension',dimension),('incremental',stale_incremental),('corrupt',empty_corrupt)]:
    setattr(ChromaStoreTests,'test_'+_name,store_test(_method))
del StoreTests


class CompatibilityTests(unittest.TestCase):
    def test_refusal_can_describe_irrelevant_retrieved_sources(self):
        from target.rag_quality import answer_metrics
        case={'expected_doc_ids':[],'allowed_citations':[],'answer_points':[]}
        hits=[{'doc_id':'P01','content':'退票手续费'}]
        r=answer_metrics(case,'无法确认。P01仅介绍退票手续费，未涉及保险。',hits)
        self.assertTrue(r['no_answer_refusal']);self.assertEqual(r['wrong_citations'],[])
        bad=answer_metrics(case,'无法确认，但保险可赔100元 P01。',hits)
        self.assertFalse(bad['no_answer_refusal']);self.assertEqual(bad['business_status'],'failed')
    @unittest.skipUnless(importlib.util.find_spec('langsmith') is not None,'optional LangSmith context import only')
    def test_live_acceptance_context_is_available_before_request(self):
        from langsmith import tracing_context
        self.assertTrue(callable(tracing_context))
    def test_qwen_default_and_explicit_legacy_model_are_distinct(self):
        from target.api_config import model_config
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop('DASHSCOPE_MODEL',None)
            self.assertEqual(model_config('bailian')['model'],'qwen3.8-flash')
            os.environ['DASHSCOPE_MODEL']='qwen-plus'
            self.assertEqual(model_config('bailian')['model'],'qwen-plus')

    def test_v35_four_request_cap_does_not_change_older_profiles(self):
        from target.bailian_runtime import Settings
        with patch.dict(os.environ,{'BAILIAN_MAX_REQUESTS':'4','TICKET_API_VALIDATION_PROFILE':'v35'}):
            self.assertEqual(Settings.from_env().max_requests,4)
            os.environ['TICKET_API_VALIDATION_PROFILE']='v34'
            with self.assertRaisesRegex(Exception,'invalid_safety_limits'):Settings.from_env()

    def test_fixed_dataset_metrics_and_unknown_faithfulness(self):
        from target.rag_store import ROOT
        from target.rag_quality import retrieval_metrics,answer_metrics,query_text
        cases=json.loads((ROOT/'cases/rag_quality_v35.json').read_text(encoding='utf-8'))['cases']
        self.assertEqual(len(cases),30)
        c=cases[0];hits=[{'doc_id':'P11','content':'模拟锁座有效期15分钟，过期释放库存'}]
        metric=retrieval_metrics([c],{c['id']:{'hits':hits}},3)
        self.assertEqual(metric['recall_at_k'],1);self.assertEqual(metric['mrr'],1)
        a=answer_metrics(c,'15分钟 P99',hits)
        self.assertEqual(a['business_status'],'failed');self.assertEqual(a['answer_faithfulness'],'indeterminate')
        self.assertIn('锁座',query_text(cases[28]))

    def test_chunk_ids_metadata_and_keyword_are_deterministic(self):
        from target.rag_store import ROOT
        chunks=documents(ROOT/'data/policies.md');self.assertEqual(len(chunks),15)
        self.assertEqual(chunks,documents(ROOT/'data/policies.md'))
        self.assertEqual(keyword(chunks,'锁座支付')[0]['doc_id'],'P11')
        self.assertTrue(all(all(k in c for k in ('doc_id','title','source','version','chunk_id')) for c in chunks))

    def test_wrong_citation_is_not_added_to_evidence(self):
        from target.rag_service import citation_check
        hits=[{'doc_id':'P11','content':'15分钟'}];before=copy.deepcopy(hits)
        r=citation_check('锁座15分钟 [P99]',hits)
        self.assertEqual(r['wrong_citations'],['P99']);self.assertEqual(hits,before)
        self.assertEqual(citation_check('无法确认',[])['faithfulness'],'indeterminate')
