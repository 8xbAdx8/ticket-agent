"""A-owned offline tests for reproducible test-lab audit findings."""
import tempfile
import json
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import config
from target.diagnostics import evaluate
from web.runtime import Conversation


class LabAuditRegression(unittest.TestCase):
    def test_lab_case_id_is_recorded_in_saved_mock_audit(self):
        root=config.BASE_DIR/'artifacts/runtime';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='lab-case-',dir=root) as directory:
            base=Path(directory).resolve();self.assertTrue(base.is_relative_to(root.resolve()))
            session=Conversation('lab',case_id='B-DEMO-001',root=base/'session')
            session.send('查明天上海到杭州的高铁','case-request')
            self.assertEqual(session.audits[-1].get('test_case_label'),'B-DEMO-001')
            saved=json.loads((session.trace_dir/'audit_runs.jsonl').read_text(encoding='utf-8').splitlines()[-1])
            self.assertEqual(saved.get('test_case_label'),'B-DEMO-001')

    def test_live_unavailable_reason_distinguishes_offline_missing_key_and_endpoint(self):
        from web.laboratory import live_unavailable_reason
        with patch.dict(os.environ,{'TICKET_WEB_OFFLINE_ONLY':'1'},clear=True):
            self.assertIn('离线',live_unavailable_reason('deepseek'))
        with patch.dict(os.environ,{'TICKET_WEB_OFFLINE_ONLY':'0'},clear=True):
            self.assertIn('DEEPSEEK_API_KEY',live_unavailable_reason('deepseek'))
            self.assertIn('DASHSCOPE_API_KEY',live_unavailable_reason('bailian'))
        with patch.dict(os.environ,{'DASHSCOPE_API_KEY':'offline-placeholder'},clear=True):
            self.assertIn('DASHSCOPE_BASE_URL',live_unavailable_reason('bailian'))
    def test_duplicate_identical_calls_in_one_step_are_detected_without_injection_metadata(self):
        public={'session_id':'duplicate','user_msg':'查车次','reply':'查到车次。','finish_reason':'stop'}
        calls=[{'id':'c1','name':'query_tickets','args':{'date':'2026-10-28'}},
               {'id':'c2','name':'query_tickets','args':{'date':'2026-10-28'}}]
        executions=[{'tool':'query_tickets','args':c['args'],'call_id':c['id'],'step':1,
                     'executed':True,'ok':True,'result':{'trains':[]}} for c in calls]
        report={'executions':executions,'model_requests':[{'source':'legacy_provider','tool_calls':calls}],
                'injection_events':[],'mutations':{}}
        result=evaluate(public,report,{'available':True,'trains':[],'orders':[]})
        self.assertEqual(result['quality_verdict'],'fail')
        self.assertTrue(result['failure_reasons'])
        self.assertTrue(result['dimensions']['platform_defect_detected'])

    def test_policy_only_input_routed_to_ticket_query_is_detected_independently(self):
        public={'session_id':'route','user_msg':'退票手续费政策是什么？','reply':'查到了车次。','finish_reason':'stop'}
        report={'executions':[{'tool':'query_tickets','args':{},'call_id':'c1','step':1,'executed':True,'ok':True,
                               'result':{'trains':[]}}],
                'model_requests':[{'source':'legacy_provider','tool_calls':[{'id':'c1','name':'query_tickets','args':{}}]}],
                'injection_events':[],'mutations':{}}
        result=evaluate(public,report,{'available':True,'trains':[],'orders':[]})
        self.assertEqual(result['quality_verdict'],'fail')
        self.assertTrue(result['failure_reasons']);self.assertFalse(result['dimensions']['business_correct'])

    def test_policy_reply_repeating_source_without_citation_fails_independently(self):
        public={'session_id':'citation','user_msg':'退票政策是什么？','reply':'退票需按规定支付手续费。','finish_reason':'stop'}
        report={'executions':[{'tool':'search_policy','args':{},'call_id':'c1','step':1,'executed':True,'ok':True,
                               'result':{'hits':[{'doc_id':'P01','content':'退票需按规定支付手续费。'}]}}],
                'model_requests':[{'source':'legacy_provider','tool_calls':[{'id':'c1','name':'search_policy','args':{}}]}],
                'injection_events':[],'mutations':{}}
        result=evaluate(public,report,{'available':True,'trains':[],'orders':[]})
        self.assertEqual(result['quality_verdict'],'fail')
        self.assertTrue(result['failure_reasons']);self.assertFalse(result['dimensions']['business_correct'])
        public['reply']='依据政策P01：退票需按规定支付手续费。'
        self.assertNotEqual(evaluate(public,report,{'available':True,'trains':[],'orders':[]})['quality_verdict'],'fail')
        public['reply']='现有资料不足，无法确认。'
        self.assertNotEqual(evaluate(public,report,{'available':True,'trains':[],'orders':[]})['quality_verdict'],'fail')

    def test_legacy_provider_exception_is_recorded_as_failure_without_contract_change(self):
        from target.agent import Agent
        from target.providers import MockProvider
        class Broken(MockProvider):
            def chat(self,*args,**kwargs):raise RuntimeError('offline synthetic failure')
        with tempfile.TemporaryDirectory(prefix='lab-provider-') as folder:
            with patch.multiple(config,PROVIDER='mock',ENGINE='legacy',DB_PATH=Path(folder)/'missing.db',
                                TRACE_DIR=Path(folder)/'traces'):
                agent=Agent(provider=Broken())
                result=agent.chat('broken','你好')
                self.assertEqual(result['finish_reason'],'stop')  # Existing two-value contract.
                self.assertTrue(agent.last_audit_report['contract_returned'])
                self.assertEqual(agent.last_audit_report['error']['category'],'legacy_provider_error')
                self.assertEqual(agent.last_audit_report['judgement']['quality_verdict'],'fail')
                self.assertTrue(agent.last_audit_report['judgement']['failure_reasons'])

    def test_lab_does_not_display_legacy_provider_error_as_success(self):
        from target.agent import Agent
        from target.providers import MockProvider
        class Broken(MockProvider):
            def chat(self,*args,**kwargs):raise RuntimeError('offline synthetic failure')
        root=config.BASE_DIR/'artifacts/runtime';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='lab-error-',dir=root) as directory:
            base=Path(directory).resolve();self.assertTrue(base.is_relative_to(root.resolve()))
            agent=Agent(provider=Broken(),engine='legacy')
            with patch('web.runtime.Agent',return_value=agent):
                session=Conversation('lab',root=base/'session')
                with self.assertRaises(RuntimeError):session.send('你好','request-1')
            self.assertEqual(session.error['category'],'legacy_provider_error')
            self.assertEqual(session.history,[])
            self.assertEqual(session.audits[-1]['judgement']['quality_verdict'],'fail')

    def test_unavailable_ticket_authority_is_indeterminate_not_pass(self):
        public={'session_id':'authority-missing','user_msg':'查票','reply':'没有班次。','finish_reason':'stop'}
        report={'executions':[{'tool':'query_tickets','executed':True,'ok':True,'result':{'trains':[]}}],
                'model_requests':[],'injection_events':[],'mutations':{}}
        judgement=evaluate(public,report,{'available':False,'trains':[],'orders':[]})
        check=next(c for c in judgement['assertions'] if c['assertion']=='query_result_train_authority')
        self.assertIsNone(check['passed'])
        self.assertEqual(judgement['quality_verdict'],'indeterminate')
        self.assertTrue(judgement['indeterminate_reasons'])
        self.assertIsNone(judgement['dimensions']['business_correct'])

    def test_inapplicable_concurrency_mutant_keeps_baseline_without_crash(self):
        root=config.BASE_DIR/'artifacts/runtime';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='lab-audit-',dir=root) as directory:
            base=Path(directory).resolve();self.assertTrue(base.is_relative_to(root.resolve()))
            for scenario in ('expired_lock','worker_failure'):
                with self.subTest(scenario=scenario):
                    session=Conversation('lab',root=base/scenario)
                    records=session.concurrency(scenario)
                    self.assertEqual(len(records),1)
                    self.assertEqual(records[0]['mode'],'normal_backend')
                    self.assertEqual(records[0]['judgement']['test_verdict'],'pass')
                    self.assertTrue(records[0]['resources_cleaned'])
                    self.assertEqual(len(session.audits),1)

    def test_saved_lab_trace_can_be_recovered_by_id_after_new_browser_session(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory(prefix='lab-replay-') as directory:
            root=Path(directory);sid='web-0123456789ab';trace_id='d'*32
            folder=root/'artifacts/runtime/v33/lab'/sid/'traces';folder.mkdir(parents=True)
            row={'trace_id':trace_id,'provider':'mock','timestamp':'2026-10-27T00:00:00Z',
                 'public_trace':{'session_id':sid,'user_msg':'查票','reply':'示例','steps':[]},
                 'judgement':{'quality_verdict':'indeterminate','dimensions':{}}}
            (folder/'audit_runs.jsonl').write_text(json.dumps(row,ensure_ascii=False)+'\n',encoding='utf-8')
            before=(folder/'audit_runs.jsonl').read_bytes()
            with patch.object(config,'BASE_DIR',root):
                app=AppTest.from_string('from web.trace_view import trace_page\ntrace_page([])').run()
                next(r for r in app.radio if r.label=='证据范围').set_value('本地实验按会话ID回放').run()
                next(t for t in app.text_input if t.label=='实验会话 ID').set_value(sid).run()
                self.assertFalse(app.exception)
                self.assertTrue(any(trace_id in c.value for c in app.caption))
            self.assertEqual((folder/'audit_runs.jsonl').read_bytes(),before)

    def test_submit_widget_rotates_after_execution_and_allows_next_deliberate_run(self):
        from streamlit.testing.v1 import AppTest
        root=config.BASE_DIR/'artifacts/runtime';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='lab-submit-',dir=root) as directory:
            base=Path(directory).resolve();self.assertTrue(base.is_relative_to(root.resolve()))
            def new_session(*args,**kwargs):
                return Conversation(*args,root=base/uuid.uuid4().hex,**kwargs)
            with patch('web.laboratory.Conversation',side_effect=new_session):
                app=AppTest.from_string('from web.laboratory import lab_page\nlab_page()').run()
                button=next(b for b in app.button if b.label=='执行测试')
                first=button.key
                self.assertIsNotNone(first)
                button.click().run()
                second=next(b for b in app.button if b.label=='执行测试')
                self.assertNotEqual(first,second.key)
                self.assertEqual(len(app.session_state['lab_session'].history),1)
                second.click().run()
                self.assertEqual(len(app.session_state['lab_session'].history),2)

    def test_case_change_creates_an_independent_experiment_database(self):
        from streamlit.testing.v1 import AppTest
        root=config.BASE_DIR/'artifacts/runtime';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='lab-cases-',dir=root) as directory:
            base=Path(directory).resolve();self.assertTrue(base.is_relative_to(root.resolve()))
            def new_session(*args,**kwargs):return Conversation(*args,root=base/uuid.uuid4().hex,**kwargs)
            with patch('web.laboratory.Conversation',side_effect=new_session):
                app=AppTest.from_string('from web.laboratory import lab_page\nlab_page()').run()
                next(b for b in app.button if b.label=='执行测试').click().run()
                first=app.session_state['lab_session']
                next(t for t in app.text_input if t.label=='测试用例 ID').set_value('B-next-case').run()
                second=app.session_state['lab_session']
                self.assertNotEqual(first.root,second.root)
                self.assertEqual(second.history,[])
                next(b for b in app.button if b.label=='执行测试').click().run()
                self.assertEqual(second.audits[-1]['test_case_label'],'B-next-case')
                self.assertTrue((first.root/'tickets.db').is_file())
                self.assertTrue((second.root/'tickets.db').is_file())

    def test_expired_lock_and_worker_failure_ui_report_not_applicable(self):
        from streamlit.testing.v1 import AppTest
        root=config.BASE_DIR/'artifacts/runtime';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='lab-concurrency-',dir=root) as directory:
            base=Path(directory).resolve();self.assertTrue(base.is_relative_to(root.resolve()))
            def new_session(*args,**kwargs):return Conversation(*args,root=base/uuid.uuid4().hex,**kwargs)
            with patch('web.laboratory.Conversation',side_effect=new_session):
                app=AppTest.from_string('from web.laboratory import lab_page\nlab_page()').run()
                for scenario in ('expired_lock','worker_failure'):
                    next(s for s in app.selectbox if s.label=='并发场景').select(scenario).run()
                    next(b for b in app.button if b.label.startswith('运行并发订单对照')).click().run()
                    self.assertFalse(app.exception)
                    self.assertTrue(any('不适用于 M8' in item.value for item in app.info))

    def test_concurrency_button_rotates_and_allows_deliberate_new_probe(self):
        from streamlit.testing.v1 import AppTest
        root=config.BASE_DIR/'artifacts/runtime';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='lab-double-probe-',dir=root) as directory:
            base=Path(directory).resolve();self.assertTrue(base.is_relative_to(root.resolve()))
            def new_session(*args,**kwargs):return Conversation(*args,root=base/uuid.uuid4().hex,**kwargs)
            with patch('web.laboratory.Conversation',side_effect=new_session):
                app=AppTest.from_string('from web.laboratory import lab_page\nlab_page()').run()
                first=next(b for b in app.button if b.label.startswith('运行并发订单对照'))
                first_key=first.key;first.click().run()
                second=next(b for b in app.button if b.label.startswith('运行并发订单对照'))
                self.assertNotEqual(first_key,second.key)
                self.assertEqual(len(app.session_state['lab_session'].audits),2)
                second.click().run()
                self.assertEqual(len(app.session_state['lab_session'].audits),4)


if __name__=='__main__':unittest.main()
