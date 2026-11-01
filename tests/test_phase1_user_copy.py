"""阶段1离线验收：来源、费用告知、诊断分层及只读切页，不发送真实请求。"""
import hashlib
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import config
from streamlit.testing.v1 import AppTest


class Phase1UserCopyTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'TICKET_DISABLE_LOCAL_SECRETS': '1', 'TICKET_WEB_OFFLINE_ONLY': '1',
            'DEEPSEEK_API_KEY': '', 'DASHSCOPE_API_KEY': '',
            'LANGCHAIN_TRACING_V2': 'false', 'LANGSMITH_TRACING': 'false',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.cfg = patch.multiple(config, PROVIDER='mock', ENGINE='legacy',
                                  LC_TOOLSET='all', USE_HTTP_MOCK=False, USE_VECTOR_RAG=False)
        self.cfg.start()
        self.addCleanup(self.cfg.stop)

    def app(self):
        app = AppTest.from_file(str(config.BASE_DIR / 'web/app.py'), default_timeout=30).run()
        self.assertFalse(app.exception)
        return app

    def text(self, app):
        return '\n'.join(str(e.value) for group in (app.markdown, app.caption, app.info, app.warning, app.error)
                         for e in group)

    def send(self, app, text):
        app.text_input(key='user_message').set_value(text)
        next(b for b in app.button if b.label == '发送').click().run()
        self.assertFalse(app.exception)

    def test_navigation_keeps_internal_routes_and_never_dispatches_on_render(self):
        with patch('web.runtime.Agent') as constructor:
            app = self.app()
            sid = app.session_state['user_sessions'][0].sid
            self.assertIn('用户工作空间', app.radio(key='workspace_mode').options)
            self.assertIn('开发者工作空间', app.radio(key='workspace_mode').options)
            self.assertIn('测试控制台', app.radio(key='workspace_mode').options)
            for route in ('开发者工作台', '测试工作台', '出行助手'):
                app.radio(key='workspace_mode').set_value(route).run()
                self.assertFalse(app.exception)
            self.assertEqual(sid, app.session_state['user_sessions'][0].sid)
            self.assertEqual('Legacy Mock', app.selectbox(key='provider_selection').value)
            constructor.assert_not_called()

    def test_ticket_and_policy_sources_without_raw_json_then_developer_can_read(self):
        app = self.app()
        self.assertIn('不提供真实出票服务', self.text(app))
        self.send(app, '查明天上海到杭州的高铁二等座')
        self.assertIn('演示数据', self.text(app))
        self.assertEqual(0, len(app.json))
        self.send(app, '锁座后多久必须完成支付？')
        self.assertIn('项目内示例政策', self.text(app))
        self.assertIn('不等于回答已被验证', self.text(app))
        self.assertEqual(0, len(app.json))
        session = app.session_state['user_sessions'][0]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in session.trace_dir.iterdir() if p.is_file()}
        history = list(session.history)
        app.button(key='user_to_trace_' + session.sid).click().run()
        self.assertFalse(app.exception)
        self.assertEqual('开发者工作台', app.radio(key='workspace_mode').value)
        self.assertTrue(any('rag_runs' not in e.value and 'run_id' in e.value for e in app.json))
        self.assertEqual(history, session.history)
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before})

    def test_confirmation_shows_exact_values_without_executing_on_render(self):
        session = SimpleNamespace(live=False, sid='phase1-confirm', history=[], results=[], audits=[],
                                  confirm_action=Mock())
        script = """import streamlit as st
from web.conversation import _confirm_cards
_confirm_cards(st.session_state['fixture'], {'tool':'lock_seat','args':{
    'train_no':'G7301','date':'2026-11-02','seat_type':'二等座','passengers':['张三']}}, None, False)
"""
        app = AppTest.from_string(script)
        app.session_state['fixture'] = session
        app.run()
        self.assertFalse(app.exception)
        visible = self.text(app)
        for value in ('G7301', '2026-11-02', '二等座', '张三', '不会真实出票或扣款'):
            self.assertIn(value, visible)
        self.assertEqual(0, len(app.json))
        session.confirm_action.assert_not_called()
        self.assertIn('确认此模拟操作', [b.label for b in app.button])

    def test_live_fee_copy_does_not_add_or_remove_authorization(self):
        for provider in ('DeepSeek', 'Qwen3.8-Flash'):
            with self.subTest(provider=provider):
                script = """import streamlit as st
from web.conversation import _composer
from types import SimpleNamespace
st.session_state['user_submit_nonce']='stable'
st.session_state['allowed']=_composer(SimpleNamespace(live=True, read_only=False,
    live_provider='bailian'), st.session_state['provider_name'])[2]
"""
                app = AppTest.from_string(script)
                app.session_state['provider_name'] = provider
                with patch('web.conversation.live_ready', return_value=True):
                    app.run()
                self.assertFalse(app.exception)
                text = self.text(app)
                for expected in (provider, '主问题', '额外使用一次', '点击追问按新消息计费', '不会真实扣款'):
                    self.assertIn(expected, text)
                self.assertTrue(app.session_state['allowed'])  # 原实现不增加额外费用checkbox。
                self.assertNotIn('user_allow_live', [c.key for c in app.checkbox])
                self.assertEqual('发送', app.button(key='user_send_stable').label)

    def test_failure_is_not_success_and_diagnostics_are_not_echoed(self):
        from web.user_copy import error_message, processing_markup
        self.assertIn('结果可能尚未确认', error_message('timeout'))
        self.assertIn('未完成', error_message('unknown_sensitive_detail'))
        self.assertNotIn('unknown_sensitive_detail', error_message('unknown_sensitive_detail'))
        message = processing_markup({'event_type': 'tool_result', 'status': 'blocked',
                                     'tool': 'pay_order', 'error': 'private_stack'})
        self.assertIn('遇到问题', message)
        self.assertNotIn('private_stack', message)

    def test_cards_keep_demo_and_payment_boundaries(self):
        from web.presentation import ticket_cards, order_card, policy_cards
        self.assertIn('不真实出票', ticket_cards({'trains': [{'train_no': 'G1'}]}))
        paid = order_card({'order_id': 'OD1', 'status': 'paid', 'duplicate_pay': True})
        self.assertIn('演示订单', paid)
        self.assertIn('不会真实出票、扣款或退款', paid)
        self.assertIn('示例政策', policy_cards({'hits': [{'doc_id': 'P01', 'content': '示例条款'}]}))
