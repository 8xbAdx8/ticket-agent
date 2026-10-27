"""Current cumulative-quota policy. Offline fixtures never send real API traffic."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent


def historical(path, count=8, *, linked=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    with contextlib.closing(sqlite3.connect(path)) as c:
        c.execute('CREATE TABLE requests(id INTEGER PRIMARY KEY, status INTEGER, category TEXT)')
        c.executemany('INSERT INTO requests(status,category) VALUES(NULL,?)',[('reserved_outcome_unknown',)]*count)
        c.execute('CREATE TABLE budget_policy(id INTEGER PRIMARY KEY,limit_value INTEGER)')
        c.execute('INSERT INTO budget_policy VALUES(1,1)')
        c.commit()
    return hashlib.sha256(path.read_bytes()).hexdigest()


class UsageOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'TICKET_API_USAGE_DIR':str(self.root/'usage')});self.env.start()

    def tearDown(self):
        self.env.stop();self.tmp.cleanup()

    def test_old_full_unknown_ledger_is_never_changed_or_consulted(self):
        from target.deepseek_runtime import RequestBudget,Settings
        from dataclasses import replace
        old=self.root/'old.db';digest=historical(old)
        log=RequestBudget(replace(Settings(),max_requests=1,ledger_path=old))
        for _ in range(20):
            uid=log.reserve();log.record(uid,status=200,model='fixture',usage={'prompt_tokens':3,'completion_tokens':1})
        state=log.snapshot()
        self.assertEqual(state['request_count'],20)
        self.assertIsNone(state['limit'])
        self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(),digest)
        self.assertNotEqual(log.path,old)

    def test_corrupt_legacy_ledger_and_invalid_old_caps_are_ignored(self):
        from target.deepseek_runtime import Settings,RequestBudget
        from target.bailian_runtime import Settings as Bailian
        old=self.root/'corrupt.db';old.write_bytes(b'not a SQLite database')
        env={'DEEPSEEK_BUDGET_PATH':str(old),'BAILIAN_BUDGET_PATH':str(old),
             'DEEPSEEK_MAX_REQUESTS':'invalid','BAILIAN_MAX_REQUESTS':'-99',
             'TICKET_INITIAL_LIVE_BUDGET':str(old),'TICKET_TOTAL_REQUEST_LIMIT':'invalid'}
        with patch.dict(os.environ,env):
            for cls in (Settings,Bailian):
                settings=cls.from_env();self.assertEqual(settings.max_requests,0)
                RequestBudget(settings).reserve()
        self.assertEqual(old.read_bytes(),b'not a SQLite database')

    def test_statistics_unknown_and_settlement_keep_first_http_result(self):
        from target.api_usage import UsageLog
        log=UsageLog('deepseek',self.root/'label',origin='offline_stub')
        uid=log.reserve({'model':'fixture'})
        log.record(uid,status=200,usage={})
        log.record(uid,category='later_sdk_error')
        row=log.snapshot()['requests'][0]
        self.assertEqual(row['status'],200)
        self.assertIsNone(row['prompt']);self.assertIsNone(row['completion']);self.assertIsNone(row['cost'])

    def test_statistic_write_failure_does_not_reject_request_identity(self):
        from target.api_usage import UsageLog
        log=UsageLog('deepseek',self.root/'label')
        with patch('target.api_usage.os.open',side_effect=PermissionError('offline fixture')):
            uid=log.reserve();log.record(uid,status=200)
        self.assertTrue(uid)
        self.assertIsNone(log.snapshot()['request_count'])

    def test_threaded_recording_has_no_total_or_provider_ceiling(self):
        from target.request_accounting import CoordinatedBudget
        from target.deepseek_runtime import Settings
        from concurrent.futures import ThreadPoolExecutor
        from dataclasses import replace
        old=self.root/'provider.db';digest=historical(old)
        logs=[CoordinatedBudget(replace(Settings(),max_requests=1,ledger_path=old),p,self.root/'total.db',1)
              for p in ('deepseek','bailian')]
        with ThreadPoolExecutor(max_workers=4) as pool:
            identities=list(pool.map(lambda i:logs[i%2].reserve(),range(30)))
        self.assertEqual(len(set(identities)),30)
        self.assertEqual(sum(log.snapshot()['request_count'] for log in logs),30)
        self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(),digest)
        self.assertFalse((self.root/'total.db').exists())

    def test_live_and_stub_statistics_are_separate(self):
        from target.api_usage import UsageLog,provider_usage
        live=UsageLog('bailian','same',origin='real_api');stub=UsageLog('bailian','same',origin='offline_stub')
        live.record(live.reserve(),status=200,usage={'prompt_tokens':7,'completion_tokens':2})
        stub.record(stub.reserve(),status=200,usage={'prompt_tokens':999,'completion_tokens':999})
        state=provider_usage('bailian')
        self.assertEqual(state['request_count'],1);self.assertEqual(state['offline_stub_requests'],1)
        self.assertEqual(state['prompt_tokens'],7);self.assertEqual(state['completion_tokens'],2)

    @unittest.skipUnless(importlib.util.find_spec('httpx') is not None,'HTTP transport dependency required')
    def test_non_mock_transport_cannot_expand_live_write_tools(self):
        import httpx
        from target.deepseek_runtime import guarded_client,Settings,DeepSeekError
        calls=[]
        class LocalTransport(httpx.BaseTransport):
            def handle_request(self,request):
                calls.append(request)
                return httpx.Response(200,json={})
        with patch('target.deepseek_runtime.allowed_tools',return_value={'query_tickets','pay_order'}):
            with guarded_client(Settings(),transport=LocalTransport()) as client:
                with self.assertRaisesRegex(DeepSeekError,'read_only_tools_required'):
                    client.post('https://api.deepseek.com/chat/completions',json={'model':'deepseek-flash',
                        'thinking':{'type':'disabled'},'max_tokens':16,'tools':[{'function':{'name':'pay_order'}}]})
        self.assertEqual(calls,[])


try:
    import test_deepseek_agent as deep_fixture
    import test_live_providers as bailian_fixture
    SDK=deep_fixture.AVAILABLE and bailian_fixture.AVAILABLE
except ImportError:
    SDK=False


@unittest.skipUnless(SDK,'full SDK environment; all HTTP uses MockTransport')
class UnlimitedProviderTests(unittest.TestCase):
    def run_provider(self,provider,scenario):
        import config
        import httpx
        from target.deepseek_runtime import DeepSeekError,RequestBudget
        cls=deep_fixture.DeepSeekAgentTests if provider=='deepseek' else bailian_fixture.LiveProviderTests
        fixture=cls()
        with contextlib.redirect_stdout(io.StringIO()):fixture.setUp()
        try:
            root=fixture.folder if provider=='deepseek' else fixture.root
            from target import deepseek_runtime,bailian_runtime
            runtime=deepseek_runtime if provider=='deepseek' else bailian_runtime
            settings=runtime.Settings.from_env()
            old=settings.ledger_path;digest=historical(old)
            shared=root/'unlinked-total.db';shared_digest=historical(shared,12)
            extras={'TICKET_INITIAL_LIVE_BUDGET':str(shared),'TICKET_TOTAL_REQUEST_LIMIT':'0',
                    'DEEPSEEK_MAX_REQUESTS':'1','BAILIAN_MAX_REQUESTS':'1','TICKET_API_VALIDATION_PROFILE':'v352',
                    'TICKET_API_USAGE_DIR':str(root/'usage')}
            with patch.dict(os.environ,extras):
                response=fixture.response({'content':'请补充出发地、目的地和日期。'})
                if scenario=='repeat':
                    agent=fixture.agent([response])
                    for i in range(10):
                        result=agent.chat('no-limit-'+str(i),'您好')
                        self.assertEqual(result['finish_reason'],'stop');self.assertEqual(result['tool_sequence'],[])
                    self.assertEqual(len(fixture.payloads),10)
                    self.assertEqual(RequestBudget(runtime.Settings.from_env()).snapshot()['request_count'],10)
                elif scenario=='log_failure':
                    agent=fixture.agent([response])
                    with patch('target.api_usage.os.open',side_effect=PermissionError('fixture only')):
                        result=agent.chat('write-error','您好')
                    self.assertEqual(result['reply'],'请补充出发地、目的地和日期。')
                    self.assertTrue(any(e['event']=='usage_recording_warning' for e in agent.langchain_engine.last_events))
                    self.assertEqual(len(fixture.payloads),1)
                elif scenario=='log_corrupt':
                    log=RequestBudget(runtime.Settings.from_env())
                    log.path.parent.mkdir(parents=True,exist_ok=True);log.path.write_text('invalid-json\n',encoding='utf-8')
                    agent=fixture.agent([response]);result=agent.chat('corrupt-statistics','您好')
                    self.assertEqual(result['reply'],'请补充出发地、目的地和日期。')
                    self.assertEqual(len(fixture.payloads),1)
                    self.assertIsNone(log.snapshot()['request_count'])
                elif scenario=='steps':
                    from datetime import timedelta
                    args={'from_city':'上海','to_city':'杭州','date':(config.today()+timedelta(days=1)).isoformat()}
                    with patch.dict(os.environ,{'DEEPSEEK_MAX_MODEL_CALLS':'1','BAILIAN_MAX_MODEL_CALLS':'1'}):
                        agent=fixture.agent([fixture.response({'content':None,'tool_calls':[fixture.call('query_tickets',args)]})])
                    result=agent.chat('bounded','查明天上海到杭州高铁')
                    self.assertEqual(result['finish_reason'],'max_steps_exceeded')
                    self.assertEqual(len(fixture.payloads),1)
                else:
                    code=int(scenario)
                    agent=fixture.agent([(code,{'error':{'message':'offline failure'}})])
                    categories={401:'authentication_failed',403:'permission_denied',429:'rate_limited',500:'server_error',503:'service_unavailable'}
                    with self.assertRaisesRegex(DeepSeekError,categories[code]):agent.chat('server-error','您好')
                    self.assertEqual(len(fixture.payloads),1)
                    self.assertEqual(agent.last_audit_report['error']['http_status'],code)
            self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(),digest)
            self.assertEqual(hashlib.sha256(shared.read_bytes()).hexdigest(),shared_digest)
        finally:
            fixture.tearDown()


def provider_case(provider,scenario):
    def run(self):self.run_provider(provider,scenario)
    return run


for _provider in ('deepseek','bailian'):
    for _scenario in ('repeat','log_failure','log_corrupt','steps','401','403','429','500','503'):
        setattr(UnlimitedProviderTests,'test_'+_provider+'_'+_scenario,provider_case(_provider,_scenario))


@unittest.skipUnless(SDK,'httpx required; no real Embedding calls')
class UnlimitedEmbeddingTests(unittest.TestCase):
    def test_cached_vectors_do_not_count_as_new_requests_and_rag_ids_are_linked(self):
        import httpx
        from target.embeddings import EmbeddingProvider,EmbeddingSettings
        from target.rag_service import scope
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);calls=[]
            def respond(request):
                calls.append(request)
                return httpx.Response(200,json={'id':'fixture-server-id','model':'text-embedding-v4',
                    'data':[{'index':0,'embedding':[1.0]+[0.0]*63}],'usage':{'total_tokens':2}})
            settings=EmbeddingSettings(base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',dimensions=64,
                ledger=root/'old.db',cache=root/'cache.db')
            with patch.dict(os.environ,{'DASHSCOPE_API_KEY':'offline-key','TICKET_API_USAGE_DIR':str(root/'usage')}):
                provider=EmbeddingProvider(settings,transport=httpx.MockTransport(respond))
                with scope(trace_id='rag-trace',call_id='search-policy-call'):
                    provider.embed_many(['query'],allow_network=True)
                self.assertEqual(len(provider.request_ids),1)
                provider.embed_many(['query'],allow_network=False)
                self.assertEqual(provider.request_ids,[]);self.assertEqual(len(calls),1)
                row=provider.budget.snapshot()['requests'][0]
                self.assertEqual(row['trace_id'],'rag-trace');self.assertEqual(row['tool_call_id'],'search-policy-call')
                self.assertEqual(row['server_request_id'],'fixture-server-id');self.assertEqual(row['tokens'],2)
                self.assertEqual(row['requested_model'],'text-embedding-v4')

    def test_more_than_eight_requests_leave_old_embedding_ledger_unchanged(self):
        import httpx
        from target.embeddings import EmbeddingProvider,EmbeddingSettings
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);old=root/'embedding.db';digest=historical(old,8);calls=[]
            def respond(request):
                calls.append(request);body=json.loads(request.content)
                return httpx.Response(200,json={'model':'text-embedding-v4','data':[{'index':i,'embedding':[1.0]+[0.0]*63} for i,_ in enumerate(body['input'])],'usage':{'total_tokens':2}})
            settings=EmbeddingSettings(base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',dimensions=64,
                                       batch_size=1,ledger=old,limit=1,cache=root/'cache.db')
            with patch.dict(os.environ,{'DASHSCOPE_API_KEY':'offline-embedding-key','TICKET_API_USAGE_DIR':str(root/'usage')}):
                provider=EmbeddingProvider(settings,transport=httpx.MockTransport(respond))
                vectors=provider.embed_many(['query-'+str(i) for i in range(12)],allow_network=True)
                self.assertEqual(len(vectors),12);self.assertEqual(len(calls),12)
                self.assertEqual(provider.budget.snapshot()['used'],12)
            self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(),digest)

    def test_embedding_statistics_failure_does_not_cancel_successful_http(self):
        import httpx
        from target.embeddings import EmbeddingProvider,EmbeddingSettings
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);calls=[]
            def respond(request):
                calls.append(request)
                return httpx.Response(200,json={'data':[{'index':0,'embedding':[1.0]+[0.0]*63}]})
            settings=EmbeddingSettings(base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',dimensions=64,ledger=root/'old.db',cache=root/'cache.db')
            with patch.dict(os.environ,{'DASHSCOPE_API_KEY':'offline-key','TICKET_API_USAGE_DIR':str(root/'usage')}):
                provider=EmbeddingProvider(settings,transport=httpx.MockTransport(respond))
                with patch('target.api_usage.os.open',side_effect=PermissionError('fixture')):
                    self.assertEqual(len(provider.embed_many(['new question'],allow_network=True)),1)
                self.assertIsNone(provider.last_receipts[0]['tokens'])
                self.assertIsNone(provider.budget.snapshot()['used'])
            self.assertEqual(len(calls),1)
