import json,unittest
from web.formal_results import parse_formal_results,formal_dimensions

class ImportTests(unittest.TestCase):
 def setUp(self):
  self.audit={'test_case_label':'E01','trace_id':'a'*32,'provider':'deepseek_live','model':'deepseek-flash','public_trace':{'session_id':'S1'}}
  self.data={'schema':'ticket-agent-b-formal-results/1','batch':{'batch_id':'run1','git_sha':'b'*40,'provider':'deepseek_live','model':'deepseek-flash','mode':'live'},'results':[{'case_id':'E01','dimension':'边界','verdict':'pass','trace_id':'a'*32}]}
 def parse(self):return parse_formal_results(json.dumps(self.data).encode(),[self.audit],'S1')
 def test_verified_trace_link_and_dimension(self):
  result=self.parse();self.assertEqual(len(result['rows']),1)
  rows=formal_dimensions(result['rows']);d=next(r for r in rows if r['dimension']=='边界');self.assertEqual(d['rate'],1)
  self.assertIsNone(next(r for r in rows if r['dimension']=='性能')['rate'])
 def test_missing_trace_and_model_do_not_count(self):
  self.data['results'][0]['trace_id']='c'*32;self.assertEqual(self.parse()['rows'],[])
  self.data['results'][0]['trace_id']='a'*32;self.data['batch']['model']='other';self.assertEqual(self.parse()['rows'],[])
 def test_reject_wrong_dimension_duplicates_invalid_metadata(self):
  self.data['results'][0]['dimension']='性能'
  with self.assertRaises(ValueError):self.parse()
  self.data['results'][0]['dimension']='边界';self.data['results'].append(dict(self.data['results'][0]))
  with self.assertRaises(ValueError):self.parse()
 def test_unknown_does_not_count_as_pass_or_fail(self):
  self.data['results'][0]['verdict']='indeterminate';r=formal_dimensions(self.parse()['rows']);self.assertIsNone(next(x for x in r if x['dimension']=='边界')['rate'])

 def test_mode_must_match_provider(self):
  self.data['batch']['mode']='mock'
  with self.assertRaises(ValueError):self.parse()

 def test_requires_case_label_and_rejects_offline_fixture(self):
  self.audit['test_case_label']='E02';self.assertEqual(self.parse()['rows'],[])
  self.audit['test_case_label']='E01';self.audit['evidence_kind']='offline_sdk_stub';self.assertEqual(self.parse()['rows'],[])
