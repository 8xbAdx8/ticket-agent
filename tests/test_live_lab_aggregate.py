"""Real recorded simulated results, replayed completely offline."""
import copy
import json
import unittest
from pathlib import Path
from target.reply_consistency import check
from target.diagnostics import evaluate

FIXTURE=json.loads((Path(__file__).parent/'fixtures/live_lab_three_trains.json').read_text(encoding='utf-8'))
CLARIFY=json.loads((Path(__file__).parent/'fixtures/live_lab_qwen_clarification.json').read_text(encoding='utf-8'))

class AggregateAvailabilityAudit(unittest.TestCase):
    def test_real_qwen_example_date_does_not_block_clarification(self):
        result=check(CLARIFY['reply'],CLARIFY['events'])
        self.assertEqual(result['status'],'not_verified',result['indeterminate'])

    def test_example_must_not_exempt_extra_unscoped_assertion(self):
        reply='请提供出行日期，例如 2026-11-03，另外余票为 23 张。'
        self.assertEqual(check(reply,[])['status'],'indeterminate')

    def test_real_trace_three_trains_are_supported(self):
        result=check(FIXTURE['reply'],FIXTURE['events'])
        self.assertEqual(result['status'],'checked_fields_match',result['indeterminate'])
        self.assertFalse(result['findings'])
        self.assertTrue(any(c.get('comparison')=='counted_all_available' for c in result['field_checks']))

    def test_aggregate_wrong_stock_is_not_ignored(self):
        data=copy.deepcopy(FIXTURE['events'])
        for row in data[0]['result']['trains']:
            if row['train_no']=='G7301':row['seats_left']=0
        result=check(FIXTURE['reply'],data)
        self.assertEqual(result['status'],'failed')
        self.assertTrue(any(f['error_type']=='availability_mismatch' for f in result['findings']))

    def test_aggregate_missing_evidence_and_ambiguous_scope_remain_unknown(self):
        data=copy.deepcopy(FIXTURE['events']);data[0]['result']['trains'][0].pop('seats_left')
        self.assertEqual(check(FIXTURE['reply'],data)['status'],'indeterminate')
        self.assertEqual(check(FIXTURE['reply'].replace('三趟车二等座','四趟车二等座'),FIXTURE['events'])['status'],'indeterminate')
        self.assertEqual(check(FIXTURE['reply'].replace('三趟车二等座','三趟车一等座'),FIXTURE['events'])['status'],'indeterminate')
        self.assertEqual(check(FIXTURE['reply'],FIXTURE['events']*2)['status'],'indeterminate')

    def test_business_unknown_does_not_become_false(self):
        public={'user_msg':'查询车票','reply':'未知','finish_reason':'stop'}
        report={'executions':[{'tool':'query_tickets','ok':True,'executed':True,'args':{},'result':{'trains':[]}}], 'model_requests':[]}
        authority={'available':True,'trains':[],'orders':[]}
        result=evaluate(public,report,authority,error={'category':'reply_data_indeterminate'})
        self.assertEqual(result['quality_verdict'],'indeterminate')
        self.assertIsNone(result['dimensions']['business_correct'])
        self.assertTrue(result['indeterminate_reasons'])

if __name__=='__main__':unittest.main()
