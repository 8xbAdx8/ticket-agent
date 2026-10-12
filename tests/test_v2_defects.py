"""成员 A 的缺陷修复回归：不替代 B 的 100 用例/xfail/正式统计。"""
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


if __name__ == "__main__":
    unittest.main()
