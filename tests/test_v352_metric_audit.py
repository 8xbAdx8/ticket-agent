import unittest
from scripts.audit_v352_metrics import recalculate


class IndependentMetricTests(unittest.TestCase):
    def case(self,ids):return [{'id':'q','expected_doc_ids':ids}]
    def result(self,ids):return {'q':{'hits':[{'doc_id':d} for d in ids]}}
    def test_multi_relevant_recall_is_not_hit_rate(self):
        r=recalculate(self.case(['P11','P12']),self.result(['P11','P12']))
        self.assertEqual(r['metrics']['recall_at_1']['fraction'],'1/2')
        self.assertEqual(r['metrics']['mrr']['fraction'],'1')
    def test_mrr_uses_first_relevant_rank_not_boolean_hit(self):
        r=recalculate(self.case(['P03']),self.result(['P01','P02','P03']))
        self.assertEqual(r['metrics']['mrr']['fraction'],'1/3')
    def test_cutoff_does_not_use_fourth_rank(self):
        r=recalculate(self.case(['P04']),self.result(['P01','P02','P03','P04']))
        self.assertEqual(r['metrics']['mrr']['fraction'],'0')
        self.assertEqual(r['metrics']['recall_at_3']['fraction'],'0')
    def test_negative_denominator_is_separate(self):
        r=recalculate([{'id':'p','expected_doc_ids':['P11']},{'id':'n','expected_doc_ids':[]}],
                      {'p':{'hits':[{'doc_id':'P11'}]},'n':{'hits':[{'doc_id':'P01'}]}})
        self.assertEqual(r['metrics']['mrr']['denominator'],1)
        self.assertEqual(r['metrics']['no_answer_false_recall_rate']['value'],1)
    def test_missing_and_failed_are_not_measured_zero(self):
        r=recalculate(self.case(['P01']),{})
        self.assertIsNone(r['metrics']['mrr']['value']);self.assertEqual(r['not_run_ids'],['q'])
        r=recalculate(self.case(['P01']),{'q':{'error':'test'}})
        self.assertEqual(r['indeterminate_ids'],['q'])
    def test_returned_order_not_resorted_and_duplicate_ids_are_deduped(self):
        r=recalculate(self.case(['P02']),self.result(['P01','P01','P02']))
        self.assertEqual(r['metrics']['mrr']['fraction'],'1/2')
    def test_duplicate_cases_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate_case'):
            recalculate(self.case(['P01'])*2,{})
