import unittest
from streamlit.testing.v1 import AppTest
from web.quality import session_assertion_counts

class SessionSummaryTests(unittest.TestCase):
 def test_counts_only_recorded_assertions(self):
  rows=[{'judgement':{'assertions':[{'passed':True},{'passed':False},{'passed':None},{'passed':1}]}}, {'judgement':{'assertions':[{'passed':True}]}}, {}]
  self.assertEqual(session_assertion_counts(rows),{'通过':2,'失败':1,'待判定':2})
 def test_render_empty_and_results(self):
  for script in ("show_session_audit_summary([])","show_session_audit_summary([{'judgement':{'assertions':[{'passed':True},{'passed':False},{'passed':None}]}}])"):
   app=AppTest.from_string('from web.quality import show_session_audit_summary\n'+script).run(timeout=15)
   self.assertFalse(app.exception)
   self.assertTrue(any('七维度正式测试状态' in h.value for h in app.subheader))
