import unittest
from target.diagnostics import evaluate

class CrossTurnAuditTests(unittest.TestCase):
 def test_linked_prior_turn_is_unknown_not_false_pass(self):
  e={'tool':'create_order','executed':True,'ok':True,'args':{'lock_id':'LK1'},'result':{'order_id':'OD1','lock_id':'LK1'}}
  auth={'available':True,'trains':[],'locks':[{'lock_id':'LK1','used':1}],'orders':[{'order_id':'OD1','lock_id':'LK1'}]}
  trace={'session_id':'s','user_msg':'确认下单','reply':'订单已创建','finish_reason':'stop'}
  checks=evaluate(trace,{'executions':[e],'model_requests':[]},auth)['assertions']
  self.assertIsNone(next(x for x in checks if x['assertion']=='create_order_requires_successful_lock')['passed'])
 def test_missing_lock_not_marked_pass(self):
  e={'tool':'create_order','executed':True,'ok':False,'args':{'lock_id':'LKmissing'},'result':{'error':'not found'}}
  auth={'available':True,'trains':[],'locks':[],'orders':[]}
  checks=evaluate({'session_id':'s','user_msg':'下单','reply':'失败','finish_reason':'stop'},{'executions':[e]},auth)['assertions']
  self.assertFalse(next(x for x in checks if x['assertion']=='create_order_requires_successful_lock')['passed'])
