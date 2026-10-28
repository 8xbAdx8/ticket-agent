import unittest
from web.trace_view import execution_counts,partial_mutation_blocked,timeline_items

class ExecutionDisplayTests(unittest.TestCase):
 def test_execution_counts_separate_blocked_and_unknown(self):
  a={'fault_report':{'executions':[{'executed':True},{'executed':False},{'executed':None},{}]}}
  self.assertEqual(execution_counts(a),{'executed':1,'not_executed':1,'unknown':2})
  self.assertIsNone(execution_counts({}))
 def test_m4_partially_executed_then_blocked(self):
  a={'mutation_events':[{'mutation_name':'infinite_loop','status':'blocked','before':1,'after':4,'related_tool_call_id':'a'}],
     'fault_report':{'executions':[{'tool':'monitor_seat','call_id':'a','executed':True} for _ in range(4)]+[{'tool':'monitor_seat','call_id':'a','executed':False}]}}
  self.assertTrue(partial_mutation_blocked(a))
  self.assertEqual(execution_counts(a)['executed'],4)
  self.assertEqual(execution_counts(a)['not_executed'],1)
  self.assertTrue(any(e['kind']=='未执行（含拦截）' for e in timeline_items(a)))
  a['fault_report']['executions'][1]['executed']=False
  a['fault_report']['executions'][2]['executed']=False
  a['fault_report']['executions'][3]['executed']=False
  self.assertFalse(partial_mutation_blocked(a))
 def test_missing_call_id_not_inferred(self):
  a={'mutation_events':[{'mutation_name':'infinite_loop','status':'blocked','before':1,'after':2}], 'fault_report':{'executions':[{'tool':'monitor_seat','executed':True}]*2}}
  self.assertFalse(partial_mutation_blocked(a))
