"""Actual SDK + create_agent protocol; every model response is explicit MockTransport.

No request goes to a model service. Frozen real evidence is a replay fixture, not
a newly executed real retrieval. The independent keyword cases execute new RAG.
"""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT=Path(__file__).resolve().parent.parent
try:
    import httpx
    from langchain_openai import ChatOpenAI
    from langchain_deepseek import ChatDeepSeek
    from target.agent import Agent
    AVAILABLE=True
except ImportError:AVAILABLE=False


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@unittest.skipUnless(AVAILABLE,'Full SDK environment required; all model HTTP is offline MockTransport')
class V351AgentRagTests(unittest.TestCase):
    def exercise(self,provider,*,frozen=None,empty=False):
        import config
        from target import bailian_runtime,deepseek_runtime
        from scripts.prepare_v351_acceptance import QUESTION
        from target.rag_service import retrieve
        label='bailian' if provider=='qwen' else 'deepseek'
        model_id='qwen3.8-flash' if provider=='qwen' else 'deepseek-flash'
        endpoint='https://dashscope.aliyuncs.com/compatible-mode/v1' if provider=='qwen' else 'https://api.deepseek.com'
        key='offline-v351-sdk-fixture-only'
        reply='根据 P11，模拟锁座有效期为15分钟；过期未支付自动释放库存。' if not empty else '现有检索证据为空，无法确认这项政策。'
        call_id='fixture-policy-'+provider
        question=QUESTION if not empty else '票务保险最高赔偿金额是多少？'
        call={'id':call_id,'type':'function','function':{'name':'search_policy','arguments':json.dumps({'question':question},ensure_ascii=False)}}
        def response(message):
            return {'id':'explicit-offline-fixture','object':'chat.completion','created':1,'model':model_id,
                'choices':[{'index':0,'message':{'role':'assistant',**message},'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}],
                'usage':{'prompt_tokens':13,'completion_tokens':5,'total_tokens':18}}
        payloads=[]
        def respond(request):
            payloads.append(json.loads(request.content))
            if len(payloads)>2:raise AssertionError('No third model request allowed, even to the stub')
            return httpx.Response(200,json=response({'content':None,'tool_calls':[call]} if len(payloads)==1 else {'content':reply}))
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            env={'DASHSCOPE_API_KEY':key,'DEEPSEEK_API_KEY':key,'DASHSCOPE_MODEL':model_id,'DASHSCOPE_BASE_URL':endpoint,
                 'BAILIAN_BUDGET_PATH':str(folder/'qwen.db'),'BAILIAN_MAX_REQUESTS':'2','BAILIAN_MAX_MODEL_CALLS':'2',
                 'DEEPSEEK_BUDGET_PATH':str(folder/'deepseek.db'),'DEEPSEEK_MAX_REQUESTS':'2','DEEPSEEK_MAX_MODEL_CALLS':'2',
                 'DEEPSEEK_THINKING':'disabled','DEEPSEEK_LIVE_TEST_PROFILE':'read_only','AGENT_MUTATIONS':'{}',
                 'TICKET_INITIAL_LIVE_BUDGET':str(folder/'shared.db'),'TICKET_TOTAL_REQUEST_LIMIT':'2',
                 'AGENT_RAG_MODE':'vector' if frozen is not None or empty else 'keyword','RAG_ALLOW_NETWORK':'0',
                 'RAG_QUALITY_PROFILE':'v351','TICKET_CASE_ID':'v351-offline-policy-'+provider,
                 'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false','TICKET_DISABLE_LOCAL_SECRETS':'1'}
            cfg={'PROVIDER':label,'ENGINE':'langchain','LC_TOOLSET':'read_only','MODEL_NAME':model_id,'BASE_URL':endpoint,
                 'API_KEY':key,'DB_PATH':folder/'tickets.db','TRACE_DIR':folder/'traces','USE_HTTP_MOCK':False,
                 'USE_VECTOR_RAG':False,'MAX_STEPS':2}
            with patch.dict(os.environ,env),patch.multiple(config,**cfg),patch.object(socket,'create_connection',side_effect=AssertionError('No sockets in offline acceptance')):
                from data.seed import build_db
                with contextlib.redirect_stdout(io.StringIO()):build_db()
                runtime=bailian_runtime if provider=='qwen' else deepseek_runtime
                model=runtime.make_model(runtime.Settings.from_env(),transport=httpx.MockTransport(respond))
                try:
                    with contextlib.ExitStack() as stack:
                        embedding=stack.enter_context(patch('target.embeddings.EmbeddingProvider._request',side_effect=AssertionError('No Embedding request allowed')))
                        # A frozen vector result retains real historical provenance, but
                        # the index itself is an explicitly declared replay fixture.
                        if frozen is not None or empty:
                            fixture=copy.deepcopy(frozen) if frozen is not None else {
                                'question':question,'mode':'vector','hits':[],'embedding_origin':'real_api',
                                'embedding_model':'text-embedding-v4','index_version':'empty-fixture',
                                'embedding_latency_ms':0,'total_latency_ms':0,'embedding_receipts':[]}
                            index=stack.enter_context(patch('target.rag_service.configured_index'))
                            index.return_value.retrieve.return_value=fixture
                        stack.enter_context(patch.object(Agent,'_chat',side_effect=AssertionError('Legacy Mock path must not execute')))
                        stack.enter_context(patch('target.rag.keyword_search',side_effect=AssertionError('Legacy policy keyword path must not execute')))
                        agent=Agent(model=model)
                        result=agent.chat('v351-'+provider+'-'+uuid.uuid4().hex,question)
                        embedding.assert_not_called()
                        if frozen is not None or empty:
                            index.return_value.retrieve.assert_called_once()
                            self.assertFalse(index.return_value.retrieve.call_args.kwargs['allow_network'])
                            self.assertTrue(index.return_value.retrieve.call_args.kwargs['require_real'])
                    self.assertEqual(len(payloads),2)
                    self.assertEqual({t['function']['name'] for t in payloads[0]['tools']},{'query_tickets','search_policy'})
                    tool_messages=[m for m in payloads[1]['messages'] if m['role']=='tool']
                    self.assertEqual(len(tool_messages),1);self.assertEqual(tool_messages[0]['tool_call_id'],call_id)
                    tool_result=json.loads(tool_messages[0]['content'])
                    self.assertEqual(tool_result['question'],question)
                    self.assertEqual(set(tool_result),{'question','hits','count'})
                    self.assertEqual(tool_result['count'],len(tool_result['hits']))
                    self.assertEqual(set(result),{'session_id','provider','model','user_msg','steps','tool_sequence','reply','finish_reason','tokens','total_latency_ms'})
                    self.assertEqual(set(result['steps'][0]['calls'][0]),{'tool','args','ok','latency_ms','result_preview'})
                    self.assertEqual(result['tool_sequence'],['search_policy']);self.assertEqual(result['reply'],reply)
                    self.assertEqual(result['finish_reason'],'stop')
                    self.assertEqual(result['steps'][0]['calls'][0]['args'],{'question':question})
                    self.assertTrue(result['steps'][0]['calls'][0]['ok'])
                    events=agent.langchain_engine.last_events
                    http_ids=[e['request_id'] for e in events if e['event']=='http_request']
                    self.assertEqual(len(http_ids),2);self.assertEqual(len(set(http_ids)),2)
                    self.assertTrue(all(len(uid)==32 for uid in http_ids))
                    model_call=next(e for e in events if e['event']=='model_response')['tool_calls'][0]
                    execution=next(e for e in events if e['event']=='tool_end')
                    self.assertEqual(model_call['id'],call_id);self.assertEqual(model_call['args'],{'question':question})
                    self.assertEqual(execution['call_id'],call_id);self.assertTrue(execution['executed']);self.assertTrue(execution['ok'])
                    self.assertEqual(execution['result'],tool_result)
                    self.assertLess(next(i for i,e in enumerate(events) if e['event']=='tool_end'),next(i for i,e in enumerate(events) if e['event']=='model_final'))
                    public=json.loads((config.TRACE_DIR/'traces.jsonl').read_text(encoding='utf-8').splitlines()[0])
                    provider_record=json.loads((config.TRACE_DIR/'provider_runs.jsonl').read_text(encoding='utf-8').splitlines()[0])
                    rag=[json.loads(line) for line in (config.TRACE_DIR/'rag_runs.jsonl').read_text(encoding='utf-8').splitlines()]
                    retrieval=next(r for r in rag if r['schema']=='ticket-rag-retrieval/1')
                    answer=next(r for r in rag if r['schema']=='ticket-rag-answer/1')
                    self.assertEqual(public,result)
                    self.assertEqual(provider_record['trace_id'],retrieval['trace_id']);self.assertEqual(answer['trace_id'],retrieval['trace_id'])
                    self.assertEqual(retrieval['call_id'],call_id);self.assertEqual(answer['original_model_reply'],reply)
                    self.assertEqual(provider_record['requested_model'],model_id)
                    self.assertEqual(provider_record['remote_status'],'not_attempted')
                    self.assertEqual(provider_record['actual_models'],[model_id])
                    self.assertEqual(provider_record['tokens'],{'prompt':26,'completion':10})
                    self.assertIsNone(provider_record['business_success'])
                    if not empty:self.assertIn('P11',[h['doc_id'] for h in tool_result['hits']])
                    else:self.assertEqual(tool_result['hits'],[])
                    with contextlib.closing(sqlite3.connect(config.DB_PATH)) as connection:self.assertEqual(connection.execute('SELECT COUNT(*) FROM orders').fetchone()[0],0)
                    record={'schema':'ticket-v351-offline-agent/1','evidence_mode':'offline_sdk_mock_transport',
                        'real_model_requests':0,'embedding_requests':0,'provider':label,'requested_model':model_id,
                        'retrieval_execution':'frozen_real_evidence_replay_fixture' if frozen is not None else 'empty_retrieval_fixture' if empty else 'new_RAG_keyword_actual_execution',
                        'question':question,'tool_call_id':call_id,'request_ids':http_ids,'tool_result_sha256':digest(tool_result),
                        'tool_result':tool_result,'original_model_reply':reply,'public_trace':result,'provider_trace':provider_record,
                        'rag_sidecars':rag,'model_request_payloads':payloads,'assertions':['two SDK requests, both intercepted by MockTransport',
                        'actual create_agent executes search_policy and returns matching ToolMessage ID','new RAG route used; no legacy Agent loop',
                        'public ten/five fields unchanged','provider/public/RAG trace IDs linked','no Embedding request and no simulated order writes'],
                        'judgement':'passed','limits':'The adapter raw provider_trace mode=live labels the SDK execution path, not a real service request; this wrapper marks fixture provenance explicitly.'}
                    self.assertNotIn(key,json.dumps(record,ensure_ascii=False))
                    output=os.getenv('V351_AGENT_EVIDENCE_OUT')
                    if output:
                        out=Path(output).resolve()
                        self.assertTrue(out.is_relative_to(ROOT/'artifacts/runtime'))
                        out.mkdir(parents=True,exist_ok=True)
                        name=provider+'-'+('frozen' if frozen is not None else 'empty' if empty else 'keyword')+'-'+uuid.uuid4().hex+'.json'
                        (out/name).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                    return record
                finally:model.root_client.close()

    def test_qwen_new_rag_keyword_actual_sdk_roundtrip(self):self.exercise('qwen')

    def test_deepseek_new_rag_keyword_actual_sdk_roundtrip(self):self.exercise('deepseek')

    def test_both_providers_receive_identical_frozen_real_evidence(self):
        source=json.loads((ROOT/'docs/evidence/v35/live/generation-result.json').read_text(encoding='utf-8'))
        frozen=next(r['frozen_retrieval_evidence'] for r in source['records'] if r.get('scenario')=='RQ01')
        left=self.exercise('qwen',frozen=frozen);right=self.exercise('deepseek',frozen=frozen)
        self.assertEqual(left['tool_result_sha256'],right['tool_result_sha256'])
        self.assertEqual(left['model_request_payloads'][0]['messages'],right['model_request_payloads'][0]['messages'])
        self.assertEqual(left['model_request_payloads'][0]['tools'],right['model_request_payloads'][0]['tools'])
        self.assertNotEqual(left['public_trace']['session_id'],right['public_trace']['session_id'])
        self.assertNotEqual(left['provider_trace']['trace_id'],right['provider_trace']['trace_id'])

    def test_both_providers_empty_evidence_can_refuse_without_fabrication(self):
        for provider in ('qwen','deepseek'):
            with self.subTest(provider=provider):self.exercise(provider,empty=True)


class V351AcceptancePlanTests(unittest.TestCase):
    def test_plan_only_reads_saved_evidence_and_budget(self):
        from scripts.prepare_v351_acceptance import plan
        with patch.object(socket,'create_connection',side_effect=AssertionError('plan must not use a socket')):
            result=plan()
        self.assertEqual(result['execution_status'],'not_run');self.assertEqual(result['network_requests'],0)
        self.assertFalse(result['reads_api_keys']);self.assertFalse(result['has_execution_switch'])
        self.assertEqual(result['minimum_new_authorization']['total_generation'],4)
        self.assertEqual(result['minimum_new_authorization']['embedding'],0)
        self.assertIn('P11',[h['doc_id'] for h in result['frozen_evidence']['tool_result']['hits']])

    def test_plan_has_no_live_execution_flag(self):
        from scripts.prepare_v351_acceptance import main
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as raised:main(['--run'])
        self.assertEqual(raised.exception.code,2)
