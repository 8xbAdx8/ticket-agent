"""Same-session policy follow-ups and real offline RAG evidence, never Live calls."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import config
from streamlit.testing.v1 import AppTest
from web.runtime import Conversation
from web.conversation import _turn_policy, _consume_followup, _policy_panel
from web.policy_interaction import followup_questions


ENV = {'TICKET_WEB_OFFLINE_ONLY': '1', 'TICKET_DISABLE_LOCAL_SECRETS': '1',
       'DEEPSEEK_API_KEY': '', 'DASHSCOPE_API_KEY': '', 'LANGCHAIN_API_KEY': '',
       'LANGSMITH_API_KEY': '', 'LANGCHAIN_TRACING_V2': 'false', 'LANGSMITH_TRACING': 'false',
       'TICKET_FROZEN_RAG_EVIDENCE': '', 'AGENT_RAG_MODE': ''}
SCRIPT = """import streamlit as st
from web.conversation import user_page
st.session_state['default_engine']='legacy'
st.session_state['default_live']=False
st.session_state['default_provider']='deepseek'
st.session_state['default_live_model']=None
user_page()
"""


class PolicyChatIntegrationTests(unittest.TestCase):
    def setUp(self):
        for guard in (patch.dict(os.environ, ENV),
                      patch.multiple(config, PROVIDER='mock', ENGINE='legacy', MAX_STEPS=8,
                                     USE_HTTP_MOCK=False, USE_VECTOR_RAG=False,
                                     POLICY_PATH=Path(__file__).resolve().parents[1]/'data/policies.md')):
            guard.start()
            self.addCleanup(guard.stop)

    def test_regression_snapshot_includes_current_theme_styles(self):
        from scripts.regression_center import source_files
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'web').mkdir()
            stylesheet = root/'web/design.css'
            stylesheet.write_text('.ta-policy-state { color: currentColor; }', encoding='utf8')
            self.assertEqual(stylesheet, source_files(root)['web/design.css'])

    def test_click_submits_once_on_same_session_without_forced_scroll_or_extra_call(self):
        app = AppTest.from_string(SCRIPT, default_timeout=30).run()
        app.text_input(key='user_message').set_value('锁座后多久必须完成支付？')
        next(b for b in app.button if b.label == '发送').click().run()
        self.assertEqual([], list(app.exception))
        session = app.session_state['user_sessions'][0]
        sid, root, agent = session.sid, session.root, session.agent
        before = copy.deepcopy(session.history)
        view = _turn_policy(session, before[0])
        self.assertEqual('retrieved', view['status'])
        actual = [h['doc_id'] for result in session.results[0] if result['tool'] == 'search_policy'
                  for h in result['result']['hits']]
        self.assertEqual(actual, [h['doc_id'] for h in view['evidence']])
        self.assertTrue(any(h['entered_context'] is True for h in view['evidence']))
        self.assertTrue(all(h['support_status'] == '尚未验证' for h in view['evidence']))
        buttons = [b for b in app.button if (b.key or '').startswith('policy_followup_')]
        self.assertIn(len(buttons), (2, 3))
        question = buttons[0].label
        nonce = app.session_state['scroll_nonce']
        buttons[0].click().run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(1, len(app.session_state['user_sessions']))
        self.assertEqual((sid, root, agent), (session.sid, session.root, session.agent))
        self.assertEqual(2, len(session.history))
        self.assertEqual(question, session.history[-1]['user_msg'])
        self.assertEqual(['search_policy'], session.history[-1]['tool_sequence'])
        self.assertEqual(before, session.history[:1])
        self.assertEqual(nonce, app.session_state['scroll_nonce'])
        self.assertNotEqual(view['run_id'], _turn_policy(session, session.history[-1])['run_id'])
        labels = [b.label for b in app.button if (b.key or '').startswith('policy_followup_')]
        self.assertEqual(len(labels), len(set(labels)))
        app.run()  # Opening/re-rendering evidence is not another submission.
        self.assertEqual(2, len(session.history))

    def test_policy_evidence_uses_trace_identity_even_after_failed_run(self):
        session = Conversation('user')
        first = session.send('锁座后多久必须完成支付？', 'first')
        original = _turn_policy(session, first)
        session.audits.append({'trace_id': 'failed-later', 'public_trace': {'session_id': session.sid}})
        self.assertEqual(original, _turn_policy(session, first))
        other = Conversation('user')
        self.assertEqual('not_searched', _turn_policy(other, first)['status'])
        self.assertEqual([], _turn_policy(other, first)['evidence'])

    def test_retrieval_without_subsequent_model_request_stays_context_unknown(self):
        with patch.object(config, 'MAX_STEPS', 1):
            session = Conversation('user')
            record = session.send('锁座后多久必须完成支付？', 'one-step')
        view = _turn_policy(session, record)
        self.assertEqual('max_steps_exceeded', record['finish_reason'])
        self.assertTrue(view['evidence'])
        self.assertTrue(all(h['entered_context'] is None for h in view['evidence']))

    def test_mock_does_not_inherit_live_embedding_network_settings(self):
        with patch.dict(os.environ, {'AGENT_RAG_MODE': 'hybrid', 'RAG_ALLOW_NETWORK': '1'}), \
             patch('target.rag_service.configured_index', side_effect=AssertionError('must remain offline')):
            session = Conversation('user')
            record = session.send('锁座后多久必须完成支付？', 'offline')
            self.assertEqual(['search_policy'], record['tool_sequence'])
            self.assertEqual('retrieved', _turn_policy(session, record)['status'])
            self.assertEqual('hybrid', os.environ['AGENT_RAG_MODE'])
            self.assertEqual('1', os.environ['RAG_ALLOW_NETWORK'])

    def test_langchain_mock_records_actual_policy_message_context(self):
        session = Conversation('user', engine='langchain')
        record = session.send('锁座后多久必须完成支付？', 'lc-policy')
        view = _turn_policy(session, record)
        self.assertEqual(['search_policy'], record['tool_sequence'])
        self.assertEqual('retrieved', view['status'])
        self.assertTrue(any(h['entered_context'] is True for h in view['evidence']))

    def test_old_trace_without_sidecars_does_not_claim_retrieval_did_not_happen(self):
        session = Conversation('user')
        view = _turn_policy(session, {'session_id': session.sid, 'tool_sequence': ['search_policy']})
        self.assertEqual('检索状态未记录', view['status_label'])
        self.assertEqual([], view['evidence'])

    def test_stale_or_unconsented_followup_never_submits(self):
        session = Conversation('user')
        record = session.send('锁座后多久必须完成支付？', 'first')
        view = _turn_policy(session, record)
        question = followup_questions(record['user_msg'], record['reply'], view['evidence'])[0]
        request = {'sid': session.sid, 'run_id': view['run_id'], 'question': question, 'request_id': 'next'}
        for overrides, busy in (({'sid': 'another-session'}, False), ({}, True), ({'run_id': 'other'}, False)):
            with patch('web.conversation.st.session_state', {'user_followup_request': {**request, **overrides}}):
                self.assertIsNone(_consume_followup(session, busy))
        session.live = True
        for consent, compose, ready in ((False, session.sid, True), (True, 'old-session', True), (True, session.sid, False)):
            state = {'user_followup_request': request.copy(), 'user_allow_live': consent, 'user_compose_session': compose}
            with patch('web.conversation.st.session_state', state), patch('web.conversation.live_ready', return_value=ready):
                self.assertIsNone(_consume_followup(session, False))
        self.assertEqual(1, len(session.history))

    def test_failed_recent_retrieval_does_not_appear_successful_or_offer_followups(self):
        from web.conversation import _followup_suggestions
        view = {'status': 'failed', 'status_label': '知识库检索失败', 'run_id': 'r',
                'evidence': [{'doc_id': 'P11', 'content': '锁座有效期15分钟', 'score': 0}]}
        script = 'import streamlit as st\nfrom web.conversation import _policy_panel\n_policy_panel(st.session_state["view"])'
        app = AppTest.from_string(script)
        app.session_state['view'] = view
        app.run()
        self.assertEqual([], list(app.exception))
        self.assertIn('检索失败', app.expander[0].label)
        self.assertTrue(list(app.warning))
        captions = '\n'.join(c.value for c in app.caption)
        self.assertIn('版本：未记录', captions)
        self.assertIn('分数：0', captions)
        self.assertIn('支持最终结论：尚未验证', captions)
        with patch('web.conversation.st.button') as button:
            _followup_suggestions(SimpleNamespace(), {}, view)
            button.assert_not_called()

    def test_first_failed_request_without_history_still_displays_real_retrieval_failure(self):
        from target.trace import Trace
        from target.run_events import capture, bind
        from target.rag_service import retrieve
        from web.runtime import scoped
        session = Conversation('user')
        trace = Trace(session.sid, '锁座多久？')
        with scoped({'TRACE_DIR': session.trace_dir}), capture(session.trace_dir/'run_events.jsonl'):
            bind(trace)
            with patch('target.rag_service.configured_index', side_effect=TimeoutError('test timeout')):
                with self.assertRaises(TimeoutError):
                    retrieve('锁座多久？', mode='vector')
        session.error = {'category': 'tool_execution_failed'}
        session.audits = [{'trace_id': trace.trace_id, 'public_trace': {'session_id': session.sid}}]
        app = AppTest.from_string(SCRIPT, default_timeout=30)
        app.session_state['user_sessions'] = [session]
        app.session_state['user_provider_signature'] = ('legacy', False, 'deepseek', None, 'manual-live-v1')
        app.run()
        self.assertEqual([], list(app.exception))
        self.assertTrue(any('知识库检索失败' in m.value for m in app.markdown))
        self.assertFalse(any((b.key or '').startswith('policy_followup_') for b in app.button))
        self.assertEqual([], session.history)


if __name__ == '__main__':
    unittest.main()
