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
