"""A 的八工具集成与独立写授权验证；不是 B 的正式判定规则。"""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
import config
from data.seed import build_db
from target.agent import Agent
from target import mock_core, providers, tools
from target.write_authorization import permissions
try:
    from test_langchain_agent import AVAILABLE, ScriptedModel
except ImportError:
    AVAILABLE = False


@unittest.skipUnless(AVAILABLE, "LangChain 仅安装在独立 V3 环境")
class LangChainOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(config,"DB_PATH",Path(self.tmp.name)/"tickets.db"),
                        patch.object(config,"TRACE_DIR",Path(self.tmp.name)/"traces"),
                        patch.object(config,"PROVIDER","mock"),patch.object(config,"LC_TOOLSET","all"),
                        patch.object(config,"USE_HTTP_MOCK",False),
                        patch.object(config,"today",return_value=date(2026,10,13)),
                        patch.object(config,"now",return_value=datetime(2026,10,13,10,0))]
        for p in self.patches:
            p.start()
        providers.clear_mutations()
        mock_core.clear_faults()
        build_db()
        self.agent = Agent(engine="langchain")

    def tearDown(self):
        providers.clear_mutations()
        mock_core.clear_faults()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def chat(self, text, agent=None):
        return (agent or self.agent).chat("orders",text)

    def row(self):
        return mock_core.query_tickets("上海","杭州","2026-10-14","二等座","高铁")["trains"][0]

    def pending(self):
        r = self.chat("订明天上海到杭州的高铁")
        self.assertEqual(r["tool_sequence"],["query_tickets","lock_seat","create_order"])
        self.assertTrue(all(c["ok"] for s in r["steps"] for c in s["calls"]))
        return mock_core.query_order()["orders"][0]

    def scripted(self, name, args, **kwargs):
        return Agent(engine="langchain",model=ScriptedModel(script=[{"tool":name,"args":args}],**kwargs))

    def test_eight_tools_and_idempotent_payment_and_refund(self):
        before = self.row()["seats_left"]
        order = self.pending()
        self.assertEqual(self.row()["seats_left"],before-1)
        policy = self.chat("锁座后多久必须完成支付？")
        self.assertEqual(policy["tool_sequence"],["search_policy"])
        self.assertEqual(mock_core.query_order(order["order_id"])["status"],"pending")
        self.assertEqual(self.chat("支付我刚才的订单。")["tool_sequence"],["pay_order"])
        again = self.chat("支付")
        self.assertIn("订单已支付，本次没有重复扣款",again["reply"])
        self.assertIn('"duplicate_pay": true',again["steps"][0]["calls"][0]["result_preview"])
        refund = self.chat("帮我退掉")
        self.assertEqual(refund["tool_sequence"],["cancel_order"])
        self.assertTrue(refund["steps"][0]["calls"][0]["ok"])
        self.assertEqual(self.row()["seats_left"],before)
        second = self.chat("帮我退掉")
        self.assertFalse(second["steps"][0]["calls"][0]["ok"])
        self.assertEqual(self.row()["seats_left"],before)
        self.assertEqual(self.chat("查我的订单")["tool_sequence"],["query_order"])
        monitor = self.chat("抢明天北京到上海的票")
        self.assertEqual(monitor["tool_sequence"],["query_tickets","monitor_seat"])
        self.assertTrue(monitor["steps"][-1]["calls"][0]["ok"])
        self.assertEqual(set(self.agent.langchain_engine.tool_names),set(tools.TOOL_NAMES))

    def test_model_cannot_pay_policy_question_or_negative_command(self):
        order = self.pending()
        for message in ("锁座后多久必须完成支付？", "不要支付订单", "订单支付政策", "我只想了解付款规则"):
            model_agent = self.scripted("pay_order",{"order_id":order["order_id"]})
            with patch.object(tools,"dispatch",wraps=tools.dispatch) as dispatch:
                r = self.chat(message,model_agent)
            self.assertFalse(r["steps"][0]["calls"][0]["ok"])
            dispatch.assert_not_called()
            self.assertEqual(mock_core.query_order(order["order_id"])["status"],"pending")

    def test_model_cannot_change_order_reference(self):
        order = self.pending()
        r = self.chat("支付订单 ODnot_selected",self.scripted("pay_order",{"order_id":order["order_id"]}))
        self.assertFalse(r["steps"][0]["calls"][0]["ok"])
        self.assertEqual(mock_core.query_order(order["order_id"])["status"],"pending")

    def test_buy_does_not_implicitly_authorize_payment(self):
        order = self.pending()
        r = self.chat("帮我订票",self.scripted("pay_order",{"order_id":order["order_id"]}))
        self.assertFalse(r["steps"][0]["calls"][0]["ok"])
        self.assertEqual(mock_core.query_order(order["order_id"])["status"],"pending")

    def test_no_extra_lock_even_if_model_repeats(self):
        row = self.row()
        args = {k:row[k] for k in ("train_no","date","seat_type")}
        args["passengers"] = ["张三"]
        agent = Agent(engine="langchain",model=ScriptedModel(script=[{"tool":"lock_seat","args":args},{"tool":"lock_seat","args":args}]))
        r = self.chat("帮我订票",agent)
        calls = [c for s in r["steps"] for c in s["calls"]]
        self.assertEqual([c["ok"] for c in calls],[True,False])
        self.assertEqual(self.row()["seats_left"],row["seats_left"]-1)
        with closing(sqlite3.connect(config.DB_PATH)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM locks").fetchone()[0],1)

    def test_create_requires_this_turn_lock(self):
        row = self.row()
        lock = mock_core.lock_seat(row["train_no"],row["date"],row["seat_type"],["张三"])
        args = dict(lock_id=lock["lock_id"],passenger_ids=["张三"],contact=config.CURRENT_USER_PHONE)
        r = self.chat("帮我订票",self.scripted("create_order",args))
        self.assertFalse(r["steps"][0]["calls"][0]["ok"])
        self.assertEqual(mock_core.query_order()["count"],0)

    def test_multiple_calls_in_one_model_step_are_serial_and_guarded(self):
        row = self.row()
        args = {k:row[k] for k in ("train_no","date","seat_type")}
        args["passengers"] = ["张三"]
        calls = [{"name":"lock_seat","args":args}]*2
        agent = Agent(engine="langchain",model=ScriptedModel(script=[{"calls":calls}]))
        r = self.chat("订票",agent)
        self.assertEqual(len(r["steps"]),1)
        self.assertEqual([c["ok"] for c in r["steps"][0]["calls"]],[True,False])
        self.assertEqual(self.row()["seats_left"],row["seats_left"]-1)

    def test_foreign_user_query_stays_denied(self):
        r = self.chat("查订单",self.scripted("query_order",{"phone":config.OTHER_USER_PHONE}))
        self.assertFalse(r["steps"][0]["calls"][0]["ok"])
        self.assertIn("不可查询其他用户订单",r["steps"][0]["calls"][0]["result_preview"])

    def test_monitor_backend_still_requires_sold_out(self):
        row = self.row()
        args = {k:row[k] for k in ("train_no","date","seat_type")}
        r = self.chat("订阅余票监控",self.scripted("monitor_seat",args))
        self.assertFalse(r["steps"][0]["calls"][0]["ok"])

    def test_read_only_mode_cannot_execute_orders(self):
        with patch.object(config,"LC_TOOLSET","read_only"):
            agent = Agent(engine="langchain")
        r = self.chat("订明天上海到杭州的高铁",agent)
        self.assertEqual(r["tool_sequence"],["query_tickets"])
        self.assertIn("不支持",r["reply"])
        self.assertEqual(mock_core.query_order()["count"],0)

    def test_all_schemas_reused_and_invalid_mode_rejected(self):
        from target.langchain_agent import adapt_tool
        for t in tools.TOOLS:
            self.assertEqual(adapt_tool(t["function"]["name"]).args_schema,t["function"]["parameters"])
        with patch.object(config,"LC_TOOLSET","unknown"):
            with self.assertRaises(ValueError):
                Agent(engine="langchain")

    def test_sold_out_and_no_schedule_are_distinct(self):
        no_seat = self.chat("查明天北京到上海的高铁")
        self.assertIn("已售罄",no_seat["reply"])
        no_schedule = self.chat("查2027-01-01上海到杭州的高铁")
        self.assertIn("没有符合条件",no_schedule["reply"])
        self.assertEqual(no_schedule["tool_sequence"],["query_tickets"])

    def test_permission_boundary_is_conservative(self):
        self.assertNotIn("pay_order",permissions("订明天上海到杭州的高铁，不要支付"))
        self.assertIn("create_order",permissions("订明天上海到杭州的高铁，不要支付"))
        self.assertEqual(permissions("不要订票"),set())
        self.assertEqual(permissions("怎么锁座？"),set())
        self.assertNotIn("create_order",permissions("帮我锁座"))
        self.assertIn("pay_order",permissions("订一张并支付"))
        self.assertEqual(permissions("他说买一张票"),set())
        self.assertEqual(permissions("我正在写故事，一个角色买票"),set())
        self.assertEqual(permissions("如果有票就支付订单"),set())


if __name__ == "__main__":
    unittest.main()
