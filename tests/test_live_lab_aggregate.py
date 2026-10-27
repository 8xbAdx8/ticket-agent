"""Real recorded simulated results, replayed completely offline."""
import copy
import json
import unittest
from pathlib import Path
from target.reply_consistency import check
from target.diagnostics import evaluate

FIXTURE=json.loads((Path(__file__).parent/'fixtures/live_lab_three_trains.json').read_text(encoding='utf-8'))
CLARIFY=json.loads((Path(__file__).parent/'fixtures/live_lab_qwen_clarification.json').read_text(encoding='utf-8'))
QWEN_AGGREGATE=json.loads((Path(__file__).parent/'fixtures/live_lab_qwen_aggregate.json').read_text(encoding='utf-8'))
DENIED=json.loads((Path(__file__).parent/'fixtures/live_lab_denied_train.json').read_text(encoding='utf-8'))
POLICY_EMPTY=json.loads((Path(__file__).parent/'fixtures/live_lab_empty_policy.json').read_text(encoding='utf-8'))

class AggregateAvailabilityAudit(unittest.TestCase):
    def test_policy_empty_is_not_a_ticket_empty_claim(self):
        result=check(POLICY_EMPTY['reply'],POLICY_EMPTY['events'])
        self.assertFalse(any(r['reason']=='empty_result_scope_unknown' for r in result['indeterminate']))
        self.assertTrue(any(c.get('comparison')=='policy_tool_returned_no_hits' for c in result['field_checks']))

    def test_policy_empty_evidence_must_exist_and_ticket_claims_still_checked(self):
        msg='查询政策知识库，没有检索到任何政策，返回结果无匹配。'
        self.assertEqual(check(msg,[])['status'],'indeterminate')
        self.assertEqual(check(msg,POLICY_EMPTY['events']*2)['status'],'indeterminate')
        nonempty=copy.deepcopy(POLICY_EMPTY['events']);nonempty[0]['result']['hits']=[{'doc_id':'P01','content':'test'}]
        self.assertEqual(check(msg,nonempty)['status'],'indeterminate')
        ticket=check(msg+' 查到 G9999 车次有余票。',POLICY_EMPTY['events'])
        self.assertEqual(ticket['status'],'indeterminate')
        self.assertTrue(any(r['reason']=='no_successful_authority' for r in ticket['indeterminate']))
        same=check('查询政策知识库，没有检索到任何政策，返回结果无匹配，但是查到 G9999 车次有余票。',POLICY_EMPTY['events'])
        self.assertTrue(any(r['reason']=='no_successful_authority' for r in same['indeterminate']))

    def test_real_explicit_result_denial_is_not_an_affirmation(self):
        result=check(DENIED['reply'],DENIED['events'])
        self.assertFalse(any(f.get('claimed')=='G9999' and f['error_type']=='unreturned_train' for f in result['findings']))
        self.assertTrue(any(c.get('comparison')=='train_absent_from_query_result' for c in result['field_checks']))

    def test_denial_requires_query_and_cannot_hide_affirmative_claim(self):
        denied='查询结果里没有 G9999 这个车次。'
        self.assertEqual(check(denied,[])['status'],'indeterminate')
        self.assertEqual(check(denied,DENIED['events']*2)['status'],'indeterminate')
        contradiction=check(denied.replace('G9999','G7301'),DENIED['events'])
        self.assertEqual(contradiction['status'],'failed')
        self.assertTrue(any(f['error_type']=='negative_train_mismatch' for f in contradiction['findings']))
        asserted=check(denied+'查到 G9998 有余票。',DENIED['events'])
        self.assertEqual(asserted['status'],'failed')
        self.assertTrue(any(f.get('claimed')=='G9998' for f in asserted['findings']))
        same_sentence=check('查询结果里没有 G9999 这个车次，但是查到 G9998 有余票。',DENIED['events'])
        self.assertTrue(any(f.get('claimed')=='G9998' for f in same_sentence['findings']))
        self.assertFalse(any(f.get('claimed')=='G9999' and f['error_type']=='unreturned_train' for f in same_sentence['findings']))
        # A broad statement about the entire database is not the same as absence in a query result.
        self.assertNotEqual(check('数据库里没有 G9999 这个车次。',DENIED['events'])['status'],'checked_fields_match')

    def test_real_qwen_grouped_train_cell_not_a_fictitious_train(self):
        result=check(QWEN_AGGREGATE['reply'],QWEN_AGGREGATE['events'])
        self.assertFalse(any(f['claimed']=='G101/G102/G103' and f['error_type']=='unreturned_train' for f in result['findings']))
        # The route was assumed by the model; field matching is not business success.
        self.assertNotEqual(result['verdict'],'consistent_for_checked_fields')

    def test_grouped_table_checks_each_train_and_inventory(self):
        events=copy.deepcopy(QWEN_AGGREGATE['events'])
        text='| 车次 | 席别 | 票价 | 余票 |\n|---|---|---|---|\n| G101/G102/G103 | 二等座 | ¥553.0 | 0（全部售罄） |'
        result=check(text,events)
        self.assertEqual(result['status'],'checked_fields_match',result)
        self.assertEqual({c['train_no'] for c in result['field_checks'] if c['field']=='train_no'}, {'G101','G102','G103'})
        bad_train=check(text.replace('G103','G9999'),events)
        self.assertEqual(bad_train['status'],'failed')
        self.assertTrue(any(f['error_type']=='unreturned_train' for f in bad_train['findings']))
        for row in events[0]['result']['trains']:
            if row['train_no']=='G102' and row['seat_type']=='二等座':row['seats_left']=2
        bad_stock=check(text,events)
        self.assertEqual(bad_stock['status'],'failed')
        self.assertTrue(any(f['field']=='seats_left' for f in bad_stock['findings']))
        self.assertEqual(check(text.replace('0（全部售罄）','0（有票）'),events)['status'],'indeterminate')

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
