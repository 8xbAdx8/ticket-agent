# Original V3.2 Streamlit-specific assertions retained against legacy_app.py.
# V3.3 default entry has separate test_v33_app.py coverage.
"""真实SDK/真实框架/真实模拟后端，HTTP响应为确定性桩；不计Live成绩。"""
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import config
from target.agent import Agent
from tests import test_deepseek_agent as sdk_fixture
from target.deepseek_runtime import DeepSeekError, Settings


@unittest.skipUnless(sdk_fixture.AVAILABLE,"SDK环境执行")
class LiveFaultPathTests(unittest.TestCase):
    response=sdk_fixture.DeepSeekAgentTests.response
    call=sdk_fixture.DeepSeekAgentTests.call
    agent=sdk_fixture.DeepSeekAgentTests.agent

    def setUp(self):
        sdk_fixture.DeepSeekAgentTests.setUp(self)
        self.profile=patch.dict(os.environ,{"DEEPSEEK_LIVE_TEST_PROFILE":"read_only","AGENT_MUTATIONS":"{}"})
        self.profile.start()

    def tearDown(self):
        self.profile.stop()
        sdk_fixture.DeepSeekAgentTests.tearDown(self)

    def query(self):
        return {"from_city":"上海","to_city":"杭州","date":config.today().isoformat(),"kind":"高铁","seat_type":"二等座"}

    def run_query(self,mutations,*,reply="已收到真实工具结果。"):
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("query_tickets",self.query())]}),
                          self.response({"content":reply})])
        agent.set_mutations(mutations)
        result=agent.chat("fault","查今天上海到杭州高铁二等座")
        return agent,result

    def test_date_actual_database_date_and_sdk_feedback(self):
        agent,result=self.run_query({"date_offset":1})
        from datetime import timedelta
        expected=(config.today()+timedelta(days=1)).isoformat()
        self.assertEqual(result["steps"][0]["calls"][0]["args"]["date"],expected)
        feedback=next(m for m in self.payloads[1]["messages"] if m["role"]=="tool")
        self.assertTrue(all(t["date"]==expected for t in json.loads(feedback["content"])["trains"]))
        self.assertEqual(agent.last_fault_report["model_requests"][0]["tool_calls"][0]["args"]["date"],config.today().isoformat())
        self.assertEqual(result["reply"],"已收到真实工具结果。")

    def test_repeat_one_model_call_two_real_backend_executions(self):
        agent,result=self.run_query({"repeat_call":True})
        self.assertEqual(result["tool_sequence"],["query_tickets"]*2)
        self.assertEqual(len(self.payloads),2)
        report=agent.last_fault_report
        self.assertEqual(len(report["model_requests"][0]["tool_calls"]),1)
        self.assertEqual(sum(e["executed"] for e in report["executions"]),2)
        self.assertEqual([e["execution_index"] for e in report["executions"]],[1,2])

    def test_route_actual_query_not_policy_and_database_unchanged(self):
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":"退票政策"})]}),
                          self.response({"content":"工具返回了查票结果，未获得退票政策。"})])
        agent.set_mutations({"route_error":True})
        result=agent.chat("route","退票政策")
        self.assertEqual(result["tool_sequence"],["query_tickets"])
        feedback=next(m for m in self.payloads[1]["messages"] if m["role"]=="tool")
        self.assertIn("trains",json.loads(feedback["content"]))
        self.assertEqual(agent.last_fault_report["executions"][0]["args"]["to_city"],"上海")

    def test_citation_original_result_and_actual_feedback(self):
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":"锁座支付"})]}),
                          self.response({"content":"本次结果缺少政策出处，无法提供可检查编号。"})])
        agent.set_mutations({"no_citation":True})
        result=agent.chat("cite","锁座后多久支付？")
        event=agent.last_fault_report["injection_events"][0]
        self.assertIn("doc_id",event["original"]["hits"][0])
        self.assertNotIn("doc_id",event["mutated"]["hits"][0])
        feedback=json.loads(next(m for m in self.payloads[1]["messages"] if m["role"]=="tool")["content"])
        self.assertEqual(feedback["citation_status"],"unavailable")
        self.assertEqual(result["reply"],"本次结果缺少政策出处，无法提供可检查编号。")

    def test_invented_citation_rejected_without_rewriting_raw_reply(self):
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":"支付规则"})]}),
                          self.response({"content":"来源 P11"})])
        agent.set_mutations({"no_citation":True})
        with self.assertRaisesRegex(DeepSeekError,"unavailable_policy_citation"):
            agent.chat("invent","支付政策")
        self.assertTrue(any(e.get("text")=="来源 P11" for e in agent.langchain_engine.last_events))

    def test_untriggered_and_inapplicable_are_explicit(self):
        agent,result=self.run_query({"no_citation":True,"skip_lock":True,"infinite_loop":True})
        status={e["mutation"]:e["status"] for e in agent.last_fault_report["injection_events"]}
        self.assertEqual(status,{"no_citation":"not_triggered","skip_lock":"not_applicable","infinite_loop":"not_applicable"})

    def test_repeat_honors_tool_cap(self):
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("query_tickets",self.query())]}),
                          self.response({"content":"工具未全部完成。"})])
        agent.set_mutations({"repeat_call":True})
        agent.langchain_engine.deepseek_settings=replace(agent.langchain_engine.deepseek_settings,max_tool_calls=1)
        with self.assertRaisesRegex(DeepSeekError,"tool_execution_failed"): agent.chat("cap","查票")
        self.assertEqual(sum(e["executed"] for e in agent.last_fault_report["executions"]),1)
        self.assertEqual(agent.last_fault_report["injection_events"][0]["status"],"blocked")

    def test_ignored_request_cap_retains_real_injection_evidence(self):
        with patch.dict(os.environ,{"DEEPSEEK_MAX_REQUESTS":"1"}):
            agent=self.agent([self.response({"content":None,"tool_calls":[self.call("query_tickets",self.query())]}),
                              self.response({"content":"模拟查询执行完成。"})])
            agent.set_mutations({"date_offset":1})
            result=agent.chat("old-cap","查票")
        self.assertEqual(len(self.payloads),2)
        self.assertEqual(result["finish_reason"],"stop")
        self.assertEqual(agent.last_fault_report["injection_events"][0]["status"],"applied")
        self.assertIsNone(agent.last_fault_report["error"])

    def test_normal_no_sidecar_and_restore_clears_mutated_memory(self):
        agent,result=self.run_query({})
        self.assertIsNone(agent.last_fault_report)
        self.assertFalse((config.TRACE_DIR/"mutation_runs.jsonl").exists())
        agent.set_mutations({"date_offset":1})
        self.assertFalse(agent.langchain_engine.threads)
        agent.set_mutations({})
        self.assertFalse(agent.langchain_engine.threads)

    def test_combined_route_date_repeat_real_path(self):
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":"政策"})]}),
                          self.response({"content":"未收到政策片段。"})])
        agent.set_mutations({"route_error":True,"date_offset":1,"repeat_call":True,"no_citation":True})
        result=agent.chat("combo","政策")
        self.assertEqual(result["tool_sequence"],["query_tickets"]*2)
        self.assertEqual([e["mutation"] for e in agent.last_fault_report["injection_events"]],
                         ["route_error","date_offset","repeat_call","no_citation"])

    def test_web_checkbox_reaches_executor_and_restore_clears_fault_state(self):
        from streamlit.testing.v1 import AppTest
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("query_tickets",self.query())]}),
                          self.response({"content":"已查询工具结果。"})])
        with patch("target.agent.Agent",return_value=agent):
            app=AppTest.from_file(str(config.BASE_DIR/"web/legacy_app.py"),default_timeout=30).run()
            next(c for c in app.checkbox if c.label=="date_offset").check().run()
            app.text_input[0].set_value("查今天上海到杭州的高铁")
            next(b for b in app.button if b.label=="发送").click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.session_state["last_fault_report"]["injection_events"][0]["mutation"],"date_offset")
            self.assertEqual(agent.mutations,{"date_offset":1})
            self.assertTrue(any("实际缺陷注入证据" in h.value for h in app.subheader))
            next(b for b in app.button if b.label=="恢复正常模式").click().run()
            self.assertEqual(agent.mutations,{})
            self.assertIsNone(app.session_state["last_fault_report"])

    def test_sandbox_required_rejects_original_db_http_and_unbounded_budget(self):
        for changes in ({},{"DEEPSEEK_SANDBOX_DIR":str(self.folder)},{"DEEPSEEK_MAX_REQUESTS":"0"}):
            with patch.dict(os.environ,{"DEEPSEEK_LIVE_TEST_PROFILE":"full_sandbox",**changes}):
                with self.assertRaises(DeepSeekError): Settings.from_env()

    def sandbox(self):
        from scripts.create_fault_sandbox import create_sandbox
        base=config.BASE_DIR/"artifacts/runtime"
        base.mkdir(parents=True,exist_ok=True)
        tmp=tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(tmp.cleanup)
        root=create_sandbox(Path(tmp.name)/"sandbox")
        cp=patch.multiple(config,DB_PATH=root/"tickets.db",TRACE_DIR=root/"traces",LC_TOOLSET="all")
        ep=patch.dict(os.environ,{"DEEPSEEK_LIVE_TEST_PROFILE":"full_sandbox","DEEPSEEK_SANDBOX_DIR":str(root),
                                "DEEPSEEK_BUDGET_PATH":str(root/"requests.db"),"DEEPSEEK_MAX_REQUESTS":"5"})
        cp.start();ep.start()
        self.addCleanup(cp.stop);self.addCleanup(ep.stop)
        return root

    def test_skip_lock_backend_rejects_fake_lock_no_orders_or_inventory_change(self):
        root=self.sandbox()
        args={"train_no":"G7303","date":config.today().isoformat(),"seat_type":"二等座","passengers":["张三"]}
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("lock_seat",args)]}),
                          self.response({"content":"下单失败，缺少有效锁座。"})])
        agent.set_mutations({"skip_lock":True})
        with self.assertRaisesRegex(DeepSeekError,"tool_execution_failed"): agent.chat("skip","帮我订今天上海到杭州的高铁，乘客张三")
        entry=agent.last_fault_report["executions"][0]
        self.assertTrue(entry["executed"])
        self.assertEqual(entry["tool"],"create_order")
        self.assertFalse(entry["ok"])
        self.assertIn("lock_id",entry["result"]["error"])
        with closing(sqlite3.connect(root/"tickets.db")) as c:
            self.assertEqual(c.execute("select count(*) from orders").fetchone()[0],0)
            self.assertEqual(c.execute("select count(*) from locks").fetchone()[0],0)

    def test_skip_lock_does_not_bypass_payment_authorization(self):
        self.sandbox()
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("pay_order",{"order_id":"ODfake"})]}),
                          self.response({"content":"没有支付授权，未执行支付。"})])
        agent.set_mutations({"skip_lock":True})
        with self.assertRaisesRegex(DeepSeekError,"tool_execution_failed"): agent.chat("pay","只查票")
        self.assertFalse(agent.last_fault_report["executions"][0]["executed"])

    def test_finite_monitor_loop_stops_at_agent_steps_with_one_model_request(self):
        self.sandbox()
        args={"train_no":"G101","date":config.today().isoformat(),"seat_type":"二等座","duration_min":30}
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("monitor_seat",args)]})])
        agent.set_mutations({"infinite_loop":True})
        result=agent.chat("loop","请帮我候补监控余票")
        self.assertEqual(result["finish_reason"],"max_steps_exceeded")
        self.assertEqual(result["tool_sequence"],["monitor_seat"]*3)
        self.assertEqual(len(self.payloads),1)
        self.assertTrue(any(e.get("reason")=="agent_max_steps" for e in agent.langchain_engine.last_events))

    def test_finite_loop_tool_limit_has_distinct_reason(self):
        self.sandbox()
        args={"train_no":"G101","date":config.today().isoformat(),"seat_type":"二等座"}
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("monitor_seat",args)]})])
        agent.set_mutations({"infinite_loop":True})
        agent.langchain_engine.deepseek_settings=replace(agent.langchain_engine.deepseek_settings,max_tool_calls=1)
        with self.assertRaisesRegex(DeepSeekError,"tool_call_limit_exceeded"): agent.chat("toolcap","请帮我候补监控")
        self.assertEqual(sum(e["executed"] for e in agent.last_fault_report["executions"]),1)

    def test_langchain_mock_write_fault_without_sandbox_is_blocked(self):
        with patch.multiple(config,PROVIDER="mock",LC_TOOLSET="all",ENGINE="langchain"):
            agent=Agent(mutations={"skip_lock":True})
            result=agent.chat("mock-unsafe","帮我订明天上海到杭州的高铁")
            self.assertTrue(any(not c["ok"] for s in result["steps"] for c in s["calls"]))
            self.assertTrue(any(e["status"]=="blocked" for e in agent.last_fault_report["injection_events"]))
            self.assertFalse(any(e["executed"] for e in agent.last_fault_report["executions"] if e["tool"]=="create_order"))

    def test_langchain_mock_write_fault_in_isolated_sandbox_reaches_backend(self):
        self.sandbox()
        with patch.multiple(config,PROVIDER="mock",ENGINE="langchain"):
            agent=Agent(mutations={"skip_lock":True})
            agent.chat("mock-safe","帮我订明天上海到杭州的高铁")
            attempts=[e for e in agent.last_fault_report["executions"] if e["tool"]=="create_order"]
            self.assertTrue(attempts[0]["executed"])
            self.assertFalse(attempts[0]["ok"])

    def test_one_step_cannot_be_claimed_as_repeated_loop(self):
        self.sandbox()
        args={"train_no":"G101","date":config.today().isoformat(),"seat_type":"二等座"}
        with patch.object(config,"MAX_STEPS",1):
            agent=self.agent([self.response({"content":None,"tool_calls":[self.call("monitor_seat",args)]})])
            agent.set_mutations({"infinite_loop":True})
            result=agent.chat("one-step","请帮我候补监控余票")
        self.assertEqual(result["tool_sequence"],["monitor_seat"])
        self.assertEqual(agent.last_fault_report["injection_events"][0]["status"],"blocked")
