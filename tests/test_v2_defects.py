"""成员 A 的缺陷修复回归：不替代 B 的 100 用例/xfail/正式统计。"""
import sqlite3
import json
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
import config
from data.seed import build_db
from target.agent import Agent
from target.providers import MockProvider
from target.tools import dispatch


class V2DefectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db, self.old_trace = config.DB_PATH, config.TRACE_DIR
        config.DB_PATH = Path(self.tmp.name)/"test.db"
        config.TRACE_DIR = Path(self.tmp.name)/"trace"
        self.today_patch = patch("config.today", return_value=date(2026,10,13))
        self.now_patch = patch("config.now", return_value=datetime(2026,10,13,10,0))
        self.today_patch.start()
        self.now_patch.start()
        build_db()
        self.agent = Agent(MockProvider(mutations={}))

    def tearDown(self):
        config.DB_PATH, config.TRACE_DIR = self.old_db, self.old_trace
        self.today_patch.stop()
        self.now_patch.stop()
        self.tmp.cleanup()

    def chat(self, text, sid="v2"):
        result = self.agent.chat(sid, text)
        self.assertEqual(set(result), {"session_id","provider","model","user_msg","steps","tool_sequence","reply","finish_reason","tokens","total_latency_ms"})
        self.assertEqual(result["tool_sequence"], [c["tool"] for s in result["steps"] for c in s["calls"]])
        for step in result["steps"]:
            for call in step["calls"]:
                self.assertEqual(set(call), {"tool","args","ok","latency_ms","result_preview"})
        return result

    def query_args(self, result):
        return [c["args"] for s in result["steps"] for c in s["calls"] if c["tool"] == "query_tickets"][-1]

    def test_def01_reset_seat_on_flight_switch(self):
        self.chat("帮我查明天北京到成都的高铁")
        args = self.query_args(self.chat("那机票呢"))
        self.assertEqual((args["kind"], args["seat_type"]), ("机票", "经济舱"))
        self.assertEqual((args["from_city"],args["to_city"],args["date"]), ("北京","成都","2026-10-14"))

    def test_def01_explicit_seat_and_tool_validation(self):
        self.assertEqual(self.query_args(self.chat("查明天北京到成都机票公务舱"))["seat_type"], "公务舱")
        self.assertEqual(self.chat("查明天北京到成都机票二等座", sid="conflict")["tool_sequence"], [])
        args = dict(from_city="北京",to_city="成都",date="2026-10-14",kind="机票",seat_type="二等座")
        self.assertFalse(dispatch("query_tickets",args)[1])

    def test_def02_switch_back_to_rail(self):
        self.chat("帮我查明天上海到杭州的高铁")
        self.chat("那机票呢")
        args = self.query_args(self.chat("还是高铁吧"))
        self.assertEqual((args["kind"],args["seat_type"]), ("高铁","二等座"))
        self.assertEqual((args["from_city"],args["to_city"],args["date"]), ("上海","杭州","2026-10-14"))

    def test_def02_omission_inherits_mode_seat_date_and_route(self):
        self.chat("查明天北京到成都的机票公务舱")
        next_day = self.query_args(self.chat("后天呢"))
        self.assertEqual((next_day["kind"],next_day["seat_type"],next_day["date"]), ("机票","公务舱","2026-10-15"))
        route = self.query_args(self.chat("到广州呢"))
        self.assertEqual((route["from_city"],route["to_city"],route["kind"],route["seat_type"]), ("北京","广州","机票","公务舱"))
        origin = self.query_args(self.chat("出发地改成上海"))
        self.assertEqual((origin["from_city"],origin["to_city"],origin["date"]), ("上海","广州","2026-10-15"))
        new_route = self.query_args(self.chat("查杭州到西安"))
        self.assertEqual((new_route["kind"],new_route["seat_type"],new_route["date"]), ("机票","公务舱","2026-10-15"))

    def test_def02_ambiguous_mode_and_city_request_clarification(self):
        self.chat("查明天上海到杭州的高铁")
        for message in ("换个交通方式", "高铁还是机票呢", "不坐高铁了", "成都呢"):
            self.assertEqual(self.chat(message)["tool_sequence"], [])
        args = self.query_args(self.chat("不要高铁，查机票"))
        self.assertEqual((args["kind"],args["seat_type"]), ("机票","经济舱"))
        self.assertEqual(self.query_args(self.chat("不要机票，还是高铁"))["kind"], "高铁")

    def test_def03_sold_out_is_explicit_without_extra_tool_calls(self):
        result = self.chat("帮我查明天北京到上海的高铁二等座")
        self.assertEqual(result["tool_sequence"], ["query_tickets"])
        self.assertIn("二等座已售罄", result["reply"])
        self.assertIn("一等座", result["reply"])
        self.assertIn("尚未查询", result["reply"])
        self.assertNotIn("为您查到", result["reply"])

    def test_def03_available_and_no_match_are_distinct(self):
        self.assertIn("有余票", self.chat("查明天上海到杭州的高铁")["reply"])
        empty = self.chat("查明天上海到成都的高铁", sid="empty")
        self.assertIn("没有符合条件", empty["reply"])
        self.assertNotIn("已售罄", empty["reply"])

    def test_def03_mixed_inventory_marks_unsellable_rows(self):
        with closing(sqlite3.connect(config.DB_PATH)) as conn, conn:
            conn.execute("UPDATE inventory SET seats_left=0 WHERE id=(SELECT id FROM inventory WHERE from_city='上海' AND to_city='杭州' AND date='2026-10-14' AND seat_type='二等座' LIMIT 1)")
        reply = self.chat("查明天上海到杭州的高铁")["reply"]
        self.assertIn("有余票", reply)
        self.assertIn("余票 0（不可售）", reply)

    def test_def04_duplicate_payment_explains_idempotency(self):
        self.chat("帮我查明天上海到杭州的高铁")
        self.chat("我要买一张")
        with closing(sqlite3.connect(config.DB_PATH)) as conn:
            inventory_before = conn.execute("SELECT SUM(seats_left) FROM inventory").fetchone()[0]
        first = self.chat("支付")
        duplicate = self.chat("支付")
        self.assertIn("支付成功", first["reply"])
        self.assertIn("订单已支付，本次没有重复扣款", duplicate["reply"])
        self.assertNotIn("支付成功", duplicate["reply"])
        self.assertEqual(duplicate["tool_sequence"], ["pay_order"])
        call = duplicate["steps"][0]["calls"][0]
        self.assertTrue(call["ok"])
        self.assertTrue(json.loads(call["result_preview"])["duplicate_pay"])
        with closing(sqlite3.connect(config.DB_PATH)) as conn:
            self.assertEqual(conn.execute("SELECT SUM(seats_left) FROM inventory").fetchone()[0], inventory_before)
            self.assertEqual(conn.execute("SELECT status FROM orders").fetchall(), [("paid",)])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
