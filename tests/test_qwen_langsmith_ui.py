"""Provider navigation and LangSmith flow: deterministic offline UI tests."""
import os
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import config
from streamlit.testing.v1 import AppTest


class QwenNavigationTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'TICKET_DISABLE_LOCAL_SECRETS':'1','TICKET_WEB_OFFLINE_ONLY':'0',
            'DEEPSEEK_API_KEY':'offline-deepseek-fixture','DASHSCOPE_API_KEY':'offline-qwen-fixture',
            'DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1','DASHSCOPE_MODEL':'qwen3.8-flash',
            'LANGCHAIN_API_KEY':'offline-langsmith-fixture','LANGSMITH_API_KEY':'',
            'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false','TICKET_LANGSMITH_EXPORT_ENABLED':'true'})
        self.cfg=patch.multiple(config,PROVIDER='deepseek',ENGINE='langchain',USE_HTTP_MOCK=False,USE_VECTOR_RAG=False)
        self.env.start();self.cfg.start()
        self.app=AppTest.from_file(str(config.BASE_DIR/'web/app.py'),default_timeout=30).run()

    def tearDown(self):self.cfg.stop();self.env.stop()

    def active(self):return self.app.session_state['user_sessions'][self.app.session_state['user_session_index']]

    def select(self,name):
        next(s for s in self.app.selectbox if s.label=='新会话模型').select(name).run()
        self.assertFalse(self.app.exception)
        return self.active()

    def roundtrip(self):
        next(r for r in self.app.radio if r.label=='工作空间').set_value('测试工作台').run()
        next(r for r in self.app.radio if r.label=='工作台导航').set_value('集成中心').run()
        next(r for r in self.app.radio if r.label=='工作空间').set_value('出行助手').run()

    def test_qwen_stays_active_after_opening_integration_center(self):
        from web import runtime
        with patch.object(runtime,'Agent') as agent:
            qwen=self.select('Qwen3.8-Flash Live');self.roundtrip()
            self.assertFalse(self.app.exception)
            self.assertEqual(self.active().sid,qwen.sid)
            self.assertEqual(self.active().live_provider,'bailian')
            self.assertTrue(any(c.label=='确认发送真实 Qwen3.8-Flash 请求（会产生 API 费用）' for c in self.app.checkbox))
            agent.assert_not_called()

    def test_new_qwen_session_stays_active_after_workbench_roundtrip(self):
        self.select('Qwen3.8-Flash Live')
        next(b for b in self.app.button if b.label=='新建会话').click().run()
        qwen=self.active();self.roundtrip()
        self.assertEqual(self.active().sid,qwen.sid);self.assertEqual(self.active().live_model,'qwen3.8-flash')

    def test_explicit_history_selection_is_preserved_and_model_is_explained(self):
        deep=self.active();self.select('Qwen3.8-Flash Live')
        next(s for s in self.app.selectbox if s.label=='历史会话').select(0).run()
        self.roundtrip()
        self.assertEqual(self.active().sid,deep.sid)
        self.assertTrue(any('正在查看历史会话' in i.value and 'DeepSeek' in i.value for i in self.app.info))

    def test_live_fee_consent_does_not_follow_a_different_provider(self):
        next(c for c in self.app.checkbox if c.label.startswith('确认发送真实')).check().run()
        self.select('Qwen3.8-Flash Live')
        self.assertFalse(next(c for c in self.app.checkbox if c.label.startswith('确认发送真实')).value)

    def test_empty_qwen_run_has_a_clear_reason_and_disabled_export(self):
        self.select('Qwen3.8-Flash Live')
        self.assertTrue(any('当前 Qwen3.8-Flash 会话还没有已保存的执行记录' in i.value for i in self.app.info))
        self.assertTrue(next(b for b in self.app.button if b.label=='导出本轮并验证远端').disabled)
        self.assertIsNone(self.active().agent)

    def test_qwen_panel_rejects_another_provider_record_without_export(self):
        session=self.select('Qwen3.8-Flash Live')
        session.agent=SimpleNamespace(langchain_engine=SimpleNamespace(last_live_run={'provider':'deepseek_live'}))
        with patch.object(session,'export_last') as upload:
            self.app.run()
            self.assertTrue(any('模型来源与当前会话不匹配' in e.value for e in self.app.error))
            self.assertFalse(any(b.label=='导出本轮并验证远端' for b in self.app.button));upload.assert_not_called()


try:
    import httpx
    import langchain_openai
    SDK=True
except ImportError:SDK=False


@unittest.skipUnless(SDK,'Actual Qwen SDK protocol test; all HTTP is intercepted offline')
class QwenExportFlowTests(unittest.TestCase):
    def test_actual_qwen_sdk_tool_run_can_export_through_web_with_mock_http(self):
        from target import bailian_runtime
        from web import runtime
        from target.observability import export_payload
        base=config.BASE_DIR
        with tempfile.TemporaryDirectory(dir=base/'artifacts/runtime') as folder:
            root=Path(folder);calls=[];models=[];exports=[];posted={}
            env={'DASHSCOPE_API_KEY':'offline-qwen-fixture','DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1',
                'DASHSCOPE_MODEL':'qwen3.8-flash','TICKET_DISABLE_LOCAL_SECRETS':'1','TICKET_WEB_OFFLINE_ONLY':'0',
                'TICKET_API_VALIDATION_PROFILE':'','LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false',
                'LANGCHAIN_API_KEY':'offline-langsmith-fixture','LANGSMITH_API_KEY':'','TICKET_LANGSMITH_EXPORT_ENABLED':'true',
                'LANGCHAIN_PROJECT':'fixture','LANGSMITH_PROJECT':'','LANGCHAIN_ENDPOINT':'https://api.smith.langchain.com',
                'LANGSMITH_ENDPOINT':'','LANGCHAIN_WORKSPACE_ID':'','LANGSMITH_WORKSPACE_ID':'','AGENT_RAG_MODE':''}
            def model_response(request):
                body=json.loads(request.content);calls.append(body)
                self.assertEqual(body['model'],'qwen3.8-flash')
                self.assertEqual({t['function']['name'] for t in body['tools']},{'query_tickets','search_policy'})
                message={'role':'assistant','content':'当前仅支持模拟查票和政策咨询。'}
                if len(calls)==1:
                    message.update(content=None,tool_calls=[{'id':'qwen-offline-query','type':'function','function':{
                        'name':'query_tickets','arguments':json.dumps({'from_city':'上海','to_city':'杭州',
                        'date':config.today().isoformat(),'kind':'高铁','seat_type':'二等座'})}}])
                return httpx.Response(200,json={'id':'offline-qwen-response','object':'chat.completion','created':1,
                    'model':'qwen3.8-flash','choices':[{'index':0,'message':message,'finish_reason':'tool_calls' if len(calls)==1 else 'stop'}],
                    'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
            original_model=bailian_runtime.make_model
            def make(settings):
                model=original_model(settings,transport=httpx.MockTransport(model_response));models.append(model);return model
            def observe(request):
                exports.append(request.method)
                if request.method=='POST':
                    posted.update(json.loads(request.content))
                    self.assertEqual(posted['extra']['metadata']['provider'],'bailian_live')
                    self.assertEqual(posted['extra']['metadata']['requested_model'],'qwen3.8-flash')
                    return httpx.Response(202,json={'message':'accepted'})
                return httpx.Response(200,json=posted)
            try:
                with patch.dict(os.environ,env),patch.object(config,'BASE_DIR',root),patch.object(runtime,'LIVE_AVAILABLE',False),\
                     patch.object(bailian_runtime,'make_model',side_effect=make):
                    session=runtime.Conversation('user',engine='langchain',live=True,live_provider='bailian',
                        live_model='qwen3.8-flash',interactive=True,root=root/'artifacts/runtime/session')
                    with redirect_stdout(io.StringIO()):record=session.send('查今天上海到杭州的高铁二等座','qwen-export-test')
                    self.assertEqual(record['provider'],'bailian_live');self.assertEqual(record['tool_sequence'],['query_tickets'])
                    self.assertTrue(any(m['role']=='tool' and m['tool_call_id']=='qwen-offline-query' for m in calls[1]['messages']))
                    run=session.agent.langchain_engine.last_live_run
                    self.assertTrue(run['local_sidecar_saved']);self.assertTrue(run['local_trace_saved'])
                    app=AppTest.from_string("import streamlit as st\nfrom web.conversation import show_remote_export\nshow_remote_export(st.session_state['session'])",default_timeout=30)
                    app.session_state['session']=session
                    original_export=session.export_last
                    with patch.object(session,'export_last',side_effect=lambda **kw:original_export(**kw,transport=httpx.MockTransport(observe))):
                        app.run();self.assertFalse(app.exception);self.assertFalse(exports)
                        self.assertTrue(next(b for b in app.button if b.label=='导出本轮并验证远端').disabled)
                        next(c for c in app.checkbox if c.label.startswith('我已检查脱敏内容')).check().run()
                        next(b for b in app.button if b.label=='导出本轮并验证远端').click().run()
                        self.assertFalse(app.exception);self.assertEqual(exports,['POST','GET'])
                        self.assertTrue(session.remote_receipts[-1]['remote_verified'])
                        app.run();self.assertEqual(exports,['POST','GET']);self.assertEqual(len(calls),2)
                        self.assertFalse(any(b.label=='导出本轮并验证远端' for b in app.button))
                    self.assertNotIn('offline-qwen-fixture',json.dumps(export_payload(run)))
                    if os.getenv('QWEN_LANGSMITH_UI_EVIDENCE_OUT'):
                        out=Path(os.environ['QWEN_LANGSMITH_UI_EVIDENCE_OUT']).resolve()
                        self.assertTrue(out.is_relative_to(base/'artifacts/runtime'));out.mkdir(parents=True,exist_ok=False)
                        report={'execution_mode':'offline_mock_transport','provider':run['provider'],'model':run['actual_models'],
                            'tool_sequence':record['tool_sequence'],'model_fixture_requests':len(calls),'langsmith_fixture_methods':exports,
                            'actual_generation_requests':0,'actual_langsmith_requests':0,'export_receipt':session.remote_receipts[-1]}
                        (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            finally:
                for model in models:model.root_client.close()
