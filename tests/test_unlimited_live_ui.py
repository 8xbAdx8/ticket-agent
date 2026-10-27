"""Explicit Web/CLI dispatch checks. All model traffic is SDK MockTransport."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parent.parent
try:
    import test_deepseek_agent as deep_fixture
    import test_live_providers as bailian_fixture
    from streamlit.testing.v1 import AppTest
    AVAILABLE=deep_fixture.AVAILABLE and bailian_fixture.AVAILABLE
except ImportError:
    AVAILABLE=False


@unittest.skipUnless(AVAILABLE,'Streamlit and SDK environment required; no paid requests')
class LivePageTests(unittest.TestCase):
    def run_page(self,provider,page):
        from web.runtime import Conversation
        cls=deep_fixture.DeepSeekAgentTests if provider=='deepseek' else bailian_fixture.LiveProviderTests
        fixture=cls()
        with contextlib.redirect_stdout(io.StringIO()):fixture.setUp()
        try:
            agent=fixture.agent([fixture.response({'content':'请提供出发地、目的地和日期。'})])
            session=Conversation('user' if page=='user' else 'lab',engine='langchain',live=True,live_provider=provider,
                initial_budget=True,interactive=False,root=ROOT/'artifacts/runtime'/('unlimited-ui-'+uuid.uuid4().hex))
            session.agent=agent
            script='from web.conversation import user_page\nuser_page()' if page=='user' else 'from web.laboratory import lab_page\nlab_page()'
            app=AppTest.from_string(script)
            if page=='user':
                for k,v in {'user_sessions':[session],'default_engine':'langchain','default_live':True,'default_provider':provider,
                    'default_live_model':None,'user_provider_signature':('langchain',True,provider,None,'manual-live-v1')}.items():app.session_state[k]=v
            else:
                app.session_state['lab_engine']='Qwen3.8-Flash Live · 只读' if provider=='bailian' else 'DeepSeek Live · 只读'
            with patch('web.runtime.live_ready',return_value=True),patch('web.conversation.live_ready',return_value=True),\
                 patch('web.laboratory.live_ready',return_value=True),patch('web.laboratory.Conversation',return_value=session),\
                 patch.object(session,'_values',return_value={}),patch.dict(os.environ,{'TICKET_LANGSMITH_EXPORT_ENABLED':'false'}):
                app.run(timeout=20)
                self.assertFalse(app.exception);self.assertEqual(len(fixture.payloads),0)
                label='发送' if page=='user' else '执行测试';key='user_allow_live' if page=='user' else 'lab_allow_live'
                if page=='user':app.text_input(key='user_message').set_value('您好')
                button=next(b for b in app.button if b.label==label)
                self.assertFalse(button.disabled)
                button.click().run(timeout=20)
                self.assertFalse(app.exception);self.assertEqual(len(fixture.payloads),0)
                app.checkbox(key=key).check().run(timeout=20)
                self.assertEqual(len(fixture.payloads),0)  # Permission alone never dispatches.
                for _ in range(7):
                    app.checkbox(key=key).check()
                    if page=='user':app.text_input(key='user_message').set_value('您好')
                    next(b for b in app.button if b.label==label).click().run(timeout=20)
                    self.assertFalse(app.exception);self.assertIsNone(session.error)
                self.assertEqual(len(fixture.payloads),7)
                self.assertEqual(len(session.history),7)
                self.assertTrue(all(r['tool_sequence']==[] for r in session.history))
        finally:
            fixture.tearDown()


def ui_case(provider,page):
    def run(self):self.run_page(provider,page)
    return run


for _provider in ('deepseek','bailian'):
    for _page in ('user','lab'):
        setattr(LivePageTests,'test_'+_provider+'_'+_page,ui_case(_provider,_page))


@unittest.skipUnless(AVAILABLE,'full environment needed')
class RagPageTests(unittest.TestCase):
    def test_online_embedding_requires_checkbox_and_button_and_never_rebuilds_baseline(self):
        index=Mock();index.status.return_value={'state':'ready','immutable_baseline':True,'chunk_count':15}
        retrieve=Mock(return_value={'question':'锁座后多久必须完成支付？','hits':[],'count':0})
        with patch.dict(os.environ,{'TICKET_WEB_OFFLINE_ONLY':'0'}),patch('target.rag_service.configured_index',return_value=index),\
             patch('target.rag_service.retrieve',retrieve):
            app=AppTest.from_string('from web.rag_page import rag_page\nrag_page()').run(timeout=25)
            self.assertFalse(app.exception);retrieve.assert_not_called();index.build.assert_not_called()
            self.assertFalse(app.checkbox(key='rag_network_consent').disabled)
            app.checkbox(key='rag_network_consent').check().run(timeout=25)
            retrieve.assert_not_called()
            self.assertTrue(app.button(key='rag_build').disabled)
            app.button(key='rag_retrieve').click().run(timeout=25)
            self.assertFalse(app.exception)
            self.assertTrue(retrieve.call_args.kwargs['allow_network'])
            index.build.assert_not_called()

    def test_offline_rag_network_remains_disabled(self):
        index=Mock();index.status.return_value={'state':'ready','immutable_baseline':True,'chunk_count':15}
        with patch.dict(os.environ,{'TICKET_WEB_OFFLINE_ONLY':'1'}),patch('target.rag_service.configured_index',return_value=index):
            app=AppTest.from_string('from web.rag_page import rag_page\nrag_page()').run(timeout=25)
            self.assertFalse(app.exception)
            self.assertTrue(app.checkbox(key='rag_network_consent').disabled)


class PreflightTests(unittest.TestCase):
    def test_legacy_audit_unreadable_history_is_unknown_and_never_admission(self):
        import tempfile
        from scripts import verify_v34_live
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            old=root/'artifacts/runtime/v33-live-providers/deepseek/requests.db'
            old.parent.mkdir(parents=True)
            raw=b'corrupt historical ledger: do not repair'
            old.write_bytes(raw)
            with patch.object(verify_v34_live,'ROOT',root):
                result=verify_v34_live.old_reconciliation()
            self.assertIsNone(result['provider_total'])
            self.assertFalse(result['identity_linkage_verified'])
            self.assertEqual(old.read_bytes(),raw)

    def test_both_cli_profiles_ignore_obsolete_count_settings_without_requests(self):
        directory=ROOT/'artifacts/runtime'/('unlimited-cli-'+uuid.uuid4().hex)
        env=dict(os.environ,TICKET_DISABLE_LOCAL_SECRETS='1',DEEPSEEK_API_KEY='offline-cli-key',
                 DASHSCOPE_API_KEY='offline-cli-key',DASHSCOPE_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1',
                 DEEPSEEK_MAX_REQUESTS='invalid-old-limit',BAILIAN_MAX_REQUESTS='invalid-old-limit',
                 TICKET_TOTAL_REQUEST_LIMIT='invalid-old-limit',TICKET_API_USAGE_DIR=str(directory/'usage'))
        for provider in ('deepseek','bailian'):
            command=[sys.executable,'scripts/live_providers.py','--provider',provider,'--profile','v35','--out',str(directory/provider)]
            result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            state=json.loads(result.stdout.splitlines()[0])
            self.assertEqual(state['usage_policy'],'unlimited_usage_only')
            self.assertIsNone(state['local_request_limit']);self.assertEqual(state['model_requests_this_command'],0)
        self.assertFalse((directory/'usage').exists())
