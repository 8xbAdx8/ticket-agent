"""A 的 V3 框架自测，不包含 B 正式判定器。V2 无框架环境下明确 skip。"""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import date, datetime
from unittest.mock import patch
import config
from data.seed import build_db
from target.agent import Agent
from target import providers

try:
    from target.langchain_model import LangChainMockModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from pydantic import Field
    AVAILABLE = True
except ModuleNotFoundError:
    AVAILABLE = False

if AVAILABLE:
    class ScriptedModel(LangChainMockModel):
        script: list[dict] = Field(default_factory=list)
        repeated: bool = False
        index: int = 0

        def _generate(self,messages,stop=None,run_manager=None,**kwargs):
            self.received_messages.append(list(messages))
            item = self.script[0] if self.repeated else (self.script[self.index] if self.index < len(self.script) else {"content":"处理完成"})
            self.index += 1
            if item.get("raise"):
                raise RuntimeError("sensitive-provider-detail")
            calls = [{"name":item["tool"],"args":item["args"],"id":f"script_{self.index}","type":"tool_call"}] if "tool" in item else []
            if "calls" in item:
                calls = [{**c,"id":f"script_{self.index}_{i}","type":"tool_call"} for i,c in enumerate(item["calls"])]
            m = AIMessage(content=item.get("content",""),tool_calls=calls,
                          usage_metadata={"input_tokens":3,"output_tokens":2,"total_tokens":5})
            return ChatResult(generations=[ChatGeneration(message=m)])


@unittest.skipUnless(AVAILABLE,"LangChain 仅安装在独立 V3 环境")
class LangChainPrototypeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(config,"DB_PATH",Path(self.tmp.name)/"tickets.db"),
                        patch.object(config,"TRACE_DIR",Path(self.tmp.name)/"traces"),
                        patch.object(config,"PROVIDER","mock"), patch.object(config,"USE_HTTP_MOCK",False),
                        patch.object(config,"today",return_value=date(2026,10,13)),
                        patch.object(config,"now",return_value=datetime(2026,10,13,10,0))]
        for p in self.patches:
            p.start()
        providers.clear_mutations()
        build_db()
        self.agent = Agent(engine="langchain",tool_names=["query_tickets","search_policy"])

    def tearDown(self):
        providers.clear_mutations()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def chat(self,text,sid="lc",agent=None):
        r = (agent or self.agent).chat(sid,text)
        self.assertEqual(set(r),{"session_id","provider","model","user_msg","steps","tool_sequence","reply","finish_reason","tokens","total_latency_ms"})
        calls = [c for step in r["steps"] for c in step["calls"]]
        self.assertEqual(r["tool_sequence"],[c["tool"] for c in calls])
        for c in calls:
            self.assertEqual(set(c),{"tool","args","ok","latency_ms","result_preview"})
        return r

    def args(self,r):
        return r["steps"][0]["calls"][0]["args"]

    def test_single_query_runs_framework_and_feedback(self):
        with patch.object(Agent,"_chat",side_effect=AssertionError("禁止执行旧循环")):
            r = self.chat("查明天上海到杭州的高铁")
        self.assertEqual(r["provider"],"langchain_mock")
        self.assertEqual(r["tool_sequence"],["query_tickets"])
        self.assertIn("有余票",r["reply"])
        received = self.agent.provider.received_messages[-1]
        tool = next(m for m in received if isinstance(m,ToolMessage))
        self.assertGreater(json.loads(tool.content)["count"],0)
        ai = next(m for m in received if isinstance(m,AIMessage) and m.tool_calls)
        self.assertEqual(ai.tool_calls[0]["id"],tool.tool_call_id)
        self.assertIn("model",self.agent.langchain_engine.graph.get_graph().nodes)

    def test_policy_returns_checkable_source(self):
        r = self.chat("锁座后多久必须完成支付？")
        self.assertEqual(r["tool_sequence"],["search_policy"])
        self.assertIn("P11",r["reply"])
        event = next(e for e in self.agent.langchain_engine.last_events if e["event"] == "tool_end")
        self.assertTrue(any(h["source"].endswith("#P11") for h in event["result"]["hits"]))

    def test_multiturn_kind_date_and_seat_inheritance(self):
        self.chat("查明天上海到杭州的高铁")
        self.assertEqual(self.args(self.chat("那机票呢"))["seat_type"],"经济舱")
        self.assertEqual(self.args(self.chat("还是高铁吧"))["kind"],"高铁")
        self.assertEqual(self.args(self.chat("后天呢"))["date"],"2026-10-15")

    def test_distinct_sessions_are_isolated(self):
        self.chat("查明天北京到成都的机票公务舱",sid="A")
        self.chat("查明天上海到杭州的高铁",sid="B")
        args = self.args(self.chat("后天呢",sid="A"))
        self.assertEqual((args["from_city"],args["to_city"],args["kind"],args["seat_type"]),("北京","成都","机票","公务舱"))
        self.assertEqual(self.chat("后天呢",sid="C")["tool_sequence"],[])

    def test_reset_removes_framework_thread_state(self):
        self.chat("查明天上海到杭州的高铁")
        self.agent.reset("lc")
        self.assertEqual(self.chat("后天呢")["tool_sequence"],[])
        self.agent.reset()
        self.assertEqual(self.agent.langchain_engine.threads,set())

    def test_original_schema_and_invalid_arguments(self):
        from target.langchain_agent import adapt_tool
        from target.tools import TOOLS
        original = next(t["function"]["parameters"] for t in TOOLS if t["function"]["name"]=="query_tickets")
        self.assertEqual(adapt_tool("query_tickets").args_schema,original)
        model = ScriptedModel(script=[{"tool":"query_tickets","args":{"from_city":"上海"}}])
        r = self.chat("查票",agent=Agent(engine="langchain",model=model))
        self.assertFalse(r["steps"][0]["calls"][0]["ok"])
        self.assertIn("缺少必填",r["steps"][0]["calls"][0]["result_preview"])
        self.assertTrue(any(isinstance(m,ToolMessage) and m.status=="error" for m in model.received_messages[-1]))

    def test_backend_error_returns_to_model_without_secret(self):
        with patch("target.tools._call_local",side_effect=RuntimeError("private-path-and-token")):
            r = self.chat("查明天上海到杭州的高铁")
        self.assertFalse(r["steps"][0]["calls"][0]["ok"])
        self.assertNotIn("private-path",json.dumps(r))
        self.assertIn("RuntimeError",r["reply"])

    def test_model_budget_and_recovery_are_not_graph_node_count(self):
        args = dict(from_city="上海",to_city="杭州",date="2026-10-14")
        model = ScriptedModel(script=[{"tool":"query_tickets","args":args}],repeated=True)
        agent = Agent(engine="langchain",model=model)
        with patch.object(config,"MAX_STEPS",2):
            r = self.chat("查票",agent=agent)
        self.assertEqual(r["finish_reason"],"max_steps_exceeded")
        self.assertEqual(r["tool_sequence"],["query_tickets"]*2)
        self.assertEqual(r["tokens"],{"prompt":6,"completion":4})
        self.assertEqual(len(model.received_messages),2)
        model.repeated=False
        self.assertEqual(self.chat("继续",agent=agent)["finish_reason"],"stop")

    def test_model_exception_is_safe_and_returns_stop(self):
        model = ScriptedModel(script=[{"raise":True}])
        r = self.chat("查票",agent=Agent(engine="langchain",model=model))
        self.assertEqual(r["finish_reason"],"stop")
        self.assertIn("RuntimeError",r["reply"])
        self.assertNotIn("sensitive-provider",r["reply"])

    def test_trace_jsonl_equals_return_value(self):
        r = self.chat("查明天上海到杭州的高铁")
        saved = json.loads((config.TRACE_DIR/"traces.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(saved,r)
        self.assertGreaterEqual(r["total_latency_ms"],0)

    def test_legacy_and_mutation_behavior_are_retained(self):
        providers.set_mutation("repeat_call")
        agent = Agent(engine="legacy")
        self.assertEqual(agent.chat("old","查明天上海到杭州的高铁")["tool_sequence"],["query_tickets"]*2)
        with self.assertRaises(ValueError):
            Agent(engine="langchain")

    def test_live_requires_key_before_network(self):
        with patch.object(config,"PROVIDER","openai"), patch.object(config,"API_KEY",""):
            with self.assertRaises(ValueError):
                Agent(engine="langchain")

    def test_unknown_tool_is_an_actual_failed_trace_call(self):
        model = ScriptedModel(script=[{"tool":"made_up_tool","args":{}}])
        r = self.chat("查票",agent=Agent(engine="langchain",model=model))
        self.assertEqual(r["tool_sequence"],["made_up_tool"])
        self.assertFalse(r["steps"][0]["calls"][0]["ok"])


if __name__ == "__main__":
    unittest.main()
