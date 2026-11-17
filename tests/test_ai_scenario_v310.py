"""AI-native V3.10 DSL generation and semantic quality contracts."""
import copy
import json
import uuid
from pathlib import Path

import pytest


def store():
    from target.scenario_generator import Store
    root = Path("artifacts/runtime/ai-v310-contract-" + uuid.uuid4().hex[:10])
    return Store(root)


def test_v310_prompt_contract_uses_only_registered_tools():
    from target.scenario_generator import V310_SYSTEM, v310_contract
    from target.v39.registry import NAMES
    contract = v310_contract()
    assert contract["tools"] == list(NAMES)
    assert "railway_lock_seat" not in contract["tools"]
    assert "integration_steps" in V310_SYSTEM
    assert "actor:\"test_user\"" in V310_SYSTEM
    assert "P2" not in V310_SYSTEM


def test_v310_mock_generation_is_executable_by_v310_adapter():
    from target.scenario_generator import review
    s = store()
    result = s.generate("验证真实车次查询与分页", "业务状态一致性", "medium", 1, "Mock", adapter="v310")
    assert result["status"] == "SUCCEEDED", result
    row = s.list()[0]
    case = row["body"]
    assert case["execution_adapter"] == "v310"
    assert case["integration_steps"]
    assert review(case)["quality"] != "REJECTED"
    s.decide([(row["id"], row["revision"])], "APPROVED", "TEST_ONLY-contract")
    run = s.run(row["id"], row["revision"] + 1)
    assert run["status"] == "passed", run
    assert run["evidence_root"]
    assert run["steps"] and all(step["verified"] for step in run["steps"])


def test_quality_rejects_weak_structural_only_assertion():
    from target.scenario_generator import review
    case = {
        "case_id": "weak", "title": "weak", "objective": "weak", "category": "业务状态一致性",
        "difficulty": "easy", "turns": ["查询"], "conversation": ["查询"], "execution_adapter": "v310",
        "fixture_scenario": "default", "expect": {}, "assertions": {}, "expected_tool_calls": ["railway_query_trips"],
        "expected_state_changes": [], "turn_expects": [], "risk_level": "medium",
        "schema_version": "ticket-ai-scenario/1", "integration_steps": [{
            "kind": "tool", "tool": "railway_query_trips", "args": {"service_date": "2026-11-05", "origin_stop_id": "AOH", "destination_stop_id": "HGH"},
            "as": "trips", "checks": [{"path": "metrics.foreign_keys_ok", "op": "eq", "value": True}]}],
        "preconditions": [], "expected_call_order": [], "source_references": ["test"], "generation_model": "test", "prompt_version": "test", "created_at": "2026-11-10T00:00:00Z", "review_status": "PENDING",
    }
    result = review(case)
    assert result["quality"] == "REJECTED"
    assert any("business assertion" in e for e in result["errors"])


def test_quality_rejects_pay_without_trusted_confirmation():
    from target.scenario_generator import review
    case = {
        "case_id": "pay-weak", "title": "pay", "objective": "pay", "category": "业务状态一致性",
        "difficulty": "easy", "turns": ["支付"], "conversation": ["支付"], "execution_adapter": "v310",
        "fixture_scenario": "default", "expect": {}, "assertions": {}, "expected_tool_calls": ["railway_pay_order"],
        "expected_state_changes": [], "turn_expects": [], "risk_level": "medium",
        "schema_version": "ticket-ai-scenario/1", "integration_steps": [{
            "kind": "tool", "tool": "railway_pay_order", "args": {"order_id": "x", "expected_total_fen": 1},
            "as": "pay", "checks": [{"path": "result.status", "op": "eq", "value": "CONFIRMATION_REQUIRED"}]}],
        "preconditions": [], "expected_call_order": [], "source_references": ["test"], "generation_model": "test", "prompt_version": "test", "created_at": "2026-11-10T00:00:00Z", "review_status": "PENDING",
    }
    result = review(case)
    assert result["quality"] == "REJECTED"
    assert any("confirmation" in e for e in result["errors"])
