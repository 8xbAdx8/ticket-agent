"""Unverified and offline evidence must never appear as successful Live runs."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from web.rag_acceptance import provider_view


class ProviderViewTests(unittest.TestCase):
    def test_offline_sdk_success_is_not_live_success(self):
        report={'evidence_mode':'offline_sdk_stub','records':[{'provider':'bailian','real_function_calling_verified':True}]}
        self.assertEqual(provider_view(report,'bailian')['label'],'未验证')

    def test_protocol_and_guard_failure_can_coexist(self):
        record={'provider':'bailian','evidence_mode':'real_api','real_function_calling_verified':True,
                'agent_completed':False,'faithfulness':{'status':'failed'}}
        report={'evidence_mode':'real_api','records':[record],'same_tool_evidence_verified':True,
                'same_system_prompt_verified':True,'source_index_unchanged':True}
        view=provider_view(report,'bailian')
        self.assertEqual(view['label'],'真实工具闭环已验证');self.assertFalse(view['record']['agent_completed'])

    def test_page_view_does_not_call_generation_or_embedding(self):
        import config
        from streamlit.testing.v1 import AppTest
        env={'TICKET_WEB_OFFLINE_ONLY':'1','TICKET_DISABLE_LOCAL_SECRETS':'1','DASHSCOPE_API_KEY':'','DEEPSEEK_API_KEY':'',
             'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'}
        with patch.dict(os.environ,env),patch.multiple(config,PROVIDER='mock',ENGINE='legacy'),\
             patch('target.embeddings.EmbeddingProvider._request') as embedding,\
             patch('scripts.verify_v352_live.execute_pair') as generation:
            app=AppTest.from_file(str(config.BASE_DIR/'web/app.py'),default_timeout=30).run()
            next(r for r in app.radio if r.label=='工作空间').set_value('测试工作台').run()
            next(r for r in app.radio if r.label=='工作台导航').set_value('RAG 知识库').run()
            self.assertEqual([e.message for e in app.exception],[])
            self.assertTrue(any('V3.5.2 双模型' in s.value for s in app.subheader))
            self.assertTrue(any('未验证' in m.value for m in app.markdown))
            embedding.assert_not_called();generation.assert_not_called()
