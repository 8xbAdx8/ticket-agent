"""LangSmith developer panel: status mapping, receipt merge, no auto upload."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from web.langsmith_panel import classify, receipts_for


def receipt(**overrides):
    row = {"local_trace_id": "t1", "remote_run_id": "r1", "remote_status": "accepted_unverified",
           "post_http_status": 202, "http_requests": 1, "upload_attempts": 1,
           "timestamp": "2026-10-30T00:00:00+00:00"}
    row.update(overrides)
    return row


class StatusTests(unittest.TestCase):
    def test_no_receipt_is_not_uploaded(self):
        self.assertEqual(classify(None)["key"], "not_uploaded")

    def test_202_is_never_success(self):
        state = classify(receipt())
        self.assertEqual(state["key"], "accepted_pending")
        self.assertNotEqual(state["label"], "已验证")
        self.assertIn("202", state["detail"])

    def test_404_after_202_is_pending_not_upload_failure(self):
        state = classify(receipt(remote_status="failed", get_http_status=404,
                                 error={"category": "run_not_readable", "http_status": 404}))
        self.assertEqual(state["key"], "accepted_pending")
        self.assertNotEqual(state["label"], "上传失败")

    def test_404_without_upload_is_not_upload_failure_either(self):
        state = classify(receipt(remote_status="failed", post_http_status=None, get_http_status=404,
                                 error={"category": "run_not_readable", "http_status": 404}))
        self.assertNotEqual(state["label"], "上传失败")

    def test_500_on_post_is_upload_failure(self):
        state = classify(receipt(remote_status="failed", post_http_status=500, get_http_status=None,
                                 error={"category": "remote_server_error", "http_status": 500}))
        self.assertEqual(state["key"], "upload_failed")

    def test_read_error_after_accepted_upload_is_verify_failure(self):
        state = classify(receipt(remote_status="pending_verification", get_http_status=500))
        self.assertEqual(state["key"], "verify_failed")

    def test_verified(self):
        self.assertEqual(classify(receipt(remote_status="verified", get_http_status=200))["key"], "verified")

    def test_unknown_outcome_is_uploading(self):
        self.assertEqual(classify(receipt(remote_status="upload_outcome_unknown", post_http_status=None))["key"], "uploading")

    def test_429_is_still_pending(self):
        self.assertEqual(classify(receipt(remote_status="pending_verification", get_http_status=429))["key"],
                         "accepted_pending")


class ReceiptMergeTests(unittest.TestCase):
    def test_readback_keeps_upload_count_and_overrides_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            traces = Path(tmp) / "traces"
            traces.mkdir()
            export = receipt(remote_status="failed", get_http_status=404,
                             timestamp="2026-10-30T00:00:00+00:00", http_requests=3)
            readback = receipt(remote_status="verified", get_http_status=200,
                               timestamp="2026-10-30T00:10:00+00:00",
                               upload_attempts=0, http_requests=1, action="readback_only")
            (traces / "langsmith_exports.jsonl").write_text(json.dumps(export) + "\n", encoding="utf-8")
            (traces / "langsmith_readbacks.jsonl").write_text(json.dumps(readback) + "\n", encoding="utf-8")
            session = SimpleNamespace(trace_dir=traces)
            rows = receipts_for(session, "t1")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["remote_status"], "verified")
            self.assertEqual(rows[0]["upload_attempts"], 1)
            self.assertEqual(rows[0]["http_requests"], 3)

    def test_filter_by_trace_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            traces = Path(tmp) / "traces"
            traces.mkdir()
            rows = [receipt(remote_run_id="a", local_trace_id="t1"),
                    receipt(remote_run_id="b", local_trace_id="t2")]
            (traces / "langsmith_exports.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            found = receipts_for(SimpleNamespace(trace_dir=traces), "t2")
            self.assertEqual([row["remote_run_id"] for row in found], ["b"])


if __name__ == "__main__":
    unittest.main()
