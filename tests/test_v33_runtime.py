import shutil
import unittest
import uuid
from unittest.mock import patch
import config
from web.runtime import Conversation, operation_kind


class RuntimeTests(unittest.TestCase):
    def tearDown(self):
        for session in getattr(self,"sessions",[]):
            shutil.rmtree(session.root,ignore_errors=True)

    def conversation(self,mode="user",**kw):
        c=Conversation(mode,**kw)
        self.sessions=getattr(self,"sessions",[])+[c]
        return c

    def test_user_and_lab_databases_and_mutations_are_isolated(self):
        original=(config.DB_PATH,config.TRACE_DIR,config.PROVIDER)
        user=self.conversation()
        lab=self.conversation("lab",mutations={"hallucinated_train":True})
        r=lab.send("查明天上海到杭州的高铁",uuid.uuid4().hex)
        self.assertIn("G9999",r["reply"])
        normal=user.send("查明天上海到杭州的高铁",uuid.uuid4().hex)
        self.assertNotIn("G9999",normal["reply"])
        self.assertNotEqual(user.root,lab.root)
        self.assertEqual((config.DB_PATH,config.TRACE_DIR,config.PROVIDER),original)

    def test_duplicate_submission_does_not_reexecute(self):
        c=self.conversation()
        r=c.send("订明天上海到杭州的高铁","same-submit")
        self.assertIs(c.send("订明天上海到杭州的高铁","same-submit"),r)
        self.assertEqual(len(c.history),1)
        self.assertEqual(r["tool_sequence"],["query_tickets","lock_seat","create_order"])

    def test_live_preflight_cannot_fall_back_or_call_with_missing_key(self):
        c=self.conversation(live=True,engine="langchain")
        with patch("web.runtime.live_ready",return_value=False),patch("web.runtime.Agent") as agent:
            with self.assertRaises(ValueError):c.send("查票","id")
            agent.assert_not_called()
        self.assertFalse(c.root.exists())

    def test_user_rejects_mutation_and_m8_is_not_chat(self):
        with self.assertRaises(ValueError):Conversation("user",mutations={"date_offset":1})
        c=self.conversation("lab",mutations={"concurrent_duplicate_order":True})
        with self.assertRaises(ValueError):c.send("查票","id")

    def test_policy_question_is_not_a_payment_confirmation(self):
        self.assertIsNone(operation_kind("锁座后多久必须完成支付？"))
        self.assertIsNone(operation_kind("不要支付"))
        self.assertIsNotNone(operation_kind("支付我刚才的订单"))
        self.assertIsNotNone(operation_kind("订明天上海到杭州的高铁"))
