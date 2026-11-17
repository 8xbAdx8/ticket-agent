import json, tempfile, unittest
from pathlib import Path
from web.evidence import lab_record_rows, recent_lab_records

class CurrentLabTests(unittest.TestCase):
 def test_isolated_records_refresh_grouping_and_unknown(self):
  root=Path('artifacts/runtime');root.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=root) as tmp:
   lab=Path(tmp)/'lab'; lab.mkdir(); other=Path(tmp)/'user';other.mkdir()
   path=lab/'audit_runs.jsonl'
   one={'trace_id':'a','timestamp':'2026-01-01','provider':'mock','model':'mock-offline','judgement':{'quality_verdict':'pass','assertions':[{'result':'pass'}]},'public_trace':{'total_latency_ms':5}}
   two={'trace_id':'b','timestamp':'2026-01-02','provider':'deepseek_live','model':'deepseek-flash','judgement':{'quality_verdict':'fail','failure_reasons':[]}}
   other.joinpath('audit_runs.jsonl').write_text(json.dumps(one),encoding='utf-8')
   path.write_text(json.dumps(one)+'\n',encoding='utf-8')
   self.assertEqual(len(recent_lab_records([lab])[0]),1)
   with path.open('a',encoding='utf-8') as f:f.write(json.dumps(two)+'\n')
   records,status=recent_lab_records([lab,lab]);rows=lab_record_rows(records)
   self.assertEqual(len(rows),2)
   self.assertEqual(rows[0]['status'],'待判定')
   self.assertEqual(rows[1]['status'],'有限规则未发现问题')
   self.assertEqual({r['provider'] for r in rows},{'mock','deepseek_live'})
   self.assertIsNone(rows[0]['tokens'])
   self.assertFalse(status['truncated'])
   self.assertEqual(path.read_text(encoding='utf-8').count('\n'),2)
 def test_error_never_counted_as_pass(self):
  rows=lab_record_rows([{'provider':'bailian_live','error':{'category':'timeout'},'judgement':{'quality_verdict':'pass','assertions':[{'result':'pass'}]}}])
  self.assertEqual(rows[0]['status'],'执行异常')
 def test_missing_and_invalid_are_reported(self):
  root=Path('artifacts/runtime');root.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=root) as tmp:
   p=Path(tmp);(p/'audit_runs.jsonl').write_text('bad json\n',encoding='utf-8')
   rows,status=recent_lab_records([p,p/'missing'])
   self.assertEqual(rows,[]);self.assertEqual(status['invalid'],1)

 def test_streamlit_current_view_and_historical_switch(self):
  from streamlit.testing.v1 import AppTest
  root=Path('artifacts/runtime');root.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=root) as tmp:
   p=Path(tmp);record={'trace_id':'run1','timestamp':'2026-01-01','provider':'deepseek_live','model':'deepseek-flash','judgement':{'quality_verdict':'indeterminate'}}
   (p/'audit_runs.jsonl').write_text(json.dumps(record),encoding='utf-8')
   app=AppTest.from_string('from web.dashboard import dashboard_page\ndashboard_page([], ['+repr(str(p))+'])')
   app.run(timeout=20)
   self.assertFalse(app.exception)
   self.assertTrue(any('待判定' in m.value for m in app.markdown))
   app.selectbox(key='dashboard_owner').select('B 独立测试').run(timeout=20)
   self.assertFalse(app.exception)
   self.assertTrue(any('>101<' in m.value for m in app.markdown))
