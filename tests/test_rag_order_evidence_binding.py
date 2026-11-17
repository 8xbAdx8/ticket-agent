import unittest
from target.rag_faithfulness import _execution_claims

class OrderBindingTests(unittest.TestCase):
 def setUp(self):
  self.event={'event':'tool_end','tool':'pay_order','ok':True,'executed':True,'args':{'order_id':'ODreal'},'result':{'order_id':'ODreal','status':'paid'}}
 def test_other_order_cannot_prove_claim(self):
  self.assertTrue(_execution_claims('我已支付订单 ODfake。',[self.event])[1])
 def test_matching_order_before_and_after(self):
  for text in ('订单 ODreal 已支付。','我已支付订单 ODreal。'):
   self.assertFalse(_execution_claims(text,[self.event])[1],text)
 def test_failed_or_unexecuted_tool_not_evidence(self):
  for field in ('ok','executed'):
   event={**self.event,field:False}
   self.assertTrue(_execution_claims('我已支付订单 ODreal。',[event])[1])
 def test_multiple_ids_not_treated_as_proof(self):
  self.assertTrue(_execution_claims('订单 ODreal 和 ODfake 已支付。',[self.event],{'ODreal':'paid'})[1])
 def test_known_paid_state_and_policy_status(self):
  self.assertFalse(_execution_claims('订单 ODreal 已支付。',[],{'ODreal':'paid'})[1])
  self.assertTrue(_execution_claims('订单 ODreal 已支付。',[],{'ODreal':'pending'})[1])
  self.assertFalse(_execution_claims('已退款或已取消的订单不可支付。',[])[1])
