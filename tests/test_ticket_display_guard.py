import unittest
from types import SimpleNamespace
from unittest.mock import patch
from target.diagnostics import digest
from web.conversation import unsafe_ticket_result,show_guarded_reply

class TicketDisplayGuardTests(unittest.TestCase):
 def setUp(self):
  self.record={'session_id':'one','user_msg':'查票','reply':'G9999 有票','tool_sequence':['query_tickets'],'steps':[]}
  self.audit={'public_trace':self.record.copy(),'public_trace_sha256':digest(self.record),'judgement':{'hallucination':{'hallucination_detected':True},'assertions':[]}}
  self.session=SimpleNamespace(audits=[self.audit])
 def test_detected_train_hides_reply(self):
  with patch('web.conversation.st.warning') as warning,patch('web.conversation.st.write') as write:
   show_guarded_reply(self.session,self.record)
   warning.assert_called_once();write.assert_not_called()
  self.assertEqual(self.record['reply'],'G9999 有票')
 def test_tool_evidence_and_normal(self):
  self.audit['judgement']={'assertions':[{'assertion':'query_result_train_authority','passed':False}]}
  self.assertTrue(unsafe_ticket_result(self.session,self.record))
  self.audit['judgement']={'assertions':[{'assertion':'query_result_train_authority','passed':True}]}
  self.assertFalse(unsafe_ticket_result(self.session,self.record))
 def test_unrelated_audit_and_sanitized_trace(self):
  self.assertFalse(unsafe_ticket_result(self.session,dict(self.record,reply='other')))
  self.audit['public_trace']={'redacted':True}
  self.assertTrue(unsafe_ticket_result(self.session,self.record))
