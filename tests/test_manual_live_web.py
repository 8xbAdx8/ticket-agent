"""Daily Live routing and export preferences: fake keys + MockTransport, no live calls."""
from contextlib import redirect_stdout
import io,json,os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import config


class ManualConfigTests(unittest.TestCase):
    def test_both_manual_profiles_are_unlimited_independent_and_readonly(self):
        from target.live_providers import manual_environment,validate_manual_binding
        from target.deepseek_runtime import Settings
        with tempfile.TemporaryDirectory() as folder,patch.object(config,'BASE_DIR',Path(folder)):
            root=Path(folder)/'artifacts/runtime/session'
            for provider in ('deepseek','bailian'):
                env=manual_environment(provider,root,model='qwen3.8-flash' if provider=='bailian' else 'deepseek-flash')
                self.assertEqual(env['DEEPSEEK_MAX_REQUESTS'],env['BAILIAN_MAX_REQUESTS'])
                self.assertEqual(env['BAILIAN_MAX_REQUESTS'],'0');self.assertEqual(env['TICKET_INITIAL_LIVE_BUDGET'],'')
                self.assertEqual(env['AGENT_LC_TOOLSET'],'read_only');self.assertEqual(env['RAG_ALLOW_NETWORK'],'0')
                setting=Settings(max_requests=0,ledger_path=Path(env['DEEPSEEK_BUDGET_PATH'] if provider=='deepseek' else env['BAILIAN_BUDGET_PATH']))
                with patch.dict(os.environ,env):validate_manual_binding(setting,provider)
                self.assertIn('manual-live',str(setting.ledger_path))
    def test_manual_binding_rejects_formal_path_and_shared_budget(self):
        from target.live_providers import validate_manual_binding
        from target.deepseek_runtime import Settings
        with patch.dict(os.environ,{'TICKET_INITIAL_LIVE_BUDGET':''}):
            with self.assertRaisesRegex(Exception,'manual_live_configuration'):
                validate_manual_binding(Settings(max_requests=0,ledger_path=Path('formal.db')),'deepseek')
    def test_daily_web_preflight_does_not_inherit_old_cli_limit(self):
        from scripts import launch_app
        with tempfile.TemporaryDirectory() as folder,patch.object(launch_app,'ROOT',Path(folder)),patch.dict(os.environ,
            {'DEEPSEEK_API_KEY':'offline-fixture','DEEPSEEK_MAX_REQUESTS':'5'},clear=True),\
             patch.object(launch_app,'missing_dependencies',return_value=[]):
            output=io.StringIO()
            with redirect_stdout(output):code=launch_app.main(['--mode','live','--check-only'])
            self.assertEqual(code,0)
            state=json.loads(output.getvalue());self.assertEqual(state['request_limit'],0)
            self.assertIn('manual-live',state['budget_path']);self.assertEqual(state['model_requests_sent'],0)
    def test_launcher_keeps_export_preference_but_disables_implicit_callbacks(self):
        from scripts.launch_app import build_environment
        env=build_environment('live',Path('runtime'),{'LANGCHAIN_TRACING_V2':'true'})
        self.assertEqual(env['TICKET_LANGSMITH_EXPORT_ENABLED'],'true')
        self.assertEqual(env['LANGCHAIN_TRACING_V2'],env['LANGSMITH_TRACING'])
        self.assertEqual(env['LANGSMITH_TRACING'],'false')
        env=build_environment('offline',Path('runtime'),{'DASHSCOPE_API_KEY':'offline-fake'})
        self.assertEqual(env['TICKET_WEB_OFFLINE_ONLY'],'1');self.assertNotIn('DASHSCOPE_API_KEY',env)
    def test_project_export_switch_no_network_no_key_written_and_survives_sdk_flags(self):
        from target import observability as obs
        with tempfile.TemporaryDirectory() as folder,patch.object(obs,'PREFERENCES',Path(folder)/'preferences.json'),patch.dict(os.environ,
            {'TICKET_DISABLE_LOCAL_SECRETS':'0','TICKET_WEB_OFFLINE_ONLY':'0','TICKET_OFFLINE_GUARD_LOG':'',
             'LANGCHAIN_API_KEY':'offline-secret-fixture','LANGSMITH_API_KEY':'','LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'}):
            with patch.dict(os.environ,{},clear=False):
                os.environ.pop('TICKET_LANGSMITH_EXPORT_ENABLED',None)
                obs.set_export_enabled(True);status=obs.configuration_status()
                self.assertTrue(status['enabled']);self.assertFalse(status['automatic_framework_export'])
                self.assertNotIn('offline-secret-fixture',obs.PREFERENCES.read_text())
                obs.set_export_enabled(False);self.assertFalse(obs.configuration_status()['enabled'])
                self.assertEqual(os.environ['TICKET_LANGSMITH_EXPORT_ENABLED'],'false')
                obs.set_export_enabled(True);self.assertTrue(obs.configuration_status()['enabled'])


try:
    import httpx
    import langchain_deepseek,langchain_openai
    SDK=True
except ImportError:SDK=False


@unittest.skipUnless(SDK,'Actual SDK test requires both installed packages; never paid API')
class ManualSDKTests(unittest.TestCase):
    def test_both_models_execute_tools_and_exceed_old_cumulative_cap_without_touching_formal_ledgers(self):
        from web import runtime
        from target import deepseek_runtime,bailian_runtime
        actual=config.BASE_DIR
        with tempfile.TemporaryDirectory(dir=actual/'artifacts/runtime') as tmp:
            root=Path(tmp);calls={};models=[]
            env={'DEEPSEEK_API_KEY':'offline-deepseek','DASHSCOPE_API_KEY':'offline-qwen',
                 'DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1','DASHSCOPE_MODEL':'qwen-plus',
                 'TICKET_WEB_OFFLINE_ONLY':'0','TICKET_DISABLE_LOCAL_SECRETS':'1','TICKET_API_VALIDATION_PROFILE':'',
                 'DEEPSEEK_MODEL':'deepseek-flash','DEEPSEEK_BASE_URL':'https://api.deepseek.com',
                 'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false','AGENT_RAG_MODE':''}
            def factory(provider,original):
                def create(settings):
                    def respond(request):
                        rows=calls.setdefault(provider,[]);body=json.loads(request.content);rows.append(body)
                        self.assertEqual({t['function']['name'] for t in body['tools']},{'query_tickets','search_policy'})
                        if len(rows)==1:
                            message={'tool_calls':[{'id':'ticket-'+provider,'type':'function','function':{'name':'query_tickets','arguments':json.dumps({
                                'from_city':'上海','to_city':'杭州','date':config.today().isoformat(),'kind':'高铁','seat_type':'二等座'})}}]}
                        else:message={'content':'当前仅支持模拟查票和政策咨询。'}
                        return httpx.Response(200,json={'id':'offline-manual','object':'chat.completion','created':1,
                            'model':'qwen3.8-flash' if provider=='bailian' else 'deepseek-flash',
                            'choices':[{'index':0,'message':{'role':'assistant',**message},'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}],
                            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
                    model=original(settings,transport=httpx.MockTransport(respond));models.append(model);return model
                return create
            with patch.dict(os.environ,env),patch.object(config,'BASE_DIR',root),patch.object(runtime,'LIVE_AVAILABLE',False),\
                 patch.object(deepseek_runtime,'make_model',side_effect=factory('deepseek',deepseek_runtime.make_model)),\
                 patch.object(bailian_runtime,'make_model',side_effect=factory('bailian',bailian_runtime.make_model)):
                for provider in ('deepseek','bailian'):
                    session=runtime.Conversation('user',engine='langchain',live=True,live_provider=provider,
                        live_model='qwen3.8-flash' if provider=='bailian' else None,interactive=True,root=root/'artifacts/runtime'/provider)
                    with redirect_stdout(io.StringIO()):
                        first=session.send('查今天上海到杭州的高铁','one')
                        for n in range(4):session.send('你好',str(n))
                    self.assertEqual(first['tool_sequence'],['query_tickets']);self.assertIsNone(session.error)
                    self.assertEqual(len(calls[provider]),6)
                    ledger=root/'artifacts/runtime/manual-live'/provider/'requests.db'
                    from target.deepseek_runtime import RequestBudget,Settings
                    self.assertEqual(RequestBudget(Settings(max_requests=0,ledger_path=ledger)).snapshot()['reserved_requests'],6)
                self.assertFalse((root/'artifacts/runtime/v33-live-providers').exists())
            for model in models:model.root_client.close()


class ManualUIBehaviorTests(unittest.TestCase):
    def test_daily_selectors_and_remote_switch_render_without_model_requests(self):
        from streamlit.testing.v1 import AppTest
        from target import observability as obs
        from web import runtime
        with tempfile.TemporaryDirectory() as folder,patch.object(obs,'PREFERENCES',Path(folder)/'ui.json'),\
             patch.multiple(config,PROVIDER='mock',ENGINE='legacy',LC_TOOLSET='all',USE_HTTP_MOCK=False,USE_VECTOR_RAG=False),\
             patch.dict(os.environ,{'TICKET_WEB_OFFLINE_ONLY':'0','TICKET_DISABLE_LOCAL_SECRETS':'1',
                'TICKET_LANGSMITH_EXPORT_ENABLED':'false','DEEPSEEK_API_KEY':'offline-deepseek',
                'DASHSCOPE_API_KEY':'offline-qwen','DASHSCOPE_MODEL':'qwen3.8-flash',
                'DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1',
                'LANGCHAIN_API_KEY':'offline-langsmith','LANGSMITH_API_KEY':'',
                'LANGCHAIN_TRACING_V2':'false','LANGSMITH_TRACING':'false'}),patch.object(runtime,'Agent') as agent:
            app=AppTest.from_file(str(config.BASE_DIR/'web/app.py'),default_timeout=30).run()
            for name in ('DeepSeek Live','Qwen3.8-Flash Live'):
                next(s for s in app.selectbox if s.label=='新会话模型').select(name).run()
                session=app.session_state['user_sessions'][app.session_state['user_session_index']]
                self.assertTrue(session.interactive);self.assertFalse(session.initial_budget)
                self.assertFalse(next(b for b in app.button if b.label=='发送').disabled)
                self.assertFalse(app.error)
                self.assertNotIn('沿用V3.5独立4次总账',''.join(m.value for m in app.info))
            next(r for r in app.radio if r.label=='工作空间').set_value('测试工作台').run()
            next(r for r in app.radio if r.label=='工作台导航').set_value('集成中心').run()
            next(b for b in app.button if b.label=='启用LangSmith脱敏导出').click().run()
            self.assertTrue(any(b.label=='关闭LangSmith脱敏导出' for b in app.button))
            self.assertFalse(app.exception);agent.assert_not_called()

    def test_failed_preflight_has_persistable_error_and_old_methods_stay_available(self):
        from web.runtime import Conversation,failure_hint
        session=Conversation('user',engine='langchain',live=True,interactive=True)
        with patch('web.runtime.live_ready',return_value=False):
            with self.assertRaises(ValueError):session.send('查票','no-key')
        self.assertIsNotNone(session.error);self.assertTrue(callable(session.export_last));self.assertTrue(callable(session.concurrency))
        self.assertIn('旧验收账本',failure_hint('historical_unlinked_ledger_requires_new_validation_pair'))
