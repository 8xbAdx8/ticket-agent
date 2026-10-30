import unittest
from web.run_evidence import workflow_rows,policy_evidence,rule_rows


class EvidenceChainTests(unittest.TestCase):
    def test_blocked_and_unknown_calls_are_not_executed(self):
        audit={'trace_id':'r','fault_report':{'executions':[{'tool':'pay_order','ok':False,'executed':False},
               {'tool':'query_order','ok':True}]}}
        rows=workflow_rows(audit)
        self.assertEqual(rows[0]['status'],'未执行／被拦截')
        self.assertEqual(rows[1]['status'],'是否执行未记录')
        self.assertIsNone(rows[0]['event_id'])
        self.assertNotIn('parent_event_id',audit['fault_report']['executions'][0])

    def test_policy_citation_links_only_actual_returned_documents(self):
        a={'trace_id':'r','public_trace':{'reply':'来源 P11；另一个编号 P110'}}
        results=[{'tool':'search_policy','ok':True,'result':{'hits':[{'doc_id':'P11','content':'原文'}]}}]
        rows=policy_evidence(a,results)
        self.assertEqual(rows[0]['trace_id'],'r');self.assertTrue(rows[0]['cited_in_reply'])
        self.assertIsNone(rows[0]['score']);self.assertIsNone(rows[0]['rank'])
        a['public_trace']['reply']='仅 P110'
        self.assertFalse(policy_evidence(a,results)[0]['cited_in_reply'])
        self.assertEqual(policy_evidence(a,[]),[])

    def test_rule_mapping_never_becomes_current_pass(self):
        rows=rule_rows('1. 不编造\n6. 权限', [{'id':'F01','name':'查询'}],{'code_commit':'old'})
        self.assertEqual(rows[0]['case_ids'],['F01'])
        self.assertEqual(rows[1]['case_ids'],[])
        self.assertTrue(all(r['verification']=='已配置，当前版本尚未验证' for r in rows))
