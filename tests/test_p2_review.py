"""Review channel tests: approve/reject/edit, human gate, illegality, load gating."""
import json
from pathlib import Path

import pytest

from target import p2_review
from target.p2_executor import run_case
from target.p2_store import Batch

QUOTE = "开车前 48 小时以上退票，收取票价 5% 手续费"


def valid_case(case_id="P2-RAG-0001", **overrides):
    case = {
        "schema": "ticket-p2-scenario/1",
        "case_id": case_id,
        "dimension": "RAG",
        "title": "退票手续费阶梯",
        "turns": ["开车前三天退票，手续费是多少？"],
        "expected_behavior": "answer",
        "expect": {"must_call": ["search_policy"], "reply_contains": ["5%"],
                   "require_citation": True, "finish_reason": "stop"},
        "expected_doc_ids": ["P01"],
        "required_evidence": [{"doc_id": "P01", "quote": QUOTE}],
        "forbidden_claims": ["真实退款已到账"],
        "difficulty": "easy",
        "packet_id": "ev-test",
        "provenance": {"origin": "ai_generated", "batch_id": "p2-test", "provider": "deepseek",
                       "model": "deepseek-flash", "prompt_sha256": "p", "response_sha256": "r",
                       "request_id": "req-1", "review_status": "candidate"},
    }
    case.update(overrides)
    return case


def make_batch(tmp_path, cases):
    root = tmp_path / "p2-gen"
    batch = Batch("p2-test", root=root)
    for case in cases:
        batch.append(case)
    batch.save_manifest(generated=len(cases))
    return batch, root


def approve(tmp_path, root, case_id="P2-RAG-0001", reviewer="张三", reason="依据充分"):
    return p2_review.review_case("p2-test", case_id, "approve", reviewer, reason=reason,
                                 batch_root=root, approved_dir=tmp_path / "approved")


def test_approve_publishes_and_loads_with_evidence(tmp_path):
    _, root = make_batch(tmp_path, [valid_case()])
    record = approve(tmp_path, root)
    assert record["decision"] == "approve"
    approved_file = tmp_path / "approved" / "p2-test.jsonl"
    assert approved_file.is_file()
    cases, rejected = p2_review.load_approved(tmp_path / "approved")
    assert rejected == []
    assert len(cases) == 1
    row = cases[0]
    assert row["review"]["reviewer"] == "张三"
    assert row["review"]["reviewed_utc"]
    assert row["provenance"]["batch_id"] == "p2-test"
    assert row["provenance"]["request_id"] == "req-1"


def test_reject_and_unreviewed_are_not_loaded(tmp_path):
    _, root = make_batch(tmp_path, [valid_case("P2-RAG-0001"), valid_case("P2-RAG-0002")])
    p2_review.review_case("p2-test", "P2-RAG-0001", "reject", "张三", reason="期望不可判定",
                          batch_root=root, approved_dir=tmp_path / "approved")
    cases, _ = p2_review.load_approved(tmp_path / "approved")
    assert cases == []


@pytest.mark.parametrize("reviewer", ["AI", "system", "auto", "deepseek", "codex", "a"])
def test_non_human_reviewer_rejected(tmp_path, reviewer):
    _, root = make_batch(tmp_path, [valid_case()])
    with pytest.raises(ValueError, match="human_reviewer_required"):
        approve(tmp_path, root, reviewer=reviewer)


def test_invalid_edit_is_recorded_but_cannot_be_approved(tmp_path):
    _, root = make_batch(tmp_path, [valid_case()])
    record = p2_review.review_case("p2-test", "P2-RAG-0001", "edit", "张三", reason="改错了",
                                   edited={"required_evidence": [{"doc_id": "P01", "quote": "这句话不在文档里"}]},
                                   batch_root=root, approved_dir=tmp_path / "approved")
    assert record["decision"] == "edit_invalid"
    assert "quote_not_verbatim:P01" in record["validation"]["errors"]
    with pytest.raises(ValueError, match="edit_invalid_pending"):
        approve(tmp_path, root)


def test_valid_edit_then_approve_uses_edited_version(tmp_path):
    _, root = make_batch(tmp_path, [valid_case()])
    edited = p2_review.review_case("p2-test", "P2-RAG-0001", "edit", "张三", reason="更准确",
                                   edited={"title": "退票 24-48 小时档"},
                                   batch_root=root, approved_dir=tmp_path / "approved")
    assert edited["validation"]["status"] == "valid"
    approve(tmp_path, root)
    cases, _ = p2_review.load_approved(tmp_path / "approved")
    assert cases[0]["title"] == "退票 24-48 小时档"
    assert cases[0]["provenance"]["edited"] is True


def test_illegal_namespace_and_rag1000_source_rejected_on_load(tmp_path):
    _, root = make_batch(tmp_path, [valid_case()])
    approve(tmp_path, root)
    path = tmp_path / "approved" / "p2-test.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    illegal = json.loads(json.dumps(rows[0]))
    illegal["case_id"] = "RAG-0001"
    rag = json.loads(json.dumps(rows[0]))
    rag["case_id"] = "P2-RAG-9999"
    rag["dataset_version"] = "rag1000-v1.1.1"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows + [illegal, rag]) + "\n",
                    encoding="utf-8")
    cases, rejected = p2_review.load_approved(tmp_path / "approved")
    assert [c["case_id"] for c in cases] == ["P2-RAG-0001"]
    reasons = {row["case_id"]: row["reason"] for row in rejected}
    assert reasons["RAG-0001"] == "not_p2_namespace"
    assert reasons["P2-RAG-9999"] == "rag1000_source"


def test_missing_review_time_rejected(tmp_path):
    _, root = make_batch(tmp_path, [valid_case()])
    approve(tmp_path, root)
    path = tmp_path / "approved" / "p2-test.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    row["review"]["reviewed_utc"] = ""
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    cases, rejected = p2_review.load_approved(tmp_path / "approved")
    assert cases == []
    assert rejected[0]["reason"] == "missing_review_time"


def test_sandbox_pass_alone_does_not_approve(tmp_path):
    _, root = make_batch(tmp_path, [valid_case("P2-RAG-0001",
                                               turns=["查明天上海到杭州的高铁二等座"],
                                               expected_behavior="answer", expected_doc_ids=[],
                                               required_evidence=[],
                                               expect={"must_call": ["query_tickets"], "finish_reason": "stop"})])
    row = run_case(valid_case("P2-RAG-0001", turns=["查明天上海到杭州的高铁二等座"],
                              expected_behavior="answer", expected_doc_ids=[], required_evidence=[],
                              expect={"must_call": ["query_tickets"], "finish_reason": "stop"}))
    assert row["status"] in ("passed", "failed")
    cases, _ = p2_review.load_approved(tmp_path / "approved")
    assert cases == []
