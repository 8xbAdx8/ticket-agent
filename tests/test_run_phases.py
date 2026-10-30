"""Run phases must come from recorded events, never from inference."""
import json
import tempfile
import unittest
from pathlib import Path

from web import run_view


def event(kind, status="recorded", **fields):
    return {"event_type": kind, "status": status, **fields}


class PhaseStateTests(unittest.TestCase):
    def test_no_events_is_unknown_not_success(self):
        states = run_view.phase_states([])
        self.assertEqual([s["key"] for s in states], ["query", "policy", "confirm", "execute", "done"])
        self.assertTrue(all(s["status"] == "unknown" for s in states))

    def test_query_success_marks_only_its_own_phases(self):
        states = run_view.phase_states([
            event("tool_result", "succeeded", tool="query_tickets", duration_ms=4),
            event("agent_returned", finish_reason="stop"),
        ])
        by_key = {s["key"]: s for s in states}
        self.assertEqual(by_key["query"]["status"], "done")
        self.assertIn("4 ms", by_key["query"]["detail"])
        self.assertEqual(by_key["policy"]["status"], "pending")
        self.assertEqual(by_key["confirm"]["status"], "pending")
        self.assertEqual(by_key["done"]["status"], "done")

    def test_failed_tool_marks_the_run_failed(self):
        states = run_view.phase_states([
            event("tool_result", "failed", tool="query_tickets", duration_ms=2),
            event("agent_returned", finish_reason="stop"),
        ])
        by_key = {s["key"]: s for s in states}
        self.assertEqual(by_key["query"]["status"], "failed")
        self.assertEqual(by_key["done"]["status"], "failed")
        self.assertNotEqual(by_key["done"]["status"], "done")

    def test_confirmation_waiting_then_approved(self):
        waiting = {s["key"]: s for s in run_view.phase_states([
            event("confirmation_requested", tool="create_order", args={})])}
        self.assertEqual(waiting["confirm"]["status"], "waiting")
        self.assertEqual(waiting["execute"]["status"], "pending")
        approved = {s["key"]: s for s in run_view.phase_states([
            event("confirmation_requested", tool="create_order", args={}),
            event("operation_resumed", "approved"),
            event("tool_result", "succeeded", tool="create_order", duration_ms=6),
        ])}
        self.assertEqual(approved["confirm"]["status"], "done")
        self.assertEqual(approved["execute"]["status"], "done")

    def test_declined_confirmation_is_not_execution(self):
        states = {s["key"]: s for s in run_view.phase_states([
            event("confirmation_requested", tool="pay_order", args={}),
            event("operation_resumed", "declined"),
        ])}
        self.assertEqual(states["confirm"]["status"], "declined")
        self.assertEqual(states["execute"]["status"], "pending")


class EventSourceTests(unittest.TestCase):
    def test_load_events_keeps_only_the_requested_run_id(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "run_events.jsonl"
            rows = [{"run_id": "run-a", "event_type": "tool_result", "tool": "query_tickets"},
                    {"run_id": "run-b", "event_type": "tool_result", "tool": "search_policy"},
                    {"run_id": "run-a", "event_type": "agent_returned"}]
            path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            events, meta = run_view.load_events(folder, "run-a")
        self.assertEqual([e["event_type"] for e in events], ["tool_result", "agent_returned"])
        self.assertFalse(meta["missing"])

    def test_missing_event_file_is_reported_not_invented(self):
        with tempfile.TemporaryDirectory() as folder:
            events, meta = run_view.load_events(folder, "run-x")
        self.assertEqual(events, [])
        self.assertTrue(meta["missing"])

    def test_call_rows_use_recorded_status_and_latency(self):
        rows = run_view.call_rows([
            event("tool_result", "succeeded", tool="query_tickets", duration_ms=11),
            event("tool_result", "blocked", tool="create_order", duration_ms=None),
        ])
        self.assertEqual([r["status"] for r in rows], ["done", "blocked"])
        self.assertEqual(rows[0]["duration"], "11 ms")
        self.assertEqual(rows[1]["duration"], "未记录")


class EventCardTests(unittest.TestCase):
    def test_headline_puts_name_status_tool_and_duration_first(self):
        headline = run_view.event_headline(
            event("tool_result", "succeeded", tool="query_tickets", duration_ms=7))
        self.assertIn("工具返回", headline)
        self.assertIn("查询余票", headline)
        self.assertIn("7 ms", headline)

    def test_summary_shows_recorded_fields_only(self):
        rows = dict(run_view.event_summary(
            event("tool_result", "failed", tool="pay_order", duration_ms=3,
                  output={"error": "订单不存在"}, timestamp="2026-10-30T00:00:00+00:00")))
        self.assertEqual(rows["工具"], "支付订单")
        self.assertEqual(rows["耗时"], "3 ms")
        self.assertIn("订单不存在", rows["结果摘要"])
        self.assertEqual(rows["参数摘要"], "未记录")
        self.assertEqual(rows["时间"], "2026-10-30T00:00:00+00:00")

    def test_summary_marks_missing_duration_instead_of_inventing_one(self):
        rows = dict(run_view.event_summary(event("agent_returned", reply="ok")))
        self.assertEqual(rows["耗时"], "未记录")
        self.assertEqual(rows["结果摘要"], "ok")

    def test_card_escapes_untrusted_values(self):
        markup = run_view.event_card(event("tool_result", "failed", tool="x",
                                          output={"error": "<img src=x>"}))
        self.assertNotIn("<img", markup)
        self.assertIn("&lt;img", markup)


class MarkupTests(unittest.TestCase):
    def test_strip_escapes_recorded_detail(self):
        states = run_view.phase_states([
            event("confirmation_requested", tool="<script>", args={}),
            event("agent_error", "failed", error="<img onerror=x>"),
        ])
        markup = run_view.phase_strip(states)
        self.assertNotIn("<script>", markup)
        self.assertNotIn("<img", markup)
        self.assertIn("&lt;script&gt;", markup)

    def test_unknown_looking_status_is_not_labelled_success(self):
        markup = run_view.phase_strip([{"key": "query", "label": "查票", "status": "unknown", "detail": ""}])
        self.assertIn("未记录", markup)
        self.assertNotIn("已完成", markup)


if __name__ == "__main__":
    unittest.main()
