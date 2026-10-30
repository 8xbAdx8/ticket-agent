"""Scroll architecture: token contract, run summary binding, layout widgets."""
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from web import scroll_bridge, run_view


def event(kind, status="recorded", **fields):
    return {"event_type": kind, "status": status, **fields}


class ScrollTokenTests(unittest.TestCase):
    def test_token_is_stable_until_an_explicit_request(self):
        self.assertEqual(scroll_bridge.scroll_token(3, "none"), scroll_bridge.scroll_token(3, "none"))
        self.assertNotEqual(scroll_bridge.scroll_token(3, "none"), scroll_bridge.scroll_token(4, "none"))
        self.assertNotEqual(scroll_bridge.scroll_token(3, "bottom"), scroll_bridge.scroll_token(3, "run", "turn_2"))

    def test_unknown_action_degrades_to_none_instead_of_scrolling(self):
        self.assertEqual(scroll_bridge.scroll_token(1, "sideways"), "1:none:")
        with self.assertRaises(ValueError):
            scroll_bridge.request("sideways")

    def test_request_records_action_and_anchor(self):
        state = {}
        with patch.dict("streamlit.session_state", state, clear=True):
            scroll_bridge.request("run", "turn_4")
            pending = scroll_bridge.current_request()
        self.assertEqual(pending["action"], "run")
        self.assertEqual(pending["anchor"], "turn_4")
        self.assertEqual(pending["nonce"], 1)

    def test_bottom_request_drops_the_anchor(self):
        state = {}
        with patch.dict("streamlit.session_state", state, clear=True):
            scroll_bridge.request("run", "turn_1")
            scroll_bridge.request("bottom")
            pending = scroll_bridge.current_request()
        self.assertEqual((pending["action"], pending["anchor"]), ("bottom", ""))

    def test_bridge_html_targets_the_container_not_the_page(self):
        html = scroll_bridge.bridge_html("user_chat_scroll", "7:bottom:", "bottom", "", 7, 560, 3)
        self.assertIn('"chatKey": "user_chat_scroll"', html)
        self.assertIn("'.st-key-' + CFG.chatKey", html)
        self.assertIn('"turns": 3', html)
        self.assertIn('"token": "7:bottom:"', html)
        # The page itself must never be scrolled by the bridge.
        self.assertNotIn("window.scrollTo", html)
        self.assertNotIn("document.body.scrollTop", html)
        # Parsing the embedded config keeps the contract honest.
        marker = html.split("var CFG = ", 1)[1].split(";", 1)[0]
        self.assertEqual(json.loads(marker)["action"], "bottom")


class RunSummaryTests(unittest.TestCase):
    def audit(self, run_id):
        return {"trace_id": run_id, "public_trace": {"user_msg": "x"}}

    def test_no_events_reports_unknown_instead_of_success(self):
        summary = run_view.run_summary(None, None, [], "离线 Mock")
        self.assertEqual(summary["status"], "未记录")
        self.assertIsNone(summary["run_id"])
        self.assertIsNone(summary["last_call"])
        self.assertIn("未记录", run_view.run_summary_line(summary))

    def test_run_id_comes_from_the_selected_audit_only(self):
        summary = run_view.run_summary(None, self.audit("run-selected"), [], "离线 Mock")
        self.assertEqual(summary["run_id"], "run-selected")

    def test_completed_run_summarises_phase_and_last_call(self):
        summary = run_view.run_summary(None, self.audit("r1"), [
            event("tool_result", "succeeded", tool="query_tickets", duration_ms=6),
            event("agent_returned", finish_reason="stop"),
        ], "离线 Mock")
        self.assertEqual(summary["status"], "已完成")
        self.assertEqual(summary["phase_label"], "完成")
        self.assertEqual(summary["last_call"]["label"], "查询余票")
        self.assertIn("查询余票", run_view.run_summary_line(summary))

    def test_failed_tool_reports_failure(self):
        summary = run_view.run_summary(None, self.audit("r2"), [
            event("tool_result", "failed", tool="pay_order", duration_ms=3),
            event("agent_returned", finish_reason="stop"),
        ], "离线 Mock")
        self.assertEqual(summary["status"], "失败")

    def test_waiting_confirmation_is_its_own_state(self):
        summary = run_view.run_summary(None, self.audit("r3"), [
            event("confirmation_requested", tool="create_order", args={}),
        ], "离线 Mock")
        self.assertEqual(summary["status"], "等待确认")
        self.assertEqual(summary["phase_key"], "confirm")


ENV = {"TICKET_WEB_OFFLINE_ONLY": "1", "TICKET_DISABLE_LOCAL_SECRETS": "1",
       "DEEPSEEK_API_KEY": "", "DASHSCOPE_API_KEY": "",
       "LANGCHAIN_TRACING_V2": "false", "LANGSMITH_TRACING": "false"}


class ScrollLayoutUITests(unittest.TestCase):
    def test_summary_shows_the_selected_session_run_and_never_the_other(self):
        with patch.dict(os.environ, ENV), patch.multiple(config, PROVIDER="mock", ENGINE="legacy",
                                                         LC_TOOLSET="all", USE_HTTP_MOCK=False,
                                                         USE_VECTOR_RAG=False):
            from streamlit.testing.v1 import AppTest
            from web.runtime import Conversation
            first = Conversation("user", engine="legacy", live=False)
            first.history = [{"user_msg": "旧会话问题", "reply": "旧回答", "tool_sequence": [],
                              "finish_reason": "stop", "total_latency_ms": 0, "steps": []}]
            first.results = [[]]
            first.audits = [{"trace_id": "run-old-session-aaaa", "public_trace": first.history[0]}]
            second = Conversation("user", engine="legacy", live=False)
            second.history = [{"user_msg": "新会话问题", "reply": "新回答", "tool_sequence": [],
                               "finish_reason": "stop", "total_latency_ms": 0, "steps": []}]
            second.results = [[]]
            second.audits = [{"trace_id": "run-new-session-bbbb", "public_trace": second.history[0]}]
            script = ("import streamlit as st\nfrom web.conversation import user_page\n"
                      "st.session_state['default_engine'] = 'legacy'\n"
                      "st.session_state['default_live'] = False\n"
                      "st.session_state['default_provider'] = 'deepseek'\n"
                      "st.session_state['default_live_model'] = None\n"
                      "st.session_state['user_provider_signature'] = ('legacy', False, 'deepseek', None, 'manual-live-v1')\n"
                      "user_page()")
            app = AppTest.from_string(script)
            app.session_state["user_sessions"] = [first, second]
            app.run(timeout=30)
            self.assertEqual([e.message for e in app.exception], [])
            markup = "\n".join(m.value for m in app.markdown)
            self.assertIn("run-old-sessi", markup)
            self.assertNotIn("run-new-sessi", markup)
            next(s for s in app.selectbox if s.label == "历史会话").select(1).run(timeout=30)
            markup = "\n".join(m.value for m in app.markdown)
            self.assertIn("run-new-sessi", markup)
            self.assertNotIn("run-old-sessi", markup)

    def test_jump_buttons_exist_and_are_disabled_without_history(self):
        with patch.dict(os.environ, ENV), patch.multiple(config, PROVIDER="mock", ENGINE="legacy",
                                                         LC_TOOLSET="all", USE_HTTP_MOCK=False,
                                                         USE_VECTOR_RAG=False):
            from streamlit.testing.v1 import AppTest
            script = ("from web.conversation import user_page\n"
                      "import streamlit as st\n"
                      "st.session_state['default_engine']='legacy'\n"
                      "st.session_state['default_live']=False\n"
                      "st.session_state['default_provider']='deepseek'\n"
                      "st.session_state['default_live_model']=None\n"
                      "user_page()")
            app = AppTest.from_string(script)
            app.run(timeout=30)
            self.assertEqual([e.message for e in app.exception], [])
            labels = [b.label for b in app.button]
            self.assertIn("回到本次运行", labels)
            self.assertIn("回到最新", labels)
            self.assertTrue(next(b for b in app.button if b.label == "回到本次运行").disabled)
            self.assertTrue(next(b for b in app.button if b.label == "回到最新").disabled)


if __name__ == "__main__":
    unittest.main()
