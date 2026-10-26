"""New policy guard exercised through real SDK/create_agent with offline HTTP stubs."""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import unittest
from unittest.mock import patch
import uuid

try:
    import test_deepseek_agent as deep
    import test_live_providers as qwen
    AVAILABLE=deep.AVAILABLE and qwen.AVAILABLE
except ImportError:AVAILABLE=False

ROOT=Path(__file__).resolve().parent.parent


@unittest.skipUnless(AVAILABLE,'Full SDK environment required; no model-service requests are made')
class V351GuardIntegrationTests(unittest.TestCase):
    def run_wrong_duration(self,provider):
        import config
        from target.deepseek_runtime import DeepSeekError
        fixture=(qwen.LiveProviderTests if provider=='qwen' else deep.DeepSeekAgentTests)()
        with contextlib.redirect_stdout(io.StringIO()):fixture.setUp()
        try:
            reply='依据 P11，模拟锁座有效期为45分钟。'
            question='锁座后多久必须完成支付？'
            model='qwen3.8-flash' if provider=='qwen' else 'deepseek-flash'
            first=fixture.response({'content':None,'tool_calls':[fixture.call('search_policy',{'question':question})]})
            last=fixture.response({'content':reply})
            first['model']=last['model']=model
            env={'AGENT_RAG_MODE':'keyword','RAG_QUALITY_PROFILE':'v351','RAG_ALLOW_NETWORK':'0',
                 'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false','TICKET_DISABLE_LOCAL_SECRETS':'1',
                 'TICKET_INITIAL_LIVE_BUDGET':'','DASHSCOPE_MODEL':model}
            with patch.dict(os.environ,env),patch.object(config,'MODEL_NAME',model),\
                    patch.object(socket,'create_connection',side_effect=AssertionError('No network in offline guard test')),\
                    patch('target.rag.keyword_search',side_effect=AssertionError('Must execute the new RAG route')),\
                    patch('target.embeddings.EmbeddingProvider._request',side_effect=AssertionError('No Embedding calls allowed')) as embedding:
                agent=fixture.agent([first,last])
                with self.assertRaisesRegex(DeepSeekError,'rag_answer_inconsistent'):
                    agent.chat('v351-guard-'+provider,question)
                self.assertEqual(len(fixture.payloads),2);embedding.assert_not_called()
                # The backend produced the correct rule, then the stub model contradicted it.
                returned=next(m for m in fixture.payloads[1]['messages'] if m['role']=='tool')
                tool_result=json.loads(returned['content'])
                p11=next(h for h in tool_result['hits'] if h['doc_id']=='P11')
                self.assertIn('15',p11['content']);self.assertNotIn('45',p11['content'])
                self.assertEqual(tool_result['question'],question)
                self.assertEqual(set(tool_result),{'question','hits','count'})
                self.assertEqual(returned['tool_call_id'],first['choices'][0]['message']['tool_calls'][0]['id'])
                engine=agent.langchain_engine;record=engine.last_live_run
                self.assertEqual(record['error']['category'],'rag_answer_inconsistent')
                self.assertFalse(record['agent_completed']);self.assertFalse(record['local_trace_saved'])
                self.assertIsNone(record['business_success']);self.assertIsNone(record['public_trace'])
                self.assertIsNone(record['reply'])
                events=record['events'];final=next(e for e in events if e['event']=='model_final')
                self.assertEqual(final['text'],reply)
                self.assertEqual(final['rag_answer_check']['status'],'failed')
                execution=next(e for e in events if e['event']=='tool_end')
                self.assertEqual(execution['tool'],'search_policy');self.assertTrue(execution['executed']);self.assertTrue(execution['ok'])
                self.assertEqual(execution['result'],tool_result)
                rag=[json.loads(line) for line in (config.TRACE_DIR/'rag_runs.jsonl').read_text(encoding='utf-8').splitlines()]
                answer=next(r for r in rag if r['schema']=='ticket-rag-answer/1')
                retrieval=next(r for r in rag if r['schema']=='ticket-rag-retrieval/1')
                self.assertEqual(retrieval['trace_id'],record['trace_id']);self.assertEqual(answer['trace_id'],record['trace_id'])
                self.assertEqual(answer['original_model_reply'],reply);self.assertFalse(answer['business_success'])
                check=answer['faithfulness_check']
                self.assertEqual(check['original_model_reply'],reply);self.assertEqual(check['status'],'failed')
                finding=next(f for f in check['findings'] if f['type']=='unsupported_quantity_or_scope')
                self.assertEqual(finding['cited_doc_ids'],['P11'])
                self.assertTrue(any(q['dimension']=='duration' and q['value']=='45' for q in finding['missing_quantities']))
                self.assertTrue(any('15' in row['text'] for row in finding['evidence']))
                self.assertEqual(check['full_semantic_faithfulness'],'indeterminate')
                self.assertFalse((config.TRACE_DIR/'traces.jsonl').exists(),'Failure must not create a successful public trace')
                saved=json.loads((config.TRACE_DIR/'provider_runs.jsonl').read_text(encoding='utf-8').splitlines()[0])
                self.assertEqual(saved['events'],events)
                with contextlib.closing(sqlite3.connect(config.DB_PATH)) as connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM orders').fetchone()[0],0)
                exported={'schema':'ticket-v351-guard-integration/1','evidence_mode':'offline_sdk_mock_transport',
                    'provider':provider,'requested_model':model,'question':question,'authoritative_tool_result':tool_result,
                    'original_model_reply':reply,'expected_error':'rag_answer_inconsistent','observed_error':record['error'],
                    'field_finding':finding,'faithfulness_check':check,'provider_trace':record,'rag_sidecars':rag,
                    'assertions':['correct 15-minute tool result returned to SDK','45-minute model claim rejected after tool success',
                        'original model text retained unchanged','failure sidecars linked by trace ID','no fabricated public success and no order writes'],
                    'judgement':'passed','new_real_generation_requests':0,'new_embedding_requests':0,
                    'limits':'The model reply and token usage are explicit fixtures; raw adapter mode=live is not a new online run.'}
                output=os.getenv('V351_AGENT_EVIDENCE_OUT')
                if output:
                    out=Path(output).resolve();self.assertTrue(out.is_relative_to(ROOT/'artifacts/runtime'))
                    out.mkdir(parents=True,exist_ok=True)
                    (out/('guard-'+provider+'-'+uuid.uuid4().hex+'.json')).write_text(json.dumps(exported,ensure_ascii=False,indent=2),encoding='utf-8')
        finally:fixture.tearDown()

    def test_qwen_unsupported_duration_fails_without_rewriting_original(self):self.run_wrong_duration('qwen')

    def test_deepseek_unsupported_duration_fails_without_rewriting_original(self):self.run_wrong_duration('deepseek')
