import unittest
from streamlit.testing.v1 import AppTest

class SummaryUITests(unittest.TestCase):
 def test_wrong_citation_is_explained_and_raw_collapsed(self):
  script="""from web.rag_page import render_mutation_result
render_mutation_result({'mutation':'rag_wrong_citation','executed':True,'real_api_requests':0,'normal_index_modified':False,'before':{'question':'锁座支付有效期'},'after':{'model_fixture_reply':'锁座15分钟 [P99]'},'judgement':{'detected':True,'assessment':{'allowed_doc_ids':['P11'],'wrong_citations':['P99']}}})"""
  app=AppTest.from_string(script).run(timeout=15)
  self.assertFalse(app.exception)
  self.assertTrue(any('已检出' in x.value for x in app.success))
  self.assertTrue(any('P99' in x.value for x in app.markdown))
  self.assertTrue(any('完整原始实验记录' in x.label for x in app.expander))
 def test_missing_verdict_is_not_success(self):
  app=AppTest.from_string("from web.rag_page import render_mutation_result\nrender_mutation_result({'mutation':'rag_wrong_citation','executed':True})").run(timeout=15)
  self.assertFalse(app.exception);self.assertEqual(len(app.success),0);self.assertTrue(app.warning)
