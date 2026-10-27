"""A-owned offline tests for reproducible test-lab audit findings."""
import tempfile
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import config
from target.diagnostics import evaluate
from web.runtime import Conversation


class LabAuditRegression(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
