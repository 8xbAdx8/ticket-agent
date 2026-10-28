import json,tempfile,unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

class SessionViewsTests(unittest.TestCase):
 def test_session_views_and_historical_switch(self):
  root=Path('artifacts/runtime');root.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=root) as tmp:
   folder=Path(tmp)
   audit={'trace_id':'example-trace','provider':'deepseek_live','model':'deepseek-flash','judgement':{'quality_verdict':'indeterminate','dimensions':{'business_correct':None},'assertions':[]}}
   rag={'retrieval_id':'retrieval-one','trace_id':'example-trace','status':'retrieved','question':'锁座后多久支付','mode':'keyword','hits':[{'doc_id':'P11','title':'模拟政策','rank':1}]}
   (folder/'audit_runs.jsonl').write_text(json.dumps(audit,ensure_ascii=False)+'\n',encoding='utf-8')
   (folder/'rag_runs.jsonl').write_text(json.dumps(rag,ensure_ascii=False)+'\n',encoding='utf-8')
   common="from pathlib import Path\nfrom types import SimpleNamespace\ns=SimpleNamespace(mode='user',sid='web-fixture',trace_dir=Path("+repr(str(folder))+") )\n"
   app=AppTest.from_string(common+'from web.quality import quality_page\nquality_page([s])').run(timeout=20)
   self.assertFalse(app.exception)
   app.radio(key='quality_source').set_value('当前会话').run(timeout=20)
   self.assertTrue(any('有限规则质量判定' in t.value for t in app.markdown))
   app.radio(key='quality_source').set_value('B 历史测试').run(timeout=20)
   self.assertFalse(app.exception)
   ragapp=AppTest.from_string(common+'from web.rag_page import current_session_rag\ncurrent_session_rag([s])').run(timeout=20)
   self.assertFalse(ragapp.exception)
   self.assertEqual(len(ragapp.dataframe),1)
   self.assertEqual(ragapp.dataframe[0].value.iloc[0]['doc_id'],'P11')
 def test_empty_views(self):
  quality=AppTest.from_string('from web.quality import quality_page\nquality_page([])').run(timeout=20)
  rag=AppTest.from_string('from web.rag_page import current_session_rag\ncurrent_session_rag([])').run(timeout=20)
  self.assertFalse(quality.exception);self.assertFalse(rag.exception)
