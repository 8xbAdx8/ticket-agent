"""Actual V3.3 entry tests; legacy tests separately retain all V3.2 assertions."""
import shutil
import unittest
from unittest.mock import patch
import config
from streamlit.testing.v1 import AppTest
from web.evidence import mutation_rows


class V33AppTests(unittest.TestCase):
    def setUp(self):
        self.settings=patch.multiple(config,PROVIDER="mock",ENGINE="legacy",LC_TOOLSET="all",USE_HTTP_MOCK=False,USE_VECTOR_RAG=False)
        self.settings.start()
        self.app=AppTest.from_file(str(config.BASE_DIR/"web/app.py"),default_timeout=30).run()
        self.clean()

    def tearDown(self):
        for key in ("user_sessions","lab_archives"):
            try:sessions=self.app.session_state[key]
            except KeyError:sessions=[]
            for session in sessions:
                shutil.rmtree(session.root,ignore_errors=True)
        self.settings.stop()

    def clean(self):
        self.assertEqual([e.message for e in self.app.exception],[])

    def button(self,label):
        return next(x for x in self.app.button if x.label==label)

    def nav(self,page):
        next(r for r in self.app.radio if r.label=="工作空间").set_value("测试工作台").run()
        next(r for r in self.app.radio if r.label=="工作台导航").set_value(page).run()
        self.clean()

    def send(self,message):
        next(t for t in self.app.text_input if t.label=="输入消息").set_value(message)
        self.button("发送").click().run()
        self.clean()

    def user(self):
        return self.app.session_state["user_sessions"][self.app.session_state["user_session_index"]]

    def test_initial_user_mode_never_initializes_or_calls_model(self):
        self.assertIsNone(self.user().agent)
        self.assertFalse(self.user().root.exists())
        self.assertEqual(len(self.app.checkbox),0)

    def test_query_cards_policy_and_rerender_are_real(self):
        self.send("查明天上海到杭州的高铁二等座")
        user=self.user()
        self.assertEqual(user.history[-1]["tool_sequence"],["query_tickets"])
        markup="\n".join(x.value for x in self.app.markdown)
        self.assertEqual(markup.count('class="ticket-card"'),len(user.results[-1][0]["result"]["trains"]))
        self.assertIn("query_tickets",markup)
        self.app.run()
        self.assertEqual(len(user.history),1)
        self.send("锁座后多久必须完成支付？")
        self.assertEqual(user.history[-1]["tool_sequence"],["search_policy"])
        self.assertIn("P11",user.history[-1]["reply"])

    def test_write_confirm_is_explicit_and_payment_idempotency_preserved(self):
        self.send("订明天上海到杭州的高铁")
        self.assertEqual(len(self.user().history),0)
        self.assertFalse(self.user().root.exists())
        self.button("确认执行模拟操作").click().run()
        self.clean()
        self.assertEqual(self.user().history[-1]["tool_sequence"],["query_tickets","lock_seat","create_order"])
        for _ in range(2):
            self.send("支付我刚才的订单")
            self.button("确认执行模拟操作").click().run()
            self.clean()
        self.assertTrue(self.user().results[-1][-1]["result"]["duplicate_pay"])
        self.assertIn("本次没有重复扣款",self.user().history[-1]["reply"])

    def test_new_and_historical_sessions_preserve_messages(self):
        self.send("查明天上海到杭州的高铁")
        old=self.user()
        self.button("新建会话").click().run()
        self.assertNotEqual(self.user().sid,old.sid)
        next(s for s in self.app.selectbox if s.label=="历史会话").select(0).run()
        self.assertEqual(self.user().sid,old.sid)
        self.assertEqual(len(self.user().history),1)

    def test_all_workbench_pages_and_light_theme_render(self):
        for page in ("测试总览","测试实验室","Trace 分析","质量分析","模型对比","集成中心"):
            self.nav(page)
        next(r for r in self.app.radio if r.label=="外观").set_value("浅色").run()
        self.clean()
        self.assertEqual(self.app.session_state["theme"],"浅色")
        self.assertTrue(any("阿里云百炼" in m.value for m in self.app.markdown))

    def test_lab_mutation_isolation_and_trace_diff(self):
        self.nav("测试实验室")
        self.assertEqual(len(self.app.checkbox),8)
        next(c for c in self.app.checkbox if c.label=="hallucinated_train").check().run()
        self.button("执行测试").click().run()
        self.clean()
        lab=self.app.session_state["lab_session"]
        self.assertIn("G9999",lab.history[-1]["reply"])
        self.assertTrue(lab.audits[-1]["judgement"]["dimensions"]["platform_defect_detected"])
        self.assertTrue(any(s.label=="选择变异事件" for s in self.app.selectbox))
        next(r for r in self.app.radio if r.label=="工作空间").set_value("出行助手").run()
        self.send("查明天上海到杭州的高铁")
        self.assertNotIn("G9999",self.user().history[-1]["reply"])

    def test_m8_disables_chat_and_executes_actual_isolated_comparison(self):
        self.nav("测试实验室")
        next(c for c in self.app.checkbox if c.label=="concurrent_duplicate_order").check().run()
        self.assertTrue(self.button("执行测试").disabled)
        self.button("运行并发订单对照（离线）").click().run()
        self.clean()
        records=self.app.session_state["lab_session"].audits
        self.assertEqual([r["judgement"]["quality_verdict"] for r in records],["pass","fail"])
        self.assertTrue(all(r["resources_cleaned"] for r in records))

    def test_quality_subpages_preserve_unknown_and_missed_states(self):
        self.nav("质量分析")
        for name in ("变异热力图","幻觉检测","并发幂等","AI 专项"):
            next(r for r in self.app.radio if r.label=="质量专题").set_value(name).run()
            self.clean()
        self.assertEqual(next(r for r in mutation_rows() if r["case_id"]=="T04" and r["origin"]=="额外探测")["status"],"missed")

    def test_trace_history_does_not_reexecute_and_has_json_search(self):
        self.send("查明天上海到杭州的高铁")
        user=self.user()
        self.nav("Trace 分析")
        self.assertTrue(any(t.label=="搜索 JSON 字段或值" for t in self.app.text_input))
        next(t for t in self.app.text_input if t.label=="搜索 JSON 字段或值").set_value("query_tickets").run()
        self.clean()
        self.assertEqual(len(user.history),1)

    def test_failure_does_not_replace_model_output_with_success(self):
        self.send("查明天上海到杭州的高铁")
        with patch.object(self.user().agent,"chat",side_effect=RuntimeError("DO_NOT_PRINT-secret")):
            self.send("查询另一条路线")
        self.assertEqual(len(self.user().history),1)
        self.assertGreater(len(self.app.error),0)
        self.assertNotIn('class="ticket-card"',"\n".join(m.value for m in self.app.markdown))
        self.assertNotIn("DO_NOT_PRINT-secret",str(self.app))

    def test_dashboard_current_batch_is_separate_from_b(self):
        self.send("查明天上海到杭州的高铁")
        self.nav("测试总览")
        next(s for s in self.app.selectbox if s.label=="证据批次").select("A 当前隔离实验").run()
        self.clean()
        self.assertTrue(any("A 当前隔离实验" in x.value for x in self.app.caption))
        self.assertTrue(any("不是 B 正式" in x.value for x in self.app.info))

    def test_new_live_ui_missing_key_does_not_construct_model(self):
        from web.runtime import Conversation
        session=Conversation("user",engine="langchain",live=True)
        self.app.session_state["user_sessions"]=[session]
        with patch("web.conversation.live_ready",return_value=False),patch("web.runtime.Agent") as agent:
            self.app.run()
            self.clean()
            self.assertTrue(self.button("发送").disabled)
            agent.assert_not_called()
        self.assertFalse(session.root.exists())

    def test_new_live_ui_uses_real_sdk_with_only_mock_transport(self):
        import json
        import os
        from web.runtime import Conversation
        try:
            import httpx
            from target.deepseek_runtime import Settings,make_model
            from target.agent import Agent as RealAgent
            import langchain_deepseek
        except ImportError:
            self.skipTest("DeepSeek SDK protocol test requires the DeepSeek environment")
        session=Conversation("user",engine="langchain",live=True)
        self.app.session_state["user_sessions"]=[session]
        session.root.mkdir(parents=True,exist_ok=True)
        payloads=[]
        def respond(request):
            payloads.append(json.loads(request.content))
            if payloads[-1].get('response_format')=={'type':'json_object'}:
                candidates=json.loads(payloads[-1]['messages'][-1]['content'])['candidates']
                msg={'role':'assistant','content':json.dumps({'suggestions':[
                    {'id':row['id'],'question':row['question']} for row in candidates[:2]]},ensure_ascii=False)}
            else:
                msg={"role":"assistant","content":None,"tool_calls":[{"id":"offline-ui-call","type":"function","function":{"name":"query_tickets","arguments":json.dumps({"from_city":"上海","to_city":"杭州","date":config.today().isoformat(),"kind":"高铁","seat_type":"二等座"},ensure_ascii=False)}}]} if len(payloads)==1 else {"role":"assistant","content":"离线 SDK 桩：查询工具已执行，班次以模拟结果为准。"}
            return httpx.Response(200,json={"id":"offline-ui-only","object":"chat.completion","created":1,"model":"deepseek-flash","choices":[{"index":0,"message":msg,"finish_reason":"tool_calls" if len(payloads)==1 else "stop"}],"usage":{"prompt_tokens":11,"completion_tokens":7,"total_tokens":18}})
        with patch.dict(os.environ,{"DEEPSEEK_API_KEY":"offline-v33-placeholder","DEEPSEEK_BUDGET_PATH":str(session.root/"requests.db"),"DEEPSEEK_MAX_REQUESTS":"5","DEEPSEEK_LIVE_TEST_PROFILE":"read_only","DEEPSEEK_THINKING":"disabled"}),patch.multiple(config,PROVIDER="deepseek",API_KEY="offline-v33-placeholder",MODEL_NAME="deepseek-flash",BASE_URL="https://api.deepseek.com"),patch.multiple("web.runtime",LIVE_AVAILABLE=True,LIVE_MODEL="deepseek-flash",LIVE_URL="https://api.deepseek.com",LIVE_KEY="offline-v33-placeholder"),patch("web.runtime.live_ready",return_value=True),patch("web.conversation.live_ready",return_value=True):
            model=make_model(Settings.from_env(),transport=httpx.MockTransport(respond))
            try:
                with patch("web.runtime.Agent",side_effect=lambda **kw:RealAgent(model=model,**kw)):
                    self.app.run()
                    next(c for c in self.app.checkbox if c.label.startswith("确认发送真实")).check()
                    self.send("查今天上海到杭州的高铁")
                # A UI regression: the original Agent loop still uses two
                # requests; the newly requested automatic follow-up uses one.
                main=[p for p in payloads if 'response_format' not in p]
                auxiliary=[p for p in payloads if p.get('response_format')=={'type':'json_object'}]
                self.assertEqual(len(main),2)
                self.assertEqual(len(auxiliary),1)
                self.assertNotIn('tools',auxiliary[0])
                self.assertEqual(session.followups_for(session.history[-1])['generation_source'],'model')
                self.app.run()
                self.assertEqual(len(payloads),3)
                self.assertEqual({t["function"]["name"] for t in payloads[0]["tools"]},{"query_tickets","search_policy"})
                self.assertEqual(session.history[-1]["tool_sequence"],["query_tickets"])
                self.assertTrue(any(m["role"]=="tool" and m["tool_call_id"]=="offline-ui-call" for m in payloads[1]["messages"]))
                self.assertNotIn("offline-v33-placeholder",str(self.app))
            finally:
                model.root_client.close()

    def test_seven_chat_mutations_reach_actual_legacy_execution(self):
        self.nav("测试实验室")
        scenarios={"date_offset":"查明天上海到杭州的高铁","skip_lock":"订明天上海到杭州的高铁",
            "repeat_call":"查明天上海到杭州的高铁","infinite_loop":"抢明天北京到上海的票",
            "route_error":"退票手续费怎么算","no_citation":"退票手续费怎么算","hallucinated_train":"查明天上海到杭州的高铁"}
        for mutation,message in scenarios.items():
            self.button("恢复正常模式").click().run()
            next(c for c in self.app.checkbox if c.label==mutation).check().run()
            next(t for t in self.app.text_input if t.label=="输入消息").set_value(message)
            self.button("执行测试").click().run()
            self.clean()
            session=self.app.session_state["lab_session"]
            self.assertGreater(len(session.audits),0,mutation)
            self.assertTrue(any(e.get("mutation")==mutation for e in session.audits[-1].get("fault_report",{}).get("injection_events",[])),mutation)

    def test_langchain_mock_write_mutation_uses_existing_sandbox_guard(self):
        try:import langchain
        except ImportError:self.skipTest("LangChain Mock requires framework dependencies")
        self.nav("测试实验室")
        next(s for s in self.app.selectbox if s.label=="执行模式").select("LangChain Mock").run()
        next(c for c in self.app.checkbox if c.label=="skip_lock").check().run()
        next(t for t in self.app.text_input if t.label=="输入消息").set_value("订明天上海到杭州的高铁")
        self.button("执行测试").click().run()
        self.clean()
        session=self.app.session_state["lab_session"]
        self.assertTrue((session.root/".ticket-agent-sandbox.json").is_file())
        self.assertTrue(any(e.get("mutation")=="skip_lock" and e.get("status")=="applied" for e in session.audits[-1]["fault_report"]["injection_events"]))
