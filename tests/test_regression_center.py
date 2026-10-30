"""Deterministic offline coverage of batch outcomes, evidence and presentation."""
import io
import json
import tempfile
import subprocess
import sys
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile
from streamlit.testing.v1 import AppTest
from scripts import regression_center as rc
from web.regression_center_view import bundle


class RegressionCenterTests(unittest.TestCase):
    def test_pytest_failures_and_setup_errors_come_from_structured_reports(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'results.json'
            rc.write(p,{'exit_code':1,'results':[
                {'case_id':'tests/test_x.py::fails','stage':'call','status':'failed','assertion_evidence':'AssertionError: expected paid'},
                {'case_id':'tests/test_x.py::error','stage':'setup','status':'failed','assertion_evidence':'FileNotFoundError'},
                {'case_id':'tests/test_x.py::ok','stage':'call','status':'passed'},
                {'case_id':'tests/test_x.py::sub','stage':'call','status':'passed','is_subtest':True}]})
            result=rc.pytest_summary(p)
            self.assertEqual((result['passed'],result['failed'],result['subtests_passed']),(1,2,1))
            self.assertEqual(result['failures'][1]['stage'],'setup')

    def test_html_escapes_untrusted_test_messages(self):
        report={'batch_id':'<script>','steps':[{'name':'test','status':'failed','reason':'<img src=x>','seconds':1}]}
        output=rc.html_report(report)
        self.assertIn('&lt;script&gt;',output);self.assertNotIn('<img',output)

    def test_export_excludes_snapshot_and_databases(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'snapshot').mkdir();(p/'snapshot/secret.env').write_text('excluded')
            (p/'tickets.db').write_bytes(b'database');(p/'report.json').write_text('{}')
            (p/'pytest.log').write_text('1 passed')
            with zipfile.ZipFile(io.BytesIO(bundle(p))) as archive:
                self.assertEqual(set(archive.namelist()),{'report.json','pytest.log'})

    def test_source_fingerprint_excludes_secrets_runtime_and_environment(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'tests').mkdir();(root/'tests/test_a.py').write_text('x=1')
            (root/'.env').write_text('secret');(root/'artifacts').mkdir();(root/'artifacts/a.json').write_text('{}')
            (root/'.venv-v35').mkdir();(root/'.venv-v35/module.py').write_text('ignore')
            self.assertEqual(set(rc.source_files(root)),{'tests/test_a.py'})

    def test_invalid_test_node_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for node in ('../tests/test_x.py','tests/../../x.py','C:/x.py','tests\\x.py'):
                with self.subTest(node=node),self.assertRaises(ValueError):rc.environment(Path(d),node)

    def pipeline(self,root,pytest_exit=1,changes=False):
        checkout=root/'checkout';checkout.mkdir()
        def command(argv,cwd,env,log,timeout=900):
            log.write_text('offline test')
            out=Path(argv[argv.index('--out')+1]);out.mkdir(parents=True)
            rc.write(out/'results.json',{'exit_code':pytest_exit,'results':[
                {'case_id':'tests/test_x.py::case','stage':'call','status':'failed' if pytest_exit else 'passed','assertion_evidence':'expected result'}]})
            return {'exit_code':pytest_exit}
        with patch.object(rc,'environment',return_value={'missing_dependencies':[],'package_exists':True}), \
             patch.object(rc,'prepare',return_value=(checkout,{},{})), \
             patch.object(rc,'run_command',side_effect=command), \
             patch.object(rc,'launcher_checks',return_value=[{'passed':True}]*5), \
             patch.object(rc,'protected_files',side_effect=[{'data/a':'a'},{'data/a':'b' if changes else 'a'}]):
            return rc.execute(root,root/'artifacts/runtime/batches',rag=False)

    def test_failed_pytest_never_becomes_success_and_skips_are_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            report=self.pipeline(Path(d))
            self.assertEqual(report['status'],'failed')
            self.assertEqual(next(s for s in report['steps'] if s['id']=='rag')['status'],'skipped')
            self.assertEqual(next(s for s in report['steps'] if s['id']=='pytest')['details']['failed'],1)
            self.assertTrue((Path(report['directory'])/'report.html').is_file())

    def test_protected_change_fails_even_when_pytest_passes(self):
        with tempfile.TemporaryDirectory() as d:
            report=self.pipeline(Path(d),pytest_exit=0,changes=True)
            self.assertEqual(report['status'],'failed')
            protection=next(s for s in report['steps'] if s['id']=='protection')
            self.assertEqual(protection['details']['changed_or_missing'],['data/a'])

    def test_missing_dependencies_block_execution(self):
        with tempfile.TemporaryDirectory() as d,patch.object(rc,'environment',return_value={'missing_dependencies':['chromadb'],'package_exists':False}),patch.object(rc,'prepare') as prepare:
            root=Path(d);report=rc.execute(root,root/'artifacts/runtime/batches')
            prepare.assert_not_called();self.assertEqual(report['status'],'blocked')
            self.assertFalse(any(s['status']=='passed' for s in report['steps'] if s['id'] in ('pytest','rag','launcher')))

    def test_unfinished_history_is_not_displayed_as_success(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'b').mkdir()
            rc.write(root/'b/report.json',{'schema':'ticket-regression-batch/1','status':'running','started':'2026-10-29'})
            self.assertEqual(rc.history(root)[0]['status'],'interrupted')
            self.assertEqual(rc.read(root/'b/report.json')['status'],'running')

    def test_page_browsing_never_launches_regression(self):
        with patch.object(rc,'execute') as execute,patch.object(rc,'history',return_value=[]):
            app=AppTest.from_string('from web.v37_console import page\npage()').run(timeout=20)
            self.assertEqual([e.message for e in app.exception],[])
            self.assertIn('执行回归',[t.label for t in app.tabs]);execute.assert_not_called()

    def test_real_offline_subprocess_preserves_assertion_setup_teardown_failures(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'scripts').mkdir();(root/'tests').mkdir()
            shutil.copy2(rc.ROOT/'scripts/v37_tests.py',root/'scripts/v37_tests.py')
            (root/'tests/test_failures.py').write_text('import pytest\n@pytest.fixture\ndef broken():\n raise RuntimeError("setup failed")\n@pytest.fixture\ndef teardown():\n yield\n raise RuntimeError("teardown failed")\ndef test_assertion():\n assert False, "intentional fixture failure"\ndef test_setup(broken): pass\ndef test_teardown(teardown): pass\n')
            out=root/'artifacts/runtime/failure-check'
            env=dict(os.environ,TICKET_DISABLE_LOCAL_SECRETS='1',PYTHONDONTWRITEBYTECODE='1')
            process=subprocess.run([sys.executable,str(root/'scripts/v37_tests.py'),'--out',str(out)],cwd=root,env=env,capture_output=True,timeout=40)
            self.assertEqual(process.returncode,1)
            result=rc.pytest_summary(out/'results.json')
            self.assertEqual((result['passed'],result['failed']),(0,3))
            self.assertEqual({f['stage'] for f in result['failures']},{'call','setup','teardown'})

    def test_guard_rejects_external_connect_before_network(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'sitecustomize.py').write_text(rc.GUARD)
            log=root/'blocked.jsonl'
            env=dict(os.environ,PYTHONPATH=str(root),TICKET_REGRESSION_NETWORK_LOG=str(log))
            process=subprocess.run([sys.executable,'-c',"import socket; socket.socket().connect(('203.0.113.1',443))"],env=env,capture_output=True,timeout=10)
            self.assertNotEqual(process.returncode,0)
            self.assertEqual(len(log.read_text().splitlines()),1)


if __name__=='__main__':unittest.main()
