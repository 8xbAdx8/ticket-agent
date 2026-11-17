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

    def test_developer_workspace_shows_principles_only(self):
        """开发者工作空间只讲设计原理；实时运行诊断视图已移除。"""
        env={'TICKET_WEB_OFFLINE_ONLY':'1','TICKET_DISABLE_LOCAL_SECRETS':'1',
             'DEEPSEEK_API_KEY':'','DASHSCOPE_API_KEY':'',
             'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'}
        with patch.dict(os.environ,env),patch.multiple(config,PROVIDER='mock',ENGINE='legacy',
                LC_TOOLSET='all',USE_HTTP_MOCK=False,USE_VECTOR_RAG=False):
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'web/app.py'),default_timeout=30).run()
            app.radio(key='workspace_mode').set_value('开发者工作台').run()
            self.assertEqual([e.message for e in app.exception],[])
            self.assertNotIn('developer_view',[r.key for r in app.radio])
            text='\n'.join([m.value for m in app.markdown]+[c.value for c in app.caption])
            self.assertNotIn('实时运行诊断',text)
            for name in ('思考分析','提示词设计','工具配置','Agent 知识库',
                         '记忆存储','工作流编排','风险控制'):
                self.assertIn(name,text)
            self.assertGreater(len(app.code),0)  # 源码块按符号实时读取


if __name__=='__main__':unittest.main()
