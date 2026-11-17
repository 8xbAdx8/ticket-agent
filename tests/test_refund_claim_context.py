import unittest
from target.rag_faithfulness import _execution_claims

class RefundClaimsTests(unittest.TestCase):
 def test_policy_order_status_is_not_action(self):
  for text in ('已退款或已取消的订单不可再次支付。','已退款订单不得再次支付。','已退款的订单不可支付。'):
   self.assertEqual(_execution_claims(text,[])[1],[],text)
 def test_actual_claim_still_requires_tool(self):
  for text in ('我已退款。','系统已退款。','已退款成功。','已退款，请查看订单。'):
   self.assertTrue(_execution_claims(text,[])[1],text)
  event={'event':'tool_end','tool':'cancel_order','ok':True,'executed':True}
  self.assertEqual(_execution_claims('我已退款。',[event])[1],[])

 def test_paid_order_state_requires_matching_authoritative_record(self):
  text='你刚才的订单 OD123 已在有效期内完成支付，状态为「已支付」。'
  self.assertFalse(_execution_claims(text,[],{'OD123':'paid'})[1])
  self.assertTrue(_execution_claims(text,[],{'OD123':'pending'})[1])
  self.assertTrue(_execution_claims(text,[],{'OD999':'paid'})[1])
