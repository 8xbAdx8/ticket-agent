import unittest
import tempfile
from pathlib import Path
import config
from data.seed import build_db
from streamlit.testing.v1 import AppTest


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db, self.trace = config.DB_PATH, config.TRACE_DIR
        config.DB_PATH = Path(self.tmp.name) / "test.db"
        config.TRACE_DIR = Path(self.tmp.name) / "trace"
        build_db()
        self.app = AppTest.from_file(str(config.BASE_DIR / "web" / "app.py"), default_timeout=20).run()

    def tearDown(self):
        config.DB_PATH, config.TRACE_DIR = self.db, self.trace
        self.tmp.cleanup()

    def button(self, label):
        return next(b for b in self.app.button if b.label == label)

    def send(self, msg):
        self.app.text_input[0].set_value(msg)
        self.button("发送").click().run()
        self.assertEqual(len(self.app.exception), 0)
        return self.app.session_state["history"][-1]

    def test_conversation_and_replay(self):
        self.assertEqual(self.send("订明天上海到杭州的高铁")["tool_sequence"], ["query_tickets", "lock_seat", "create_order"])
        self.assertEqual(self.send("支付")["tool_sequence"], ["pay_order"])
        self.assertEqual(self.send("帮我退掉")["tool_sequence"], ["cancel_order"])
        self.assertTrue(any(s.label == "选择回放记录" for s in self.app.selectbox))
        self.assertGreater(len(self.app.json), 0)

    def test_all_controls_and_restore(self):
        self.assertEqual(len(self.app.checkbox), 6)
        for box in self.app.checkbox:
            box.check()
        self.app.run()
        self.assertEqual(len(self.app.session_state["mutations"]), 6)
        self.button("恢复正常模式").click().run()
        self.assertEqual(dict(self.app.session_state["mutations"]), {})
        self.assertTrue(all(not b.value for b in self.app.checkbox))
        self.assertRegex(self.send("退票手续费怎么算")["reply"], r"P01")
        next(b for b in self.app.checkbox if b.label == "infinite_loop").check().run()
        self.assertEqual(self.send("抢明天北京到上海的票")["finish_reason"], "max_steps_exceeded")
        self.assertGreater(len(self.app.error), 0)


if __name__ == "__main__":
    unittest.main()
