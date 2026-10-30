"""Selector/preflight behavior is offline. No --run invocation in regression."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import config
from streamlit.testing.v1 import AppTest


class LiveProviderUITests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{"DASHSCOPE_API_KEY":"","DEEPSEEK_API_KEY":"","LANGCHAIN_TRACING_V2":"false",
            "LANGSMITH_TRACING":"false","LANGCHAIN_API_KEY":"","LANGSMITH_API_KEY":"","TICKET_WEB_OFFLINE_ONLY":"1"})
        self.cfg=patch.multiple(config,PROVIDER="mock",ENGINE="legacy",USE_HTTP_MOCK=False,USE_VECTOR_RAG=False)
        self.env.start();self.cfg.start()
        self.app=AppTest.from_file(str(config.BASE_DIR/"web/app.py"),default_timeout=30).run()

    def tearDown(self):
        for key in ("user_sessions","lab_archives"):
            try: sessions=self.app.session_state[key]
            except KeyError: sessions=[]
            for session in sessions:
                self.assertTrue(session.root.resolve().is_relative_to((config.BASE_DIR/"artifacts/runtime").resolve()))
                shutil.rmtree(session.root,ignore_errors=True)
        self.cfg.stop();self.env.stop()

    def select(self,label):
        next(s for s in self.app.selectbox if s.label=="新会话模型").select(label).run()
        self.assertEqual([e.message for e in self.app.exception],[])
        return self.app.session_state["user_sessions"][self.app.session_state["user_session_index"]]

    def nav(self,label):
        next(r for r in self.app.radio if r.label=="工作空间").set_value("测试工作台").run()
        next(r for r in self.app.radio if r.label=="工作台导航").set_value(label).run()

    def test_all_four_models_select_without_initializing_or_network(self):
        from web import runtime
        with patch.object(runtime,"Agent") as agent:
            for label in ("Legacy Mock","LangChain Mock","DeepSeek Live","Qwen3.8-Flash Live"):
                session=self.select(label)
                self.assertIsNone(session.agent)
                self.assertFalse(session.root.exists())
            agent.assert_not_called()

    def test_live_providers_have_distinct_memory_and_database_paths(self):
        a=self.select("DeepSeek Live"); b=self.select("Qwen3.8-Flash Live")
        self.assertNotEqual(a.sid,b.sid);self.assertNotEqual(a.root,b.root)
        self.assertEqual((a.live_provider,b.live_provider),("deepseek","bailian"))
        self.assertFalse(any(a.history+b.history))

    def test_missing_key_blocks_send_no_fallback_and_no_secret_ui_field(self):
        self.select("Qwen3.8-Flash Live")
        self.assertTrue(next(b for b in self.app.button if b.label=="发送").disabled)
        self.assertTrue(any("不会自动切换 Mock" in i.value for i in self.app.info))
        self.assertFalse(any("key" in i.label.lower() for i in self.app.text_input))

    def test_integration_states_do_not_claim_remote_verification(self):
        self.nav("集成中心")
        self.assertEqual([e.message for e in self.app.exception],[])
        text="\n".join(x.value for x in self.app.markdown)+str([x.value for x in self.app.caption])
        self.assertIn("显式确认",text)
        self.assertIn("未配置",text)

    def test_both_live_modes_available_in_lab_and_rerun_never_calls_agent(self):
        self.nav("测试实验室")
        selector=next(s for s in self.app.selectbox if s.label=="执行模式")
        self.assertIn("Qwen3.8-Flash Live · 模拟票务",selector.options)
        from web import runtime
        with patch.object(runtime,"Agent") as agent:
            selector.select("Qwen3.8-Flash Live · 模拟票务").run()
            self.app.run()
            agent.assert_not_called()
        self.assertEqual([e.message for e in self.app.exception],[])
        self.assertTrue(next(b for b in self.app.button if b.label=="执行测试").disabled)


class ProviderCommandTests(unittest.TestCase):
    def test_offline_dashboard_excludes_both_live_providers(self):
        from web.evidence import audit_batch
        entries=[{"kind":"当前工作空间","record":{"provider":p,"trace_id":p,"judgement":{"test_verdict":"pass"}}}
                 for p in ("legacy_mock","langchain_mock","deepseek_live","bailian_live")]
        with patch("web.evidence.audit_catalog",return_value=entries):
            report=audit_batch()
        self.assertEqual([r["id"] for r in report["rows"]],["legacy_mock","langchain_mock"])

    def test_cli_preflight_missing_and_fake_key_is_offline(self):
        root=config.BASE_DIR/"artifacts/runtime"
        root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root,prefix="providers-command-") as tmp:
            for value,expected in (("",2),("offline-preflight-fixture",0)):
                env=dict(os.environ,DASHSCOPE_API_KEY=value,DASHSCOPE_MODEL="qwen-plus",
                    DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    LANGCHAIN_TRACING_V2="false",LANGSMITH_TRACING="false",LANGCHAIN_API_KEY="",LANGSMITH_API_KEY="")
                result=subprocess.run([sys.executable,"scripts/live_providers.py","--provider","bailian","--out",tmp],cwd=config.BASE_DIR,
                    env=env,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=20)
                self.assertIsNotNone(result.stdout,'子进程输出无法按 UTF-8 解码；stderr='+repr(result.stderr))
                self.assertEqual(result.returncode,expected,result.stdout)
                self.assertNotIn("offline-preflight-fixture",result.stdout+result.stderr)
                self.assertFalse((Path(tmp)/"tickets.db").exists())
                self.assertFalse((Path(tmp)/"report.json").exists())
                body=json.loads(result.stdout.splitlines()[-1])
                self.assertEqual(body.get("model_requests_this_command",body.get("new_generation_requests")),0)
