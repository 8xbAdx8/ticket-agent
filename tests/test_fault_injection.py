import unittest
from target.fault_injection import FaultRun, normalize, summarize


class FaultDefinitionTests(unittest.TestCase):
    def test_default_and_config_validation(self):
        self.assertEqual(normalize(),{})
        self.assertEqual(normalize({"date_offset":0,"repeat_call":False}),{})
        for config in ({"unknown":True},{"date_offset":True},{"date_offset":2},{"repeat_call":1},[]):
            with self.assertRaises(ValueError): normalize(config)

    def test_date_original_and_actual_are_independent(self):
        call={"id":"x","name":"query_tickets","args":{"date":"2026-10-18"}}
        run=FaultRun({"date_offset":1},"s","offline")
        actual=run.arguments(call,"")
        self.assertEqual(actual["args"]["date"],"2026-10-19")
        self.assertEqual(call["args"]["date"],"2026-10-18")
        self.assertEqual(run.events[0]["original"],call["args"])

    def test_invalid_date_fails_explicitly(self):
        run=FaultRun({"date_offset":1},"s","offline")
        with self.assertRaises(ValueError): run.arguments({"id":"x","name":"query_tickets","args":{"date":"bad"}},"")
        self.assertEqual(run.events[0]["status"],"failed")

    def test_route_means_policy_to_ticket_not_city_swap(self):
        run=FaultRun({"route_error":True},"s","offline")
        actual=run.arguments({"id":"x","name":"search_policy","args":{"question":"退票政策"}},"退票政策")
        self.assertEqual(actual["name"],"query_tickets")
        self.assertEqual(actual["args"]["from_city"],"北京")

    def test_citation_removed_from_real_result_without_mutating_original(self):
        result={"hits":[{"doc_id":"P11","source":"data/policies.md#P11","title":"规则","content":"见 P11"}],"count":1}
        run=FaultRun({"no_citation":True},"s","offline")
        changed=run.result("search_policy",result,"x")
        self.assertNotIn("doc_id",changed["hits"][0])
        self.assertIn("doc_id",result["hits"][0])
        self.assertEqual(run.events[0]["original"],result)

    def test_disabled_is_noop_and_runs_do_not_leak(self):
        call={"id":"x","name":"query_tickets","args":{"date":"2026-10-18"}}
        changed=FaultRun({"date_offset":1},"s","offline").arguments(call,"")
        self.assertNotEqual(changed,call)
        normal=FaultRun({},"s2","offline")
        self.assertEqual(normal.arguments(call,""),call)
        self.assertEqual(normal.events,[])

    def test_multiple_faults_have_fixed_order_and_untriggered_reason(self):
        run=FaultRun({"route_error":True,"date_offset":1,"no_citation":True},"s","offline")
        run.arguments({"id":"x","name":"search_policy","args":{"question":"政策"}},"政策")
        self.assertEqual([e["mutation"] for e in run.events],["route_error","date_offset"])
        last=run.report()["injection_events"][-1]
        self.assertEqual(last["status"],"not_triggered")
        self.assertTrue(last["reason"])

    def test_statistics_do_not_invent_agent_judgements(self):
        run=FaultRun({"date_offset":1,"skip_lock":True},"s","offline")
        run.emit("date_offset","2026-10-18","2026-10-19")
        run.emit("skip_lock",status="not_applicable",reason="只读模式")
        stats=summarize([run.report()])
        self.assertEqual(stats["counts"]["applied"],1)
        self.assertEqual(stats["counts"]["not_applicable"],1)
        self.assertEqual(stats["injection_success_rate"],1)
        self.assertIsNone(stats["agent_defect_detection_rate"])
        self.assertIsNone(stats["agent_recovery_rate"])
