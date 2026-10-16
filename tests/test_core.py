"""成员 A 的实现自测，不是成员 B 的正式比赛断言平台。"""
import unittest
import tempfile
import sqlite3
from contextlib import closing
from pathlib import Path
from datetime import timedelta
import config
from data.seed import build_db
from target import tools, mock_core


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.DB_PATH
        config.DB_PATH = Path(self.tmp.name) / "test.db"
        build_db()
        self.day = (config.today() + timedelta(days=1)).isoformat()
        self.row = tools.dispatch("query_tickets", dict(from_city="上海", to_city="杭州", date=self.day, seat_type="二等座"))[0]["trains"][0]

    def tearDown(self):
        config.DB_PATH = self.old
        mock_core.clear_faults()
        self.tmp.cleanup()

    def invoke(self, name, **args):
        return tools.dispatch(name, args)[0]

    def lock(self):
        return self.invoke("lock_seat", train_no=self.row["train_no"], date=self.day, seat_type="二等座", passengers=["张三", "李四"])

    def order(self):
        lock = self.lock()
        return self.invoke("create_order", lock_id=lock["lock_id"], passenger_ids=["张三", "李四"], contact=config.CURRENT_USER_PHONE)

    def seats(self):
        rows = self.invoke("query_tickets", from_city="上海", to_city="杭州", date=self.day, seat_type="二等座")["trains"]
        return next(r["seats_left"] for r in rows if r["train_no"] == self.row["train_no"])

    def test_order_idempotency_refund_and_inventory(self):
        before = self.seats()
        order = self.order()
        again = self.invoke("create_order", lock_id=order["lock_id"], passenger_ids=["张三", "李四"], contact=config.CURRENT_USER_PHONE)
        self.assertEqual(order["order_id"], again["order_id"])
        self.assertEqual(self.seats(), before - 2)
        self.assertEqual(self.invoke("pay_order", order_id=order["order_id"])["status"], "paid")
        self.assertTrue(self.invoke("pay_order", order_id=order["order_id"])["duplicate_pay"])
        self.assertEqual(self.invoke("cancel_order", order_id=order["order_id"])["status"], "refunded")
        self.assertEqual(self.seats(), before)
        self.assertIn("error", self.invoke("cancel_order", order_id=order["order_id"]))
        self.assertIn("error", self.invoke("pay_order", order_id=order["order_id"]))
        self.assertEqual(self.seats(), before)

    def test_pending_cancel_and_expiration(self):
        before = self.seats()
        order = self.order()
        self.assertEqual(self.invoke("cancel_order", order_id=order["order_id"])["status"], "cancelled")
        self.assertEqual(self.seats(), before)
        order = self.order()
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            c.execute("UPDATE locks SET expire_at='2000-01-01T00:00:00'")
        self.assertIn("error", self.invoke("pay_order", order_id=order["order_id"]))
        self.assertEqual(self.seats(), before)
        self.assertEqual(self.invoke("query_order", order_id=order["order_id"])["status"], "expired")
        self.assertEqual(self.seats(), before)

    def test_authorization_and_passenger_match(self):
        lock = self.lock()
        self.assertIn("error", self.invoke("create_order", lock_id=lock["lock_id"], passenger_ids=["张三"], contact=config.CURRENT_USER_PHONE))
        order = self.order()
        with closing(sqlite3.connect(config.DB_PATH)) as c, c:
            c.execute("UPDATE orders SET phone=? WHERE order_id=?", (config.OTHER_USER_PHONE, order["order_id"]))
        for name in ("query_order", "pay_order", "cancel_order"):
            self.assertIn("error", self.invoke(name, order_id=order["order_id"]))
        self.assertIn("error", self.invoke("query_order", phone=config.OTHER_USER_PHONE))

    def test_schema_fault_and_monitor_seat(self):
        for args in ({}, {"from_city":"上海", "to_city":"杭州", "date":"2026-02-30"}):
            self.assertFalse(tools.dispatch("query_tickets", args)[1])
        self.assertFalse(tools.dispatch("__dict__", {})[1])
        self.assertFalse(tools.dispatch("lock_seat", dict(train_no="G101", date=self.day, seat_type="二等座", passengers=[]))[1])
        self.assertIn("task_id", self.invoke("monitor_seat", train_no="G101", date=self.day, seat_type="二等座"))
        self.assertIn("error", self.invoke("monitor_seat", train_no="missing", date=self.day, seat_type="二等座"))
        self.assertIn("error", self.invoke("monitor_seat", train_no=self.row["train_no"], date=self.day, seat_type="二等座"))
        mock_core.set_fault("query_tickets", "timeout")
        self.assertFalse(tools.dispatch("query_tickets", dict(from_city="上海", to_city="杭州", date=self.day))[1])


if __name__ == "__main__":
    unittest.main()
