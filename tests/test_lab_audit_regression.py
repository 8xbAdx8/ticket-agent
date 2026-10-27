"""A-owned offline tests for reproducible test-lab audit findings."""
import tempfile
import unittest
from pathlib import Path

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


if __name__=='__main__':unittest.main()
