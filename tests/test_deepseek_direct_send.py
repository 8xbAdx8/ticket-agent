"""DeepSeek user UI sends explicitly without fee checkbox; offline only."""
import os
import unittest
from unittest.mock import patch

import config
from streamlit.testing.v1 import AppTest
from web.conversation import _live_request_allowed
from web.runtime import Conversation


class DeepSeekDirectSendTests(unittest.TestCase):
    def setUp(self):
        env={'TICKET_DISABLE_LOCAL_SECRETS':'1','TICKET_WEB_OFFLINE_ONLY':'0',
             'DEEPSEEK_API_KEY':'offline-ui-only','DASHSCOPE_API_KEY':'offline-ui-only',
             'DASHSCOPE_BASE_URL':'https://dashscope.aliyuncs.com/compatible-mode/v1',
             'LANGSMITH_TRACING':'false','LANGCHAIN_TRACING_V2':'false'}
        for guard in (patch.dict(os.environ,env),
                      patch.multiple(config,PROVIDER='deepseek',ENGINE='langchain',MODEL_NAME='deepseek-flash',
                                     BASE_URL='https://api.deepseek.com',API_KEY='offline-ui-only'),
                      patch('web.runtime.Agent')):
            value=guard.start();self.addCleanup(guard.stop)
        self.agent=value
        self.app=AppTest.from_file(str(config.BASE_DIR/'web/app.py'),default_timeout=30).run()

    def session(self):return self.app.session_state['user_sessions'][self.app.session_state['user_session_index']]

    def send_button(self):return next(b for b in self.app.button if b.label=='发送')

    def test_configured_online_default_is_deepseek_and_render_never_calls_agent(self):
        self.assertFalse(self.app.exception)
        self.assertEqual('DeepSeek Live',next(s for s in self.app.selectbox if s.label=='新会话模型').value)
        self.assertTrue(self.session().live)
        self.assertNotIn('user_allow_live',[c.key for c in self.app.checkbox])
        self.assertTrue(any('当前为 DeepSeek 在线模式，发送请求会产生 API 费用。' in c.value for c in self.app.caption))
        self.app.run();self.agent.assert_not_called()

    def test_query_send_dispatches_once_without_checkbox_and_refresh_does_not_repeat(self):
        session=self.session()
        with patch.object(session,'send',return_value={}) as send:
            self.app.text_input(key='user_message').set_value('查明天上海到杭州的高铁二等座')
            self.send_button().click().run()
            self.assertFalse(self.app.exception);send.assert_called_once()
            self.assertEqual('查明天上海到杭州的高铁二等座',send.call_args.args[0])
            self.assertTrue(send.call_args.kwargs['followup_authorized'])
            self.app.run();send.assert_called_once()

    def test_empty_send_does_not_dispatch(self):
        with patch.object(self.session(),'send') as send:
            self.app.text_input(key='user_message').set_value('   ')
            self.send_button().click().run();send.assert_not_called()

    def test_missing_key_still_disables_send(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':''}),patch('web.conversation.live_ready',return_value=False):
            self.app.run()
            self.assertTrue(self.send_button().disabled);self.agent.assert_not_called()

    def test_qwen_still_requires_its_original_checkbox(self):
        next(s for s in self.app.selectbox if s.label=='新会话模型').select('Qwen3.8-Flash Live').run()
        self.assertFalse(self.app.checkbox(key='user_allow_live').value)
        with patch.object(self.session(),'send') as send:
            self.app.text_input(key='user_message').set_value('查票')
            self.send_button().click().run();send.assert_not_called()
            self.app.checkbox(key='user_allow_live').check().run();send.assert_not_called()

    def test_mock_selection_retains_offline_behavior(self):
        next(s for s in self.app.selectbox if s.label=='新会话模型').select('Legacy Mock').run()
        self.assertFalse(self.session().live);self.assertEqual('legacy',self.session().engine)
        self.assertNotIn('user_allow_live',[c.key for c in self.app.checkbox]);self.agent.assert_not_called()

    def test_lab_keeps_explicit_request_confirmation(self):
        next(r for r in self.app.radio if r.label=='工作空间').set_value('测试工作台').run()
        next(r for r in self.app.radio if r.label=='工作台导航').set_value('测试实验室').run()
        select=next(s for s in self.app.selectbox if s.label=='执行模式')
        select.select(next(s for s in select.options if s.startswith('DeepSeek Live'))).run()
        self.assertFalse(self.app.exception)
        self.assertFalse(self.app.checkbox(key='lab_allow_live').value)
        with patch.object(Conversation,'send') as send:
            next(b for b in self.app.button if b.label=='执行测试').click().run()
            send.assert_not_called()

    def test_direct_send_permission_is_session_and_provider_specific(self):
        session=self.session()
        state={'user_compose_session':session.sid,'user_allow_live':False}
        with patch('web.conversation.st.session_state',state):
            self.assertTrue(_live_request_allowed(session))
            session.live_provider='bailian';self.assertFalse(_live_request_allowed(session))
            session.live_provider='deepseek';session.mode='lab';self.assertFalse(_live_request_allowed(session))
            session.mode='user';state['user_compose_session']='old-session'
            self.assertFalse(_live_request_allowed(session))

    def test_business_operation_buttons_still_require_separate_confirmation(self):
        session=self.session()
        script="""import streamlit as st
from web.conversation import _confirm_cards
s=st.session_state['fixture_session']
st.session_state['user_compose_session']=s.sid
_confirm_cards(s,st.session_state['fixture_action'],None,False)
"""
        for tool in ('lock_seat','create_order','pay_order','cancel_order'):
            with self.subTest(tool=tool),patch.object(session,'confirm_action') as confirm:
                app=AppTest.from_string(script,default_timeout=30)
                app.session_state['fixture_session']=session
                app.session_state['fixture_action']={'tool':tool,'args':{'fixture':True}}
                app.run();self.assertFalse(app.exception);confirm.assert_not_called()
                next(b for b in app.button if b.label=='确认此模拟操作').click().run()
                self.assertFalse(app.exception);confirm.assert_called_once()
                self.assertIs(confirm.call_args.args[0],True)


if __name__=='__main__':unittest.main()
