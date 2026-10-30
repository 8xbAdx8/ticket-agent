"""Offline interaction checks for the shared UI; no model API is configured."""
import json
import os
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import config
from web.design import table, processing_event


class UIProTests(unittest.TestCase):
    def test_sorting_changes_table_and_export_together(self):
        rows=[{'position':i,'name':'row '+str(i)} for i in range(21)]
        with patch('web.design.st.expander',return_value=nullcontext()), \
             patch('web.design.st.selectbox',return_value='position'), \
             patch('web.design.st.checkbox',return_value=True), \
             patch('web.design.st.markdown') as markup, \
             patch('web.design.st.caption'), \
             patch('web.design.st.download_button') as download:
            table(rows,'sort-check',search=False)
        html=markup.call_args.args[0]
        csv=download.call_args.args[1].decode('utf-8-sig')
        self.assertLess(html.index('row 20'),html.index('row 19'))
        self.assertEqual(csv.splitlines()[1],'20,row 20')
        self.assertEqual(rows[0]['position'],0)  # The source evidence is unchanged.

    def test_processing_reports_real_blocked_event_and_escapes_tool_name(self):
        html=processing_event({'event_type':'permission_check','status':'blocked','tool':'<script>'})
        self.assertIn('权限检查 · 已拦截',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script>',html)
        self.assertNotIn('成功',html)

    def test_select_workflow_node_shows_its_actual_event(self):
        env={'TICKET_WEB_OFFLINE_ONLY':'1','TICKET_DISABLE_LOCAL_SECRETS':'1',
             'DEEPSEEK_API_KEY':'','DASHSCOPE_API_KEY':'',
             'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'}
        with patch.dict(os.environ,env),patch.multiple(config,PROVIDER='mock',ENGINE='legacy',
                LC_TOOLSET='all',USE_HTTP_MOCK=False,USE_VECTOR_RAG=False):
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'web/app.py'),default_timeout=30).run()
            next(t for t in app.text_input if t.label=='输入消息').set_value('查明天上海到杭州的高铁二等座')
            next(b for b in app.button if b.label=='发送').click().run()
            session=app.session_state['user_sessions'][0]
            trace_id=session.audits[-1]['trace_id']
            events=[json.loads(line) for line in (session.trace_dir/'run_events.jsonl').read_text(encoding='utf-8').splitlines()]
            events=[e for e in events if e['run_id']==trace_id]
            index=next(i for i,e in enumerate(events) if e['event_type']=='tool_result')
            app.radio(key='workspace_mode').set_value('开发者工作台').run()
            app.button(key='selected_event_'+trace_id+'_'+str(index)).click().run()
            self.assertEqual([e.message for e in app.exception],[])
            selected=[json.loads(j.value) for j in app.json if 'event_type' in j.value]
            self.assertTrue(any(e.get('event_id')==events[index]['event_id'] and e.get('run_id')==trace_id for e in selected))
            next(c for c in app.checkbox if c.label=='纵向布局（窄屏）').check().run()
            self.assertEqual([e.message for e in app.exception],[])
            self.assertEqual(len(session.history),1)  # Viewing evidence never reruns the Agent.


if __name__=='__main__':unittest.main()
