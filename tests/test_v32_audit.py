"""V3.2 SDK 桩/实际框架/实际隔离后端的证据一致性，无外部请求。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import config
from data.seed import build_db
from target.agent import Agent
from target.diagnostics import read_audits, detect_hallucinated_trains, redact_credentials
from target.trace import Trace
from tests import test_live_faults as fixtures


class AuditCompatibilityTests(unittest.TestCase):
    def test_legacy_baseline_mutant_restore_and_unique_ids(self):
        with tempfile.TemporaryDirectory() as directory, patch.multiple(config,PROVIDER="mock",ENGINE="legacy",
                DB_PATH=Path(directory)/"tickets.db",TRACE_DIR=Path(directory)/"traces",USE_HTTP_MOCK=False), patch.dict(os.environ,{"AGENT_MUTATIONS":"{}"}):
            build_db()
            agent=Agent(mutations={})
            normal=agent.chat("same","查今天上海到杭州高铁")
            baseline=agent.last_audit_report
            agent.set_mutations({"hallucinated_train":True})
            mutant=agent.chat("same","查今天上海到杭州高铁")
            audit=agent.last_audit_report
            self.assertNotIn("G9999",audit["authority"]["trains"])
            entry=audit["fault_report"]["executions"][0]
            self.assertTrue(entry["executed"])
            self.assertEqual(entry["parameter_validation"]["status"],"valid")
            self.assertNotIn("G9999",[r["train_no"] for r in entry["original_result"]["trains"]])
            self.assertIn("G9999",mutant["reply"])
            self.assertTrue(audit["judgement"]["hallucination"]["hallucination_detected"])
            event=next(e for e in audit["mutation_events"] if e["mutation_name"]=="hallucinated_train")
            self.assertEqual(event["status"],"applied")
            self.assertEqual(event["related_step"],1)
            self.assertEqual(event["related_tool_call_id"],entry["call_id"])
            self.assertNotEqual(audit["trace_id"],baseline["trace_id"])
            agent.set_mutations({})
            self.assertIsNone(agent.last_audit_report)
            restored=agent.chat("same","查今天上海到杭州高铁")
            self.assertNotIn("G9999",restored["reply"])
            self.assertEqual(set(normal),set(mutant))
            self.assertEqual(len(normal),10)
            self.assertEqual(len(normal["steps"][0]["calls"][0]),5)
            self.assertEqual(len(read_audits(config.TRACE_DIR)),3)
            self.assertIsNone(baseline["judgement"]["dimensions"]["injection_applied"])

    def test_public_trace_credentials_only_redaction(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{"DEEPSEEK_API_KEY":"private-test-marker"}):
            trace=Trace("privacy","private-test-marker")
            trace.record_call(0,"example",{"contact":"13800000000","Authorization":"anything"},
                              {"api_key":"unconfigured-other-secret"},True,0)
            record=trace.finish("Bearer raw-secret").to_dict()
            trace.save(Path(folder)/"trace.jsonl")
            output=(Path(folder)/"trace.jsonl").read_text(encoding="utf-8")
            for secret in ("private-test-marker","raw-secret","anything","unconfigured-other-secret"):
                self.assertNotIn(secret,output)
            self.assertEqual(record["steps"][0]["calls"][0]["args"]["contact"],"13800000000")
            self.assertEqual(json.loads(output),record)
            self.assertNotIn("other",str(redact_credentials({"result":'Authorization="other"'})))


@unittest.skipUnless(fixtures.sdk_fixture.AVAILABLE,"SDK 环境执行")
class AuditSDKTests(unittest.TestCase):
    setUp=fixtures.LiveFaultPathTests.setUp
    tearDown=fixtures.LiveFaultPathTests.tearDown
    response=fixtures.LiveFaultPathTests.response
    call=fixtures.LiveFaultPathTests.call
    agent=fixtures.LiveFaultPathTests.agent
    query=fixtures.LiveFaultPathTests.query
    sandbox=fixtures.LiveFaultPathTests.sandbox

    def execute(self,name):
        query=self.query()
        tool="search_policy" if name in ("route_error","no_citation") else "query_tickets"
        args={"question":"退票政策"} if tool=="search_policy" else query
        reply="本次未取得可核验政策来源。" if tool=="search_policy" else "查到 G9999 有余票。" if name=="hallucinated_train" else "已收到工具结果。"
        if name in ("skip_lock","infinite_loop"):
            self.sandbox()
            tool="lock_seat" if name=="skip_lock" else "monitor_seat"
            args={"train_no":"G7301","date":config.today().isoformat(),"seat_type":"二等座"}
            if name=="skip_lock":args["passengers"]=["张三"]
            else:args["train_no"]="G101"
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call(tool,args)]}),
                          self.response({"content":reply})])
        agent.set_mutations({name:1 if name=="date_offset" else True})
        message=("订今天上海到杭州高铁，乘客张三" if name=="skip_lock" else "请帮我候补监控今天余票" if name=="infinite_loop"
                 else "锁座支付政策是什么？" if name in ("route_error","no_citation") else "查今天上海到杭州高铁")
        try: result=agent.chat(name,message)
        except fixtures.DeepSeekError:
            self.assertEqual(name,"skip_lock")
            result=None
        return agent,result

    def test_seven_mutations_have_linked_actual_evidence(self):
        # 每个子场景重建 SDK/临时预算，完全不连接网络。
        for name in ("date_offset","route_error","no_citation","repeat_call","hallucinated_train","infinite_loop","skip_lock"):
            with self.subTest(mutation=name):
                self.payloads.clear()
                with patch.dict(os.environ,{"DEEPSEEK_BUDGET_PATH":str(self.folder/(name+"-budget.db"))}):
                    agent,result=self.execute(name)
                audit=agent.last_audit_report
                events=[e for e in audit["mutation_events"] if e["mutation_name"]==name]
                self.assertTrue(any(e["status"]=="applied" for e in events))
                applied=next(e for e in events if e["status"]=="applied")
                self.assertTrue(applied["timestamp"])
                self.assertTrue(applied["target"])
                self.assertTrue(applied["related_tool_call_id"])
                self.assertIsNotNone(applied["related_step"])
                self.assertTrue(audit["judgement"]["dimensions"]["platform_defect_detected"])
                self.assertTrue(any(c["result"]=="fail" for c in audit["judgement"]["assertions"]))
                self.assertTrue(all(e["parameter_validation"]["status"]=="valid" for e in audit["fault_report"]["executions"]))
                self.assertEqual(audit["judgement"]["case_id"],audit["trace_id"])
                if name in ("no_citation","route_error","infinite_loop"):
                    self.assertFalse(audit["judgement"]["dimensions"]["business_correct"])
                if name=="date_offset":
                    checks={c["assertion"]:c["passed"] for c in audit["judgement"]["assertions"]}
                    self.assertTrue(checks["model_original_date_matches_user"])
                    self.assertFalse(checks["executed_query_date_matches_user"])
                if name=="skip_lock":
                    self.assertFalse(audit["contract_returned"])
                    self.assertFalse(audit["authority"]["orders"])
                    self.assertTrue(audit["judgement"]["dimensions"]["safe_stop"])
    def test_model_original_wrong_date_separated_from_injector(self):
        from datetime import timedelta
        args=self.query();args["date"]=(config.today()+timedelta(days=2)).isoformat()
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("query_tickets",args)]}),self.response({"content":"完成查询。"})])
        agent.set_mutations({"date_offset":1})
        agent.chat("wrong-first","查今天上海到杭州高铁")
        checks={c["assertion"]:c["passed"] for c in agent.last_audit_report["judgement"]["assertions"]}
        self.assertFalse(checks["model_original_date_matches_user"])
        self.assertFalse(checks["executed_query_date_matches_user"])

    def test_invalid_parameter_does_not_claim_backend_executed(self):
        args=self.query();args["date"]="not-a-date"
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("query_tickets",args)]}),self.response({"content":"工具失败。"})])
        with self.assertRaises(fixtures.DeepSeekError):agent.chat("invalid","查高铁")
        entry=agent.last_audit_report["fault_report"]["executions"][0]
        self.assertFalse(entry["executed"])
        self.assertEqual(entry["parameter_validation"]["status"],"invalid")

    def test_no_citation_reject_preserves_raw_public_reply(self):
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("search_policy",{"question":"支付政策"})]}),self.response({"content":"来源 P11"})])
        agent.set_mutations({"no_citation":True})
        with self.assertRaises(fixtures.DeepSeekError):agent.chat("invent","支付政策")
        audit=agent.last_audit_report
        self.assertEqual(audit["raw_model_reply"],"来源 P11")
        self.assertFalse(audit["contract_returned"])
        self.assertIsNone(audit["judgement"]["dimensions"]["agent_recovered"])

    def test_actual_corrective_query_required_for_recovery(self):
        from datetime import timedelta
        first=self.query();second=self.query()
        second["date"]=(config.today()-timedelta(days=1)).isoformat()
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("query_tickets",first,"first")]}),
                          self.response({"content":None,"tool_calls":[self.call("query_tickets",second,"corrective")]}),
                          self.response({"content":"已查询到今天的模拟余票。"})])
        agent.set_mutations({"date_offset":1})
        agent.chat("corrected","查今天上海到杭州高铁")
        dims=agent.last_audit_report["judgement"]["dimensions"]
        self.assertTrue(dims["agent_anomaly_recognized"])
        self.assertTrue(dims["agent_recovered"])

    def test_self_claim_without_corrective_action_is_unknown(self):
        agent=self.agent([self.response({"content":None,"tool_calls":[self.call("query_tickets",self.query())]}),
                          self.response({"content":"我发现了日期错误，已经纠正。"})])
        agent.set_mutations({"date_offset":1})
        agent.chat("claim","查今天上海到杭州高铁")
        dims=agent.last_audit_report["judgement"]["dimensions"]
        self.assertIsNone(dims["agent_anomaly_recognized"])
        self.assertIsNone(dims["agent_recovered"])
        self.assertFalse(dims["business_correct"])

    def test_unknown_token_usage_explicit_in_audit(self):
        agent=self.agent([self.response({"content":"桩没有用量。"},usage=False)])
        with self.assertRaises(fixtures.DeepSeekError):agent.chat("unknown-usage","你好")
        audit=agent.last_audit_report
        self.assertFalse(audit["contract_returned"])
        self.assertEqual(audit["token_usage_evidence"]["status"],"unknown_or_partial")
        self.assertIsNone(audit["token_usage_evidence"]["reported"])
