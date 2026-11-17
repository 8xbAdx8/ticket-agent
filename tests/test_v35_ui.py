"""RAG page rerenders and explicit keyword retrieval are offline; original B tests untouched."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import config
from streamlit.testing.v1 import AppTest


class RagPageTests(unittest.TestCase):
    def test_page_load_and_keyword_action_do_not_create_model_or_embedding_client(self):
        env={'TICKET_WEB_OFFLINE_ONLY':'1','TICKET_DISABLE_LOCAL_SECRETS':'1','DASHSCOPE_API_KEY':'',
             'DEEPSEEK_API_KEY':'','LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'}
        with patch.dict(os.environ,env),patch.multiple(config,PROVIDER='mock',ENGINE='legacy'):
            with patch('target.embeddings.EmbeddingProvider._request') as request:
                app=AppTest.from_file(str(config.BASE_DIR/'web/app.py'),default_timeout=30).run()
                next(r for r in app.radio if r.label=='工作空间').set_value('测试工作台').run()
                next(r for r in app.radio if r.label=='工作台导航').set_value('RAG 知识库').run()
                self.assertEqual([e.message for e in app.exception],[])
                self.assertIn('Qwen3.8-Flash Live',next(s for s in app.selectbox if s.label=='新会话模型').options)
                next(s for s in app.selectbox if s.label=='政策检索模式').select('keyword').run()
                next(b for b in app.button if b.label=='检索政策证据').click().run()
                self.assertEqual([e.message for e in app.exception],[])
                self.assertTrue(app.session_state['rag_retrieval_result']['hits'])
                self.assertEqual(app.session_state['rag_retrieval_result']['hits'][0]['doc_id'],'P11')
                request.assert_not_called()
