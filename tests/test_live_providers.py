"""Real SDKs with MockTransport only. No paid API traffic, including fake-Key cases."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import config
from target.deepseek_runtime import DeepSeekError, RequestBudget, Settings as DeepSettings
from target import bailian_runtime as bailian
try:
    import httpx
    from langchain_openai import ChatOpenAI
    from target.agent import Agent
    AVAILABLE=True
except ImportError:
    AVAILABLE=False


@unittest.skipUnless(AVAILABLE,"Live SDK compatibility is verified in the full dependency environment")
class LiveProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{"DASHSCOPE_API_KEY":"offline-bailian-fixture-key","DASHSCOPE_MODEL":"qwen-plus",
            "DASHSCOPE_BASE_URL":"https://dashscope.aliyuncs.com/compatible-mode/v1",
            "BAILIAN_BUDGET_PATH":str(self.root/"bailian.db"),"BAILIAN_MAX_REQUESTS":"3",
            "DEEPSEEK_BUDGET_PATH":str(self.root/"deepseek.db"),"DEEPSEEK_MAX_REQUESTS":"3",
            "TICKET_INITIAL_LIVE_BUDGET":"","TICKET_CASE_ID":"offline-fixture","AGENT_MUTATIONS":"{}",
            "LANGCHAIN_TRACING_V2":"false","LANGSMITH_TRACING":"false"})
        self.env.start()
        self.cfg=patch.multiple(config,PROVIDER="bailian",ENGINE="langchain",LC_TOOLSET="read_only",MODEL_NAME="qwen-plus",
            BASE_URL=os.environ["DASHSCOPE_BASE_URL"],API_KEY="offline-bailian-fixture-key",DB_PATH=self.root/"tickets.db",
            TRACE_DIR=self.root/"traces",USE_HTTP_MOCK=False,USE_VECTOR_RAG=False,MAX_STEPS=3)
        self.cfg.start()
        from data.seed import build_db
        with contextlib.redirect_stdout(io.StringIO()): build_db()
        self.models=[]; self.payloads=[]

    def tearDown(self):
        for model in self.models: model.root_client.close()
        self.cfg.stop(); self.env.stop(); self.tmp.cleanup()

    def response(self,message,usage=True):
        body={"id":"offline-sdk","object":"chat.completion","created":1,"model":"qwen-plus-actual-fixture",
              "choices":[{"index":0,"message":{"role":"assistant",**message},"finish_reason":"tool_calls" if message.get("tool_calls") else "stop"}]}
        if usage: body["usage"]={"prompt_tokens":13,"completion_tokens":5,"total_tokens":18}
        return body

    def call(self,name,args):
        return {"id":"offline-call","type":"function","function":{"name":name,"arguments":json.dumps(args)}}

    def agent(self,responses):
        def respond(request):
            self.payloads.append(json.loads(request.content))
            response=responses[min(len(self.payloads)-1,len(responses)-1)]
            if isinstance(response,Exception): raise response
            if isinstance(response,tuple): return httpx.Response(response[0],json=response[1])
            return httpx.Response(200,json=response)
        factory=bailian.make_model
        def make(settings):
            model=factory(settings,transport=httpx.MockTransport(respond)); self.models.append(model); return model
        with patch.object(bailian,"make_model",side_effect=make): return Agent()

    def test_default_mock_and_bailian_env_only(self):
        env=dict(os.environ,AGENT_PROVIDER="bailian",AGENT_MODEL="ignored-other-model",AGENT_API_KEY="ignored-other-key")
        for key in ("AGENT_ENGINE","AGENT_TRACE_DIR"): env.pop(key,None)
        code="import config,json; print(json.dumps([config.MODEL_NAME,config.ENGINE,config.API_KEY=='offline-bailian-fixture-key',config.TRACE_DIR.name]))"
        got=json.loads(subprocess.check_output([sys.executable,"-c",code],env=env,text=True))
        self.assertEqual(got,["qwen-plus","langchain",True,"bailian_live"])
        env.pop("AGENT_PROVIDER")
        self.assertEqual(subprocess.check_output([sys.executable,"-c","import config; print(config.PROVIDER)"],env=env,text=True).strip(),"mock")

    def test_missing_key_never_builds_http_client(self):
        with patch.dict(os.environ,{"DASHSCOPE_API_KEY":""}),patch.object(bailian,"guarded_client") as factory:
            with self.assertRaisesRegex(DeepSeekError,"missing_DASHSCOPE_API_KEY"): bailian.make_model()
            factory.assert_not_called()

    def test_endpoint_model_and_independent_ledger_fail_closed(self):
        for address in ("http://dashscope.aliyuncs.com/compatible-mode/v1","https://dashscope.aliyuncs.com.evil.invalid/compatible-mode/v1",
                        "https://secret@dashscope.aliyuncs.com/compatible-mode/v1","https://coding.dashscope.aliyuncs.com/v1",
                        "https://attacker.oss-cn-beijing.aliyuncs.com/compatible-mode/v1",
                        "https://dashscope.aliyuncs.com/compatible-mode/v1?key=x"):
            with patch.object(config,"BASE_URL",address),self.assertRaises(DeepSeekError): bailian.validate_configuration()
        with patch.object(config,"MODEL_NAME",""),self.assertRaisesRegex(DeepSeekError,"missing_DASHSCOPE_MODEL"): bailian.validate_configuration()
        with patch.dict(os.environ,{"BAILIAN_BUDGET_PATH":os.environ["DEEPSEEK_BUDGET_PATH"]}),self.assertRaisesRegex(DeepSeekError,"independent"): bailian.Settings.from_env()
        with patch.dict(os.environ,{"BAILIAN_MAX_REQUESTS":"0"}),self.assertRaises(DeepSeekError): bailian.Settings.from_env()

    def test_only_two_tools_and_real_sdk_tool_result_roundtrip(self):
        args={"from_city":"上海","to_city":"杭州","date":str(config.today()),"kind":"高铁","seat_type":"二等座"}
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("query_tickets",args)]}),
                          self.response({"content":"模拟查询完成；车次以本轮工具结果为准。"})])
        result=agent.chat("bailian-one","查上海到杭州的高铁")
        self.assertEqual(result["provider"],"bailian_live")
        self.assertEqual(result["tool_sequence"],["query_tickets"])
        self.assertEqual(set(result),{"session_id","provider","model","user_msg","steps","tool_sequence","reply","finish_reason","tokens","total_latency_ms"})
        self.assertEqual(set(result["steps"][0]["calls"][0]),{"tool","args","ok","latency_ms","result_preview"})
        self.assertEqual({t["function"]["name"] for t in self.payloads[0]["tools"]},{"query_tickets","search_policy"})
        returned=next(m for m in self.payloads[1]["messages"] if m["role"]=="tool")
        self.assertGreater(json.loads(returned["content"])["count"],0)
        self.assertEqual(result["tokens"],{"prompt":26,"completion":10})
        record=agent.langchain_engine.last_live_run
        self.assertEqual(record["actual_models"],["qwen-plus-actual-fixture"])
        self.assertTrue(record["local_trace_saved"])
        self.assertIsNone(record["business_success"])
        self.assertFalse((config.TRACE_DIR/"deepseek_runs.jsonl").exists())

    def test_policy_sources_and_conversation_context(self):
        agent=self.agent([self.response({"tool_calls":[self.call("search_policy",{"question":"锁座有效期"})]}),
            self.response({"content":"锁座有效期 15 分钟，来源 P11。"}),self.response({"content":"继续政策咨询。"})])
        result=agent.chat("same","锁座多久支付？")
        self.assertEqual(result["tool_sequence"],["search_policy"])
        self.assertIn("P11",self.payloads[1]["messages"][-1]["content"])
        agent.chat("same","继续")
        self.assertTrue(any(m.get("content")=="锁座多久支付？" for m in self.payloads[2]["messages"]))

    def test_api_errors_are_classified_without_retry_or_mock(self):
        for status,category in ((400,"invalid_format"),(401,"authentication_failed"),(402,"insufficient_balance"),
                (403,"permission_denied"),(404,"model_or_endpoint_not_found"),(422,"invalid_parameters"),
                (429,"rate_limited"),(500,"server_error"),(503,"service_unavailable")):
            with self.subTest(status=status),patch.dict(os.environ,{"BAILIAN_BUDGET_PATH":str(self.root/f"{status}.db")}):
                before=len(self.payloads)
                agent=self.agent([(status,{"error":{"message":os.environ["DASHSCOPE_API_KEY"]}})])
                with self.assertRaisesRegex(DeepSeekError,category): agent.chat(f"err-{status}","查票")
                self.assertEqual(len(self.payloads),before+1)
                self.assertEqual(agent.langchain_engine.last_live_run["error"]["category"],category)
        all_text="".join(p.read_text(encoding="utf-8") for p in config.TRACE_DIR.glob("*.jsonl"))
        self.assertNotIn(os.environ["DASHSCOPE_API_KEY"],all_text)
        self.assertFalse((config.TRACE_DIR/"traces.jsonl").exists())

    def test_timeout_and_network_error_are_single_attempt(self):
        for name,exc in (("timeout",httpx.ReadTimeout("secret must not be logged")),("network_connection",httpx.ConnectError("secret"))):
            with patch.dict(os.environ,{"BAILIAN_BUDGET_PATH":str(self.root/(name+".db"))}):
                before=len(self.payloads); agent=self.agent([exc])
                with self.assertRaisesRegex(DeepSeekError,name): agent.chat(name,"查票")
                self.assertEqual(len(self.payloads),before+1)

    def test_bailian_400_error_codes_refine_safe_classification(self):
        for code,category in (("Arrearage","insufficient_balance"),("InvalidParameter.Model","model_not_found"),("InvalidApiKey","authentication_failed")):
            with patch.dict(os.environ,{"BAILIAN_BUDGET_PATH":str(self.root/(code+".db"))}):
                agent=self.agent([(400,{"error":{"code":code,"message":"not retained"}})])
                with self.assertRaisesRegex(DeepSeekError,category): agent.chat(code,"你好")

    def test_unknown_usage_is_explicit_error_and_null_evidence(self):
        agent=self.agent([self.response({"content":"普通文本"},usage=False)])
        with self.assertRaisesRegex(DeepSeekError,"token_usage_unknown"): agent.chat("unknown","你好")
        self.assertIsNone(agent.langchain_engine.last_live_run["tokens"])
        self.assertFalse((config.TRACE_DIR/"traces.jsonl").exists())
        row=RequestBudget(bailian.Settings.from_env()).snapshot()["requests"][0]
        self.assertIsNone(row["prompt"])

    def test_tool_failure_not_disguised_as_success(self):
        agent=self.agent([self.response({"tool_calls":[self.call("search_policy",{"question":"退款"})]}),
            self.response({"content":"工具执行失败。"})])
        from target import tools
        with patch.object(tools,"dispatch",return_value=({"error":"fixture tool failure"},False,0)):
            with self.assertRaisesRegex(DeepSeekError,"tool_execution_failed"): agent.chat("failure","退款政策")
        self.assertFalse(agent.langchain_engine.last_live_run["tool_execution_success"])

    def test_unavailable_write_call_is_blocked_by_code(self):
        agent=self.agent([self.response({"tool_calls":[self.call("pay_order",{"order_id":"fake"})]}),
            self.response({"content":"当前只支持查票和政策咨询。"})])
        with self.assertRaisesRegex(DeepSeekError,"tool_execution_failed"): agent.chat("blocked","支付订单")
        executions=[e for e in agent.langchain_engine.last_events if e["event"]=="tool_end"]
        self.assertEqual(executions[0]["executed"],False)

    def test_budget_three_stops_fourth_before_transport(self):
        agent=self.agent([self.response({"content":"当前只支持模拟查票和政策咨询。"})])
        for i in range(3): agent.chat(str(i),"你好")
        with self.assertRaisesRegex(DeepSeekError,"request_budget_exhausted"): agent.chat("four","你好")
        self.assertEqual(len(self.payloads),3)

    def test_shared_initial_budget_limits_both_providers_together(self):
        from target.deepseek_runtime import guarded_client
        sent=[]
        transport=httpx.MockTransport(lambda r:(sent.append(r.url.host) or httpx.Response(200,json={"model":"fixture"})))
        with patch.dict(os.environ,{"TICKET_INITIAL_LIVE_BUDGET":str(self.root/"shared.db")}):
            with bailian.guarded_client(bailian.Settings.from_env(),transport=transport) as client:
                for _ in range(2): client.post(config.BASE_URL+"/chat/completions",json={"model":"qwen-plus","max_tokens":16})
            settings=replace(DeepSettings(),max_requests=3,ledger_path=self.root/"deepseek.db")
            with guarded_client(settings,transport=transport) as client:
                body={"model":"deepseek-flash","max_tokens":16,"thinking":{"type":"disabled"}}
                client.post("https://api.deepseek.com/chat/completions",json=body)
                with self.assertRaises(DeepSeekError): client.post("https://api.deepseek.com/chat/completions",json=body)
        self.assertEqual(len(sent),3)

    def test_six_write_tools_rejected_before_sending(self):
        settings=bailian.Settings.from_env()
        with bailian.guarded_client(settings,transport=httpx.MockTransport(lambda r:self.fail("must not send"))) as client:
            for tool in ("lock_seat","create_order","pay_order","cancel_order","query_order","monitor_seat"):
                with self.assertRaises(DeepSeekError):
                    client.post(config.BASE_URL+"/chat/completions",json={"model":"qwen-plus","max_tokens":16,"tools":[{"function":{"name":tool}}]})
        self.assertEqual(RequestBudget(settings).snapshot()["reserved_requests"],0)

    def test_sdk_does_not_return_credential_in_reply_or_trace(self):
        agent=self.agent([self.response({"content":"fixture "+os.environ["DASHSCOPE_API_KEY"]})])
        result=agent.chat("redact","hello "+os.environ["DASHSCOPE_API_KEY"])
        self.assertNotIn(os.environ["DASHSCOPE_API_KEY"],json.dumps(result))
        self.assertNotIn(os.environ["DASHSCOPE_API_KEY"],(config.TRACE_DIR/"provider_runs.jsonl").read_text(encoding="utf-8"))
