"""Developer runs: mode classification and single-run evidence binding."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from web.developer_workspace import _results_for, _run_identity, _run_mode


def session(sid, audits, trace_dir=None):
    return SimpleNamespace(sid=sid, audits=audits, trace_dir=Path(trace_dir or tempfile.gettempdir()),
                           history=[], results=[])


class RunModeTests(unittest.TestCase):
    def test_debug_session_is_never_the_replayed_run(self):
        older = {"trace_id": "run-old"}
        newer = {"trace_id": "run-new"}
        user = session("web-a", [older])
        debug = session("web-b", [newer])
        self.assertEqual(_run_mode(debug, newer, [user], debug), "debug")
        # Without the debug session in scope the newest saved run is the current one.
        self.assertEqual(_run_mode(user, older, [user], None), "current")

    def test_only_the_newest_run_of_the_newest_session_is_current(self):
        first = {"trace_id": "run-1"}
        second = {"trace_id": "run-2"}
        old_session = session("web-old", [{"trace_id": "run-0"}])
        new_session = session("web-new", [first, second])
        sessions = [old_session, new_session]
        self.assertEqual(_run_mode(new_session, second, sessions, None), "current")
        self.assertEqual(_run_mode(new_session, first, sessions, None), "history")
        self.assertEqual(_run_mode(old_session, old_session.audits[0], sessions, None), "history")


class EvidenceBindingTests(unittest.TestCase):
    def test_results_are_taken_from_the_matching_history_record_only(self):
        public_a = {"user_msg": "A", "reply": "a"}
        public_b = {"user_msg": "B", "reply": "b"}
        target = session("web-a", [{"trace_id": "r1", "public_trace": public_b}])
        target.history = [public_a, public_b]
        target.results = [[{"tool": "query_tickets"}], [{"tool": "search_policy"}]]
        self.assertEqual(_results_for(target, {"public_trace": public_b}),
                         [{"tool": "search_policy"}])

    def test_identity_marks_missing_event_file_and_escapes_run_id(self):
        with tempfile.TemporaryDirectory() as folder:
            empty = session("web-a", [], folder)
            markup = _run_identity(empty, {"trace_id": "<b>run</b>"}, "history")
        self.assertIn("&lt;b&gt;run&lt;/b&gt;", markup)
        self.assertNotIn("<b>run</b>", markup)
        self.assertIn("无事件文件", markup)
        self.assertIn("历史回放", markup)

    def test_identity_reports_a_readable_event_file(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "run_events.jsonl").write_text("", encoding="utf-8")
            markup = _run_identity(session("web-a", [], folder), {"trace_id": "run-1"}, "current")
        self.assertIn("事件文件可读", markup)
        self.assertIn("当前运行", markup)


if __name__ == "__main__":
    unittest.main()
