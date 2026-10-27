"""Actual SDK + actual cached Chroma; all generation HTTP is explicit MockTransport."""
from contextlib import redirect_stdout
from dataclasses import replace
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

AVAILABLE=all(importlib.util.find_spec(n) for n in ('chromadb','langchain_deepseek','langchain_openai'))


@unittest.skipUnless(AVAILABLE,'Both SDKs and actual Chroma are required; never paid requests')
class PairProtocolTests(unittest.TestCase):
    def exercise(self,behavior,resume=False):
        import httpx
        import target.v352_validation as validation
        from scripts.verify_v352_live import execute_pair
        from target.embeddings import EmbeddingProvider
        from target.rag_protection import BASELINE,tree_hashes
        before=tree_hashes(BASELINE);payloads={};models=[]
        with tempfile.TemporaryDirectory(dir=validation.ROOT/'artifacts/runtime',ignore_cleanup_errors=True) as folder:
            auth=Path(folder)/'authorization'
            env={'DEEPSEEK_API_KEY':'offline-v352-only','DASHSCOPE_API_KEY':'offline-v352-only',
                'DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1','DASHSCOPE_MODEL':'qwen-plus',
                'TICKET_DISABLE_LOCAL_SECRETS':'1','LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'}
            def factory(provider,runtime):
                import config
                self.assertEqual(config.MODEL_NAME,'qwen3.8-flash' if provider=='bailian' else 'deepseek-flash')
                if resume and provider=='bailian' and not (auth/'paired-report.json').exists():
                    from target.deepseek_runtime import DeepSeekError
                    raise DeepSeekError('v352_model_identity_required')
                calls=payloads.setdefault(provider,[])
                model_id='qwen3.8-flash' if provider=='bailian' else 'deepseek-flash'
                def respond(request):
                    body=json.loads(request.content);calls.append(body)
                    if len(calls)>2:raise AssertionError('No third generation attempt')
                    if behavior=='timeout':raise httpx.ReadTimeout('fixture timeout')
                    if behavior=='no_tool':message={'content':'当前无法确认这项政策。'}
                    elif len(calls)==1:
                        message={'content':None,'tool_calls':[{'id':'policy-'+provider,'type':'function','function':{
                            'name':'search_policy','arguments':json.dumps({'question':validation.QUESTION},ensure_ascii=False)}}]}
                    else:message={'content':'模拟锁座有效期'+('45' if behavior=='wrong_answer' else '15')+'分钟 [P11]。'}
                    return httpx.Response(200,json={'id':'offline-sdk-stub','object':'chat.completion','created':1,'model':model_id,
                        'choices':[{'index':0,'message':{'role':'assistant',**message},'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}],
                        'usage':{'prompt_tokens':17,'completion_tokens':7,'total_tokens':24}})
                model=runtime.make_model(runtime.Settings.from_env(),transport=httpx.MockTransport(respond));models.append(model)
                return model
            with patch.object(validation,'AUTH',auth),patch.dict(os.environ,env),patch.object(EmbeddingProvider,'_request',side_effect=AssertionError('No Embedding API')) as embedding:
                with redirect_stdout(io.StringIO()):report=execute_pair(model_factory=factory)
                embedding.assert_not_called()
                for model in models:self.assertTrue(model.root_client.is_closed())
                self.assertEqual(report['evidence_mode'],'offline_sdk_stub');self.assertEqual(report['real_generation_requests'],0)
                self.assertTrue(report['source_index_unchanged']);self.assertEqual(tree_hashes(BASELINE),before)
                for row in report['records']:
                    self.assertLessEqual(row['generation_requests'],2);self.assertEqual(row['automatic_retries'],0)
                    self.assertFalse(row['real_function_calling_verified'])
                with self.assertRaises(FileExistsError),redirect_stdout(io.StringIO()):execute_pair(model_factory=factory)
                self.assertEqual(sum(len(rows) for rows in payloads.values()),sum(r['generation_requests'] for r in report['records']))
                if resume:
                    original=(auth/'paired-report.json').read_bytes();marker=(auth/'generation-attempt.json').read_bytes()
                    deep_ledger=(auth/'deepseek-generation.db').read_bytes()
                    deep_report=(auth/'runs/deepseek/report.json').read_bytes()
                    self.assertEqual(report['records'][0]['generation_requests'],0)
                    self.assertEqual(len(payloads['deepseek']),2)
                    with redirect_stdout(io.StringIO()):report=execute_pair(model_factory=factory,resume_unattempted_qwen=True)
                    self.assertEqual((auth/'paired-report.json').read_bytes(),original)
                    self.assertEqual((auth/'generation-attempt.json').read_bytes(),marker)
                    self.assertEqual((auth/'deepseek-generation.db').read_bytes(),deep_ledger)
                    self.assertEqual((auth/'runs/deepseek/report.json').read_bytes(),deep_report)
                    self.assertEqual({k:len(v) for k,v in payloads.items()},{'deepseek':2,'bailian':2})
                    self.assertTrue((auth/'paired-report-resumed.json').is_file())
                    self.assertFalse(report['records'][0]['real_function_calling_verified'])
                    from target.request_accounting import snapshot
                    self.assertEqual(snapshot(auth/'generation-total.db',4)['reserved_requests'],4)
                    embedding.assert_not_called()
                with self.assertRaisesRegex(ValueError,'resume_requires_zero_qwen_dispatch'),redirect_stdout(io.StringIO()):
                    execute_pair(model_factory=factory,resume_unattempted_qwen=True)
                output=os.getenv('V352_PROTOCOL_EVIDENCE_OUT')
                if output:
                    destination=Path(output);destination.mkdir(parents=True,exist_ok=True)
                    from target.diagnostics import sanitize
                    (destination/(behavior+'.json')).write_text(json.dumps(sanitize(report),ensure_ascii=False,indent=2),encoding='utf-8')
                return report

    def test_local_zero_http_failure_can_only_resume_unused_qwen_budget(self):
        r=self.exercise('good',resume=True)
        self.assertTrue(r['same_tool_evidence_verified']);self.assertTrue(r['same_system_prompt_verified'])
        self.assertEqual(r['real_generation_requests_this_command'],0)
        self.assertTrue(all(x['protocol_closure'] for x in r['records']))

    def test_pair_receives_identical_actual_chroma_tool_results(self):
        r=self.exercise('good')
        self.assertTrue(r['same_tool_evidence_verified']);self.assertTrue(r['same_system_prompt_verified'])
        for row in r['records']:
            self.assertTrue(row['protocol_closure']);self.assertTrue(row['agent_completed'])
            self.assertEqual(row['delivered_evidence'][0]['parsed_result_sha256'],row['expected_evidence_sha256'])
            self.assertIn('15',row['original_model_reply']);self.assertIsNone(row['business_success'])

    def test_protocol_success_and_wrong_answer_are_separate(self):
        r=self.exercise('wrong_answer')
        for row in r['records']:
            self.assertTrue(row['protocol_closure']);self.assertFalse(row['agent_completed'])
            self.assertEqual(row['status'],'protocol_passed_guard_rejected')
            self.assertEqual(row['faithfulness']['faithfulness_check']['status'],'failed')
            self.assertIn('45',row['original_model_reply']);self.assertIsNone(row['final_display_result'])

    def test_timeout_is_not_retried_and_other_provider_has_own_budget(self):
        r=self.exercise('timeout')
        self.assertEqual([x['generation_requests'] for x in r['records']],[1,1])
        self.assertFalse(r['same_tool_evidence_verified'])
        self.assertTrue(all(not x['protocol_closure'] for x in r['records']))

    def test_text_only_answer_is_not_tool_calling_success(self):
        r=self.exercise('no_tool')
        self.assertFalse(r['same_tool_evidence_verified'])
        self.assertTrue(all(not x['protocol_closure'] for x in r['records']))


class FixedBudgetTests(unittest.TestCase):
    def test_per_provider_two_and_shared_four_are_persisted(self):
        from target.deepseek_runtime import Settings
        from target.request_accounting import CoordinatedBudget
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);shared=root/'shared.db'
            q=CoordinatedBudget(Settings(max_requests=2,ledger_path=root/'q.db'),'bailian',shared,4)
            d=CoordinatedBudget(Settings(max_requests=2,ledger_path=root/'d.db'),'deepseek',shared,4)
            q.reserve();q.reserve()
            with self.assertRaisesRegex(Exception,'budget_exhausted'):q.reserve()
            d.reserve();d.reserve()
            with self.assertRaisesRegex(Exception,'budget_exhausted'):d.reserve()
            self.assertEqual(q.snapshot()['reserved_requests'],2);self.assertEqual(d.snapshot()['reserved_requests'],2)

    def test_fresh_budget_requires_explicit_command_marker(self):
        import target.v352_validation as v
        from target.deepseek_runtime import Settings
        with tempfile.TemporaryDirectory() as folder,patch.object(v,'AUTH',Path(folder)):
            settings=Settings(max_requests=2,max_model_calls=2,ledger_path=Path(folder)/'deepseek-generation.db')
            with patch.dict(os.environ,{'TICKET_INITIAL_LIVE_BUDGET':str(Path(folder)/'generation-total.db'),'TICKET_TOTAL_REQUEST_LIMIT':'4'}):
                with self.assertRaisesRegex(Exception,'explicit_validation_command_required'):v.validate_generation_binding(settings,'deepseek')
                with self.assertRaisesRegex(Exception,'fixed_generation_budget_required'):
                    v.validate_generation_binding(replace(settings,ledger_path=Path(folder)/'alias.db'),'deepseek')
