import unittest
from web.trace_view import timeline_items
from web.integrations import observation_envelope,FutureModelConfig
from target.diagnostics import sanitize


class ObservationTests(unittest.TestCase):
    def test_only_actual_validation_events_are_added(self):
        audit={"fault_report":{"executions":[{"tool":"query_tickets","parameter_validation":{"status":"valid","validated_args":{"date":"2026-10-25"}}}]}}
        rows=timeline_items(audit)
        self.assertEqual([r["kind"] for r in rows],["参数校验旁证","实际执行"])
        self.assertEqual(timeline_items({}),[])

    def test_future_envelope_does_not_invent_graph_or_export_private_reasoning(self):
        envelope=observation_envelope({"trace_id":"id","fault_report":{"executions":[{"authorization":"secret","reasoning_content":"private"}]}})
        self.assertIsNone(envelope["graph"])
        self.assertFalse(envelope["external_export_enabled"])
        self.assertNotIn("private",str(envelope))
        self.assertNotIn("secret",str(envelope))
        self.assertEqual(FutureModelConfig().base_url_env,"BAILIAN_BASE_URL")
