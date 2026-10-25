"""A-owned deterministic budget/config/protocol regression. No paid network calls."""
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from contextlib import closing
from unittest.mock import patch
from target.deepseek_runtime import Settings,DeepSeekError
from target.request_accounting import CoordinatedBudget,snapshot


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.settings=replace(Settings(),max_requests=2,ledger_path=self.root/'p.db')
        self.budget=CoordinatedBudget(self.settings,'deepseek',self.root/'total.db',4)

    def tearDown(self):self.tmp.cleanup()

    def test_same_uuid_atomic_pair_and_idempotent_settlement(self):
        uid=self.budget.reserve({'model':'fixture'})
        self.assertEqual(self.budget.reserve(request_id=uid),uid)
        for _ in range(2):self.budget.record(uid,status=200,usage={'prompt_tokens':7,'completion_tokens':2},model='fixture')
        a=snapshot(self.root/'total.db',4)['requests'];b=self.budget.snapshot()['requests']
        self.assertEqual(a,b);self.assertEqual(len(a),1);self.assertEqual(a[0]['request_id'],uid)
        self.budget.record(uid,category='sdk_error_outcome_unknown')
        self.assertEqual(self.budget.snapshot()['requests'][0]['status'],200)

    def test_provider_limit_does_not_leak_total_reservation(self):
        for _ in range(2):self.budget.reserve()
        with self.assertRaises(DeepSeekError):self.budget.reserve()
        self.assertEqual(snapshot(self.root/'total.db',4)['reserved_requests'],2)
        self.assertEqual(self.budget.snapshot()['reserved_requests'],2)

    def test_concurrent_providers_never_exceed_four_and_ids_match(self):
        second=CoordinatedBudget(replace(self.settings,ledger_path=self.root/'q.db'),'bailian',self.root/'total.db',4)
        def work(i):
            try:return (self.budget if i%2 else second).reserve()
            except DeepSeekError:return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:ids=list(pool.map(work,range(12)))
        a=snapshot(self.root/'total.db',4)['requests']
        b=self.budget.snapshot()['requests']+second.snapshot()['requests']
        self.assertEqual(len(a),4);self.assertEqual(len(set(filter(None,ids))),4)
        self.assertEqual({r['request_id'] for r in a},{r['request_id'] for r in b})

    def test_legacy_ledger_is_rejected_without_rewrite(self):
        path=self.root/'total.db'
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE requests(id INTEGER PRIMARY KEY,category TEXT)');db.execute("INSERT INTO requests VALUES(1,'reserved_outcome_unknown')");db.commit()
        before=path.read_bytes()
        with self.assertRaisesRegex(DeepSeekError,'historical_unlinked'):self.budget.reserve()
        self.assertEqual(path.read_bytes(),before)
        self.assertTrue(snapshot(path,3)['historical_unlinked'])

    def test_unknown_tokens_are_null_and_pending_survives_restart(self):
        uid=self.budget.reserve()
        again=CoordinatedBudget(self.settings,'deepseek',self.root/'total.db',4)
        self.assertIn(uid,again.snapshot()['unsettled_ids'])
        again.record(uid,status=200,usage={})
        row=again.snapshot()['requests'][0]
        self.assertIsNone(row['prompt']);self.assertIsNone(row['completion'])

    def test_process_exit_keeps_recoverable_identity_and_does_not_refund(self):
        code="from pathlib import Path; from dataclasses import replace; import os; from target.deepseek_runtime import Settings; from target.request_accounting import CoordinatedBudget; b=CoordinatedBudget(replace(Settings(),max_requests=2,ledger_path=Path(os.environ['V34_TEST_PROVIDER'])),'deepseek',Path(os.environ['V34_TEST_TOTAL']),4); b.reserve(); os._exit(0)"
        env=dict(os.environ,V34_TEST_PROVIDER=str(self.settings.ledger_path),V34_TEST_TOTAL=str(self.root/'total.db'))
        subprocess.run([sys.executable,'-c',code],env=env,check=True,capture_output=True)
        self.assertEqual(self.budget.snapshot()['reserved_requests'],1)
        self.assertEqual(len(self.budget.snapshot()['unsettled_ids']),1)

    def test_policy_cannot_be_silently_raised(self):
        self.budget.reserve()
        other=CoordinatedBudget(self.settings,'deepseek',self.root/'total.db',3)
        with self.assertRaisesRegex(DeepSeekError,'persisted_budget_limit'):other.reserve()
        self.assertEqual(snapshot(self.root/'total.db',4)['reserved_requests'],1)

    def test_snapshot_missing_is_readonly(self):
        self.assertEqual(self.budget.snapshot()['reserved_requests'],0)
        self.assertFalse(self.settings.ledger_path.exists())


class ConfigTests(unittest.TestCase):
    def test_preflight_redacts_key_accidentally_used_as_model(self):
        from target.api_config import status
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'private-fixture-model','DEEPSEEK_MODEL':'private-fixture-model'}):
            self.assertNotIn('private-fixture-model',json.dumps(status('deepseek')))

    def test_live_gate_refuses_unverified_or_unmatched_offline_evidence(self):
        from scripts.verify_v34_live import gate
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'report.json';path.write_text(json.dumps({'status':'failed','real_api_requests':0,'tested_source_head':'not-current'}))
            with self.assertRaisesRegex(ValueError,'matching_frozen'):gate(path)

    def test_authorization_plan_is_fixed_two_two_four(self):
        from target.live_providers import isolated_environment
        import config
        with patch.dict(os.environ,{'TICKET_API_VALIDATION_PROFILE':'v34'}):
            a=isolated_environment('deepseek',config.BASE_DIR/'artifacts/runtime/v34-test-case')
            b=isolated_environment('bailian',config.BASE_DIR/'artifacts/runtime/v34-test-case-b')
        self.assertEqual(a['TICKET_TOTAL_REQUEST_LIMIT'],'4')
        self.assertEqual((a['DEEPSEEK_MAX_REQUESTS'],b['BAILIAN_MAX_REQUESTS']),('2','2'))
        self.assertEqual(a['TICKET_INITIAL_LIVE_BUDGET'],b['TICKET_INITIAL_LIVE_BUDGET'])
        self.assertNotEqual(a['DEEPSEEK_BUDGET_PATH'],b['BAILIAN_BUDGET_PATH'])

    def test_environment_wins_over_protected_file_and_no_interpolation(self):
        from target.api_config import bootstrap
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'.env').write_text('DASHSCOPE_API_KEY=file-fixture\nDASHSCOPE_MODEL=qwen-plus\nUNSUPPORTED=x\n',encoding='utf-8')
            with patch.dict(os.environ,{'DASHSCOPE_API_KEY':'process-fixture','TICKET_ENV_FILE':str(root/'.env'),'TICKET_OFFLINE_GUARD_LOG':'','TICKET_WEB_OFFLINE_ONLY':'0','TICKET_DISABLE_LOCAL_SECRETS':'0'}):
                os.environ.pop('DASHSCOPE_MODEL',None)
                sources=bootstrap(root)
                self.assertEqual(os.environ['DASHSCOPE_API_KEY'],'process-fixture')
                self.assertEqual(os.environ['DASHSCOPE_MODEL'],'qwen-plus')
                self.assertNotIn('UNSUPPORTED',sources)

    def test_offline_guard_never_discovers_local_keys(self):
        from target.api_config import bootstrap
        with patch.dict(os.environ,{'TICKET_DISABLE_LOCAL_SECRETS':'1'}):
            self.assertEqual(bootstrap()['local_secret_discovery'],'disabled')

    def test_endpoint_summary_never_exposes_url_secret(self):
        from target.api_config import safe_endpoint
        for url in ('https://private@api.example.invalid','https://example.invalid?key=private','https://example.invalid:bad'):
            self.assertEqual(safe_endpoint(url),'<invalid endpoint>')


try:
    import httpx
    import test_live_providers as fixtures
    SDK=fixtures.AVAILABLE
except ImportError:SDK=False


@unittest.skipUnless(SDK,'Full LangChain environment required')
class SDKLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.LiveProviderTests(methodName='runTest');self.fixture.setUp()
        self.env=patch.dict(os.environ,{'TICKET_INITIAL_LIVE_BUDGET':str(self.fixture.root/'total.db'),'TICKET_TOTAL_REQUEST_LIMIT':'4','BAILIAN_MAX_REQUESTS':'2'})
        self.env.start()

    def tearDown(self):self.env.stop();self.fixture.tearDown()

    def test_first_200_survives_second_timeout_and_partial_tokens(self):
        f=self.fixture
        agent=f.agent([f.response({'tool_calls':[f.call('search_policy',{'question':'锁座政策'})]}),httpx.ReadTimeout('fixture timeout')])
        with self.assertRaisesRegex(DeepSeekError,'timeout'):agent.chat('partial','锁座政策')
        p=snapshot(f.root/'bailian.db',2)['requests'];g=snapshot(f.root/'total.db',4)['requests']
        self.assertEqual([r['request_id'] for r in p],[r['request_id'] for r in g])
        self.assertEqual([r['status'] for r in g],[200,None])
        self.assertEqual(g[0]['prompt'],13)
        record=agent.langchain_engine.last_live_run
        self.assertTrue(record['model_response_received']);self.assertFalse(record['agent_completed'])
        self.assertIsNone(record['tokens']);self.assertEqual(record['observed_tokens'],{'prompt':13,'completion':5})
        self.assertEqual(len(f.payloads),2)

    def test_real_sdk_roundtrip_links_calls_and_does_not_retry(self):
        f=self.fixture
        agent=f.agent([f.response({'tool_calls':[f.call('search_policy',{'question':'锁座政策'})]}),f.response({'content':'锁座15分钟，来源P11。'})])
        result=agent.chat('roundtrip','锁座政策')
        events=agent.langchain_engine.last_events
        ids=[e['request_id'] for e in events if e['event']=='http_request']
        self.assertEqual(len(set(ids)),2)
        self.assertEqual([e['request_id'] for e in events if e['event']=='model_response'],ids)
        row=snapshot(f.root/'total.db',4)['requests'][1]
        self.assertEqual(json.loads(row['request_summary'])['returned_tool_call_ids'],['offline-call'])
        self.assertEqual(result['tool_sequence'],['search_policy'])

    def test_budget_blocks_before_network_without_phantom_total_row(self):
        f=self.fixture;agent=f.agent([f.response({'content':'当前只读咨询。'})])
        agent.chat('1','你好');agent.chat('2','你好')
        with self.assertRaises(DeepSeekError):agent.chat('3','你好')
        self.assertEqual(len(f.payloads),2)
        self.assertEqual(snapshot(f.root/'total.db',4)['reserved_requests'],2)
