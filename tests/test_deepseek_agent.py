# Original V3.2 Streamlit-specific assertions retained against legacy_app.py.
# V3.3 default entry has separate test_v33_app.py coverage.
"""真实 ChatDeepSeek SDK + httpx 桩的离线验证；不是真实 API 成绩。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch
import config
from data.seed import build_db
from target.agent import Agent
from target import providers

try:
    import httpx
    from target.deepseek_runtime import Settings,RequestBudget,DeepSeekError,make_model
    from langchain_deepseek import ChatDeepSeek
    from langchain_core.messages import AIMessage
    AVAILABLE = True
except ModuleNotFoundError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE,"DeepSeek SDK 仅安装于独立 .venv-deepseek 环境")
class DeepSeekAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.config = patch.multiple(config,PROVIDER="deepseek",ENGINE="langchain",API_KEY="offline-only-sdk-key",
            MODEL_NAME="deepseek-flash",BASE_URL="https://api.deepseek.com",LC_TOOLSET="read_only",USE_HTTP_MOCK=False,
            USE_VECTOR_RAG=False,MAX_STEPS=3,DB_PATH=self.folder/"tickets.db",TRACE_DIR=self.folder/"traces")
        self.env = patch.dict(os.environ,{"DEEPSEEK_BUDGET_PATH":str(self.folder/"budget.db"),"DEEPSEEK_MAX_REQUESTS":"5",
                                         "DEEPSEEK_THINKING":"disabled","DEEPSEEK_API_KEY":"offline-only-sdk-key"})
        self.config.start(); self.env.start()
        providers.clear_mutations()
        build_db()
        self.payloads = []
        self.models = []

    def tearDown(self):
        for model in self.models:
            model.root_client.close()
        self.env.stop(); self.config.stop()
        self.tmp.cleanup()

    def response(self, message, usage=True):
        body = {"id":"offline-sdk-response","object":"chat.completion","created":1,"model":"deepseek-flash",
            "choices":[{"index":0,"message":{"role":"assistant",**message},
                        "finish_reason":"tool_calls" if message.get("tool_calls") else "stop"}]}
        if usage:
            body["usage"] = {"prompt_tokens":13,"completion_tokens":5,"total_tokens":18}
        return body

    def agent(self, responses):
        def respond(request):
            self.payloads.append(json.loads(request.content))
            result = responses[min(len(self.payloads)-1,len(responses)-1)]
            if isinstance(result,Exception):
                raise result
            if isinstance(result,tuple):
                return httpx.Response(result[0],json=result[1])
            return httpx.Response(200,json=result)
        model = make_model(Settings.from_env(),transport=httpx.MockTransport(respond))
        self.models.append(model)
        return Agent(model=model)

    def call(self,name,args,identity="server-tool-1"):
        return {"id":identity,"type":"function","function":{"name":name,"arguments":json.dumps(args,ensure_ascii=False)}}

    def test_real_sdk_tool_call_feedback_usage_and_contract(self):
        args = {"from_city":"上海","to_city":"杭州","date":(config.today()+timedelta(days=1)).isoformat(),"seat_type":"二等座","kind":"高铁"}
        agent = self.agent([self.response({"content":None,"tool_calls":[self.call("query_tickets",args)]}),
                            self.response({"content":"离线 SDK 桩已收到工具库存。"})])
        with patch.object(Agent,"_chat",side_effect=AssertionError("不能走 Mock/原生循环")):
            result = agent.chat("sdk-query","查询高铁")
        self.assertEqual(result["provider"],"deepseek_live")
        self.assertEqual(set(result),{"session_id","provider","model","user_msg","steps","tool_sequence","reply","finish_reason","tokens","total_latency_ms"})
        self.assertEqual(result["tool_sequence"],["query_tickets"])
        self.assertEqual(result["tokens"],{"prompt":26,"completion":10})
        self.assertEqual({t["function"]["name"] for t in self.payloads[0]["tools"]},{"query_tickets","search_policy"})
        tool = next(m for m in self.payloads[1]["messages"] if m["role"]=="tool")
        self.assertEqual(tool["tool_call_id"],"server-tool-1")
        self.assertGreater(json.loads(tool["content"])["count"],0)
        self.assertEqual(self.payloads[0]["thinking"],{"type":"disabled"})
        events = agent.langchain_engine.last_events
        self.assertEqual(next(e for e in events if e["event"]=="model_response")["tool_calls"][0]["id"],"server-tool-1")

    def test_policy_sources_and_multiturn_context_are_returned_to_sdk(self):
        agent = self.agent([self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":"锁座后多久必须支付"})]}),
                            self.response({"content":"锁座 15 分钟，请参考 P11。"}),self.response({"content":"离线桩继续对话。"})])
        r = agent.chat("same","锁座政策")
        self.assertEqual(r["tool_sequence"],["search_policy"])
        tool = next(m for m in self.payloads[1]["messages"] if m["role"]=="tool")
        self.assertTrue(any(h["doc_id"]=="P11" for h in json.loads(tool["content"])["hits"]))
        agent.chat("same","继续上个问题")
        self.assertTrue(any(m.get("content")=="锁座政策" for m in self.payloads[2]["messages"]))

    def test_live_write_expansion_is_rejected_and_model_cannot_pay(self):
        with patch.object(config,"LC_TOOLSET","all"):
            with self.assertRaisesRegex(DeepSeekError,"read_only_tools_required"):
                Agent()
        agent = self.agent([self.response({"content":None,"tool_calls":[self.call("pay_order",{"order_id":"imagined"})]}),
                            self.response({"content":"当前只读，未执行付款。"})])
        with patch("target.mock_core.pay_order",side_effect=AssertionError("不得付款")):
            with self.assertRaisesRegex(DeepSeekError,"tool_execution_failed"):
                agent.chat("security","只查票")
        failed = json.loads((config.TRACE_DIR/"deepseek_runs.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(failed["tool_sequence"],["pay_order"])
        self.assertFalse(failed["tool_attempts"][0]["calls"][0]["ok"])

    def test_missing_usage_raises_safe_error_without_fake_zero_trace(self):
        agent = self.agent([self.response({"content":"无用量的离线响应"},usage=False)])
        with self.assertRaisesRegex(DeepSeekError,"token_usage_unknown"):
            agent.chat("unknown","查询")
        self.assertFalse((config.TRACE_DIR/"traces.jsonl").exists())
        error = json.loads((config.TRACE_DIR/"deepseek_runs.jsonl").read_text(encoding="utf-8"))
        self.assertIsNone(error["tokens"])
        self.assertEqual(error["error"]["category"],"token_usage_unknown")

    def test_http_error_is_not_retried_and_never_leaks_secret_or_body(self):
        agent = self.agent([(401,{"error":{"message":"offline-only-sdk-key hidden-internal-reasoning"}})])
        with self.assertRaisesRegex(DeepSeekError,"authentication_failed"):
            agent.chat("error","查询")
        self.assertEqual(len(self.payloads),1)
        output = (config.TRACE_DIR/"deepseek_runs.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("offline-only-sdk-key",output)
        self.assertNotIn("hidden-internal-reasoning",output)

    def test_reasoning_is_not_logged_and_thinking_replay_is_unsupported(self):
        agent = self.agent([self.response({"content":"仅最终回复","reasoning_content":"offline-private-reasoning-marker"})])
        r = agent.chat("privacy","你好")
        output = (config.TRACE_DIR/"deepseek_runs.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("offline-private-reasoning-marker",output)
        self.assertNotIn("reasoning_content",output)
        message = AIMessage(content="",tool_calls=[{"id":"x","name":"query_tickets","args":{},"type":"tool_call"}],
                            additional_kwargs={"reasoning_content":"offline-protocol-only"})
        payload = agent.provider._get_request_payload([message])
        # 记录真实兼容性限制，不对思考协议伪造内容进行修补。
        self.assertNotIn("reasoning_content",payload["messages"][0])
        self.assertEqual(r["reply"],"仅最终回复")

    def test_tool_call_count_limit_and_max_model_steps(self):
        calls = [self.call("search_policy",{"question":"支付规则"},str(i)) for i in range(3)]
        agent = self.agent([self.response({"content":None,"tool_calls":calls}),self.response({"content":"离线桩结束"})])
        agent.langchain_engine.deepseek_settings = replace(agent.langchain_engine.deepseek_settings,max_tool_calls=1)
        with self.assertRaisesRegex(DeepSeekError,"tool_execution_failed"):
            agent.chat("limit","政策")
        failed = json.loads((config.TRACE_DIR/"deepseek_runs.jsonl").read_text(encoding="utf-8"))
        self.assertEqual([c["ok"] for s in failed["tool_attempts"] for c in s["calls"]],[True,False,False])
        agent.reset("limit")
        with patch.object(config,"MAX_STEPS",1):
            # 重复使用纯离线响应；没有新增真实 API 请求。
            other = self.agent([self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":"支付规则"})]})])
            r = other.chat("steps","政策")
        self.assertEqual(r["finish_reason"],"max_steps_exceeded")

    def test_tool_exception_is_returned_to_sdk_as_failure(self):
        agent = self.agent([self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":"支付规则"})]}),
                            self.response({"content":"[离线桩] 工具失败，无法确认政策。"})])
        with patch("target.tools.dispatch",side_effect=RuntimeError("private-key-or-path")):
            with self.assertRaisesRegex(DeepSeekError,"tool_execution_failed"):
                agent.chat("fault","支付规则")
        failed = json.loads((config.TRACE_DIR/"deepseek_runs.jsonl").read_text(encoding="utf-8"))
        self.assertFalse(failed["tool_attempts"][0]["calls"][0]["ok"])
        feedback = next(m for m in self.payloads[1]["messages"] if m["role"]=="tool")
        self.assertIn("error",json.loads(feedback["content"]))
        self.assertNotIn("private-key-or-path",json.dumps(failed))

    def test_streamlit_shows_deepseek_source_and_real_sdk_tool_result(self):
        from streamlit.testing.v1 import AppTest
        agent = self.agent([self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":"锁座支付有效期"})]}),
                            self.response({"content":"[离线SDK桩] 15 分钟，来源 P11。"})])
        with patch("target.agent.Agent",return_value=agent):
            app = AppTest.from_file(str(config.BASE_DIR/"web/legacy_app.py"),default_timeout=30).run()
            app.text_input[0].set_value("锁座后多久支付？")
            next(b for b in app.button if b.label=="发送").click().run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(all(not c.disabled for c in app.checkbox))  # V3.1显式注入现已接入真实执行器。
        self.assertEqual(app.session_state["history"][-1]["provider"],"deepseek_live")
        self.assertTrue(any("DeepSeek Live" in m.value for m in app.markdown))
        self.assertTrue(any("API 报告 Token" in c.value for c in app.caption))
        self.assertTrue(any('class="policy-card"' in m.value and "P11" in m.value for m in app.markdown))

    def test_streamlit_missing_key_is_clear_and_does_not_fall_back(self):
        from streamlit.testing.v1 import AppTest
        with patch.object(config,"API_KEY",""):
            app = AppTest.from_file(str(config.BASE_DIR/"web/legacy_app.py"),default_timeout=30).run()
        self.assertEqual(len(app.exception),0)
        self.assertTrue(next(b for b in app.button if b.label=="发送").disabled)
        self.assertTrue(any("missing_DEEPSEEK_API_KEY" in c.value for c in app.caption))
        self.assertFalse((config.TRACE_DIR/"traces.jsonl").exists())


if __name__=="__main__":
    unittest.main()
