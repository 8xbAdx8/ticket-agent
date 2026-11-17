import copy
import json
from pathlib import Path
import unittest
from target.rag_claim_audit import audit_claims
from target.rag_faithfulness import check_answer


class ClaimAuditTests(unittest.TestCase):
    def hit(self,content='模拟预约有效期30分钟，过期未支付自动释放库存；下单必须提供与预约一致的乘客列表。重复支付不重复扣减库存。',doc='P88'):
        return [{'doc_id':doc,'title':'预约规则','content':content,'version':'v1','source':'fixture.md#'+doc}]
    def audit(self,reply,hits=None,**kwargs):return audit_claims(reply,self.hit() if hits is None else hits,**kwargs)
    def test_footer_citation_needs_fact_proof_and_works_for_other_ids_values(self):
        r=self.audit('预约有效期为30分钟。\n来源：《预约规则》（doc_id:P88）')
        self.assertEqual(r['assertions'][0]['verdict'],'supported')
        self.assertEqual(r['assertions'][0]['citation_binding'],'explicit_single_document_footer')
    def test_footer_does_not_prove_unknown_statement(self):
        r=self.audit('提前付款一定更稳妥。\n来源：P88')
        self.assertEqual(r['verdict'],'INDETERMINATE')
    def test_prefix_applies_to_whole_paragraph_not_other_paragraph(self):
        r=self.audit('根据政策库（doc_id:P88）：预约有效期30分钟。重复支付不会重复扣减库存。\n\n预约有效期30分钟。')
        supported=[x for x in r['assertions'] if x['verdict']=='supported']
        self.assertTrue(any('重复支付' in x['assertion'] for x in supported))
        self.assertEqual(r['assertions'][-1]['verdict'],'indeterminate')
    def test_headers_and_footer_without_terminal_punctuation_are_not_dropped(self):
        r=self.audit('根据政策库查询结果：\n预约有效期30分钟。\n来源：P88')
        self.assertEqual(len(r['assertions']),3);self.assertEqual(r['assertions'][0]['rule'],'query_completion')
    def test_raw_spans_and_inputs_preserved(self):
        text='**预约有效期为30分钟。**\n来源：P88';hits=self.hit();before=copy.deepcopy(hits)
        r=self.audit(text,hits)
        self.assertEqual(hits,before);self.assertEqual(r['original_model_reply'],text)
        for x in r['assertions']:self.assertEqual(text[x['start']:x['end']],x['original_sentence'])
    def test_wrong_duration_is_contradicted_not_just_unknown(self):
        r=self.audit('预约有效期60分钟[P88]')
        self.assertEqual(r['assertions'][0]['verdict'],'contradicted');self.assertEqual(r['verdict'],'FAIL')
    def test_unit_conversion_not_equal_digit_match(self):
        self.assertEqual(self.audit('预约有效期0.5小时[P88]')['verdict'],'PASS')
        self.assertEqual(self.audit('预约有效期30小时[P88]')['verdict'],'FAIL')
    def test_entire_predicate_price_or_fee_wrong(self):
        hits=self.hit('延期收取5元。')
        r=self.audit('延期收取8元[P88]',hits)
        self.assertEqual(r['assertions'][0]['verdict'],'contradicted')
    def test_percentage_wrong_is_not_supported(self):
        self.assertEqual(self.audit('退票收取20%手续费[P88]',self.hit('退票收取10%手续费。'))['verdict'],'FAIL')
    def test_correct_number_does_not_prove_additional_compound_fact(self):
        r=self.audit('预约有效期30分钟且付款后可以无条件改签[P88]')
        self.assertEqual(len(r['assertions']),2);self.assertNotEqual(r['verdict'],'PASS')
    def test_requirement_without_numbers_is_checked(self):
        r=check_answer('下单必须提供与预约一致的乘客列表[P88]',self.hit())
        self.assertTrue(r['claim_checks']);self.assertEqual(r['claim_audit']['assertions'][0]['verdict'],'supported')
    def test_explicit_added_insurance_requirement_is_failed(self):
        r=check_answer('下单必须购买保险[P88]',self.hit())
        self.assertEqual(r['status'],'failed')
    def test_explicit_unstated_time_origin_is_unsupported(self):
        r=self.audit('预约有效期从支付完成时开始计时30分钟[P88]')
        self.assertEqual(r['assertions'][0]['verdict'],'unsupported')
    def test_model_cannot_relabel_simulated_policy_as_official(self):
        self.assertEqual(self.audit('铁路官方规定预约有效期30分钟[P88]')['verdict'],'FAIL')
    def test_wrong_or_absent_doc_id_cannot_pass(self):
        self.assertEqual(self.audit('预约有效期30分钟[P99]')['verdict'],'FAIL')
        self.assertEqual(self.audit('预约有效期30分钟')['verdict'],'INDETERMINATE')
    def test_stale_and_missing_versions_remain_distinct(self):
        self.assertEqual(self.audit('预约有效期30分钟[P88]',policy_versions={'P88':'v2'})['verdict'],'FAIL')
        hit=self.hit();hit[0].pop('version')
        self.assertEqual(self.audit('预约有效期30分钟[P88]',hit,policy_versions={'P88':'v1'})['verdict'],'INDETERMINATE')
    def test_wrong_title_is_cross_document_attribution_error(self):
        self.assertEqual(self.audit('来源：《行李规则》（doc_id:P88）')['verdict'],'FAIL')
    def test_user_quote_id_cannot_contaminate_following_assertion(self):
        r=self.audit('用户说“预约有效期60分钟[P99]”，请先核对您的问题。')
        self.assertFalse(any(x['verdict'] in ('unsupported','contradicted') for x in r['assertions']))
    def test_negative_scope_and_hedges_are_not_positive_errors(self):
        self.assertNotEqual(self.audit('P99未涉及该问题，无法确认。')['verdict'],'FAIL')
        self.assertEqual(self.audit('预约也许有效60分钟[P88]')['verdict'],'INDETERMINATE')
    def test_empty_evidence_refusal_and_positive_claim_separate(self):
        self.assertNotEqual(self.audit('没有相关政策依据，无法确认。',[])['verdict'],'FAIL')
        self.assertEqual(check_answer('预约有效期30分钟[P88]',[])['status'],'failed')
    def test_query_completion_requires_executed_success(self):
        text='根据政策库查询结果：\n来源：P88'
        self.assertEqual(self.audit(text)['verdict'],'FAIL')
        event={'event':'tool_end','tool':'search_policy','ok':True,'executed':True}
        self.assertNotEqual(self.audit(text,events=[event])['verdict'],'FAIL')
    def test_capability_not_inferred_from_prompt_or_absence_of_writes(self):
        r=self.audit('当前助手仅支持模拟查票和政策咨询，无法实际办理锁座、支付或下单。')
        self.assertEqual(r['counts']['indeterminate'],5)
        event={'event':'tool_end','tool':'search_policy','ok':True,'executed':True}
        r=self.audit(r['original_model_reply'],events=[event])
        self.assertEqual(r['counts']['supported'],1);self.assertEqual(r['counts']['indeterminate'],4)
    def test_verified_runtime_binding_can_decide_capabilities_but_is_separate_authority(self):
        r=self.audit('当前助手仅支持模拟查票和政策咨询，无法实际执行锁座或支付操作。',
            capability_evidence={'runtime_tool_binding_verified':True,'allowed_tools':['query_tickets','search_policy']})
        self.assertEqual(r['verdict'],'PASS')
    def test_self_contradiction_not_masked_by_one_correct_number(self):
        r=self.audit('预约有效期30分钟[P88]；预约有效期60分钟[P88]。')
        self.assertTrue(r['self_conflicts']);self.assertEqual(r['verdict'],'FAIL')
    def test_explicit_query_and_modification_claims_require_actual_tools(self):
        for text in ('我已经查询订单。','我已修改订单。','我已查询政策。','我已查询余票。'):
            self.assertEqual(check_answer(text,self.hit())['status'],'failed',text)
        event={'event':'tool_end','tool':'query_order','ok':True,'executed':True}
        self.assertNotEqual(check_answer('我已查询订单。',self.hit(),events=[event])['status'],'failed')
    def test_atomic_unknown_is_exposed_in_legacy_manual_review(self):
        r=check_answer('当前助手仅支持模拟查票和政策咨询，无法实际执行锁座或支付操作。',self.hit())
        self.assertTrue(any(x['reason']=='atomic_runtime_capability_evidence_missing' for x in r['manual_review']))
    def test_ticket_result_header_not_misclassified_as_policy_query(self):
        self.assertNotEqual(check_answer('根据余票查询结果：',self.hit())['status'],'failed')
    def test_real_whole_replies_have_no_missing_requirement_clause(self):
        root=Path(__file__).resolve().parent.parent
        saved=json.loads((root/'docs/evidence/v352/live/paired-report-resumed.json').read_text(encoding='utf-8'))
        for row in saved['records']:
            hits=row['delivered_evidence'][0]['tool_result']['hits']
            r=self.audit(row['original_model_reply'],hits,events=row['live_evidence']['events'],policy_versions={h['doc_id']:h['version'] for h in hits})
            self.assertEqual(r['factual_assertions'],10);self.assertEqual(r['verdict'],'INDETERMINATE')
            self.assertEqual(r['counts']['contradicted']+r['counts']['unsupported'],0)
            requirement=next(x for x in r['assertions'] if '乘客列表' in x['assertion'])
            self.assertEqual(requirement['verdict'],'supported')
            self.assertEqual(r['counts']['indeterminate'],3 if row['provider']=='bailian' else 4)
