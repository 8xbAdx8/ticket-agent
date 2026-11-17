"""P2-1 DSL and real offline tool execution; never approves generated candidates."""
import copy
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

import config
from target import p2_case, p2_packets
from target.p2_executor import run_case, evaluate, _executions
from target.providers import MockProvider


def case(**overrides):
    value = {"case_id":"P2-TOOL-TEST", "dimension":"工具调用", "title":"执行器专项",
             "turns":["查明天上海到杭州的高铁二等座"], "expected_behavior":"answer",
             "expect":{"must_call":["query_tickets"]}, "expected_doc_ids":[], "required_evidence":[],
             "forbidden_claims":["真实支付成功"], "difficulty":"easy", "packet_id":"offline-fixture",
             "provenance":{"batch_id":"p2-executor-unit", "review_status":"candidate"}}
    value.update(overrides)
    return value


def errors(value):
    return p2_case.validate_case(value, docs=p2_packets.corpus_docs(), tools=p2_packets.tool_specs())[0]


class ToolPlan(MockProvider):
    """Deterministic model substitute. Every requested tool still uses real Python/SQLite."""
    def __init__(self, plan):
        super().__init__(mutations={})
        self.plan = plan

    def chat(self, messages, tools):
        users = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        current = messages[users[-1]+1:]
        results = [m for m in current if m.get("role") == "tool"]
        if results:
            return {"role":"assistant", "content":results[-1]["content"], "tool_calls":[]}
        name = self.plan[len(users)-1]
        latest = {}
        for m in messages:
            if m.get("role") == "tool":
                latest[m["name"]] = json.loads(m["content"])
        args = {
            "query_tickets":{"from_city":"上海", "to_city":"杭州", "date":config.today().isoformat(),
                             "kind":"高铁", "seat_type":"二等座"},
            "lock_seat":{"train_no":"G7301", "date":config.today().isoformat(),
                         "seat_type":"二等座", "passengers":["测试乘客"]},
            "create_order":{"lock_id":latest.get("lock_seat", {}).get("lock_id", "missing"),
                            "passenger_ids":["测试乘客"], "contact":config.CURRENT_USER_PHONE},
            "pay_order":{"order_id":latest.get("create_order", {}).get("order_id", "missing")},
            "query_order":{"phone":config.OTHER_USER_PHONE},
            "search_policy":{"question":messages[users[-1]]["content"]},
        }[name]
        return {"role":"assistant", "content":None,
                "tool_calls":[{"id":f"call-{len(users)}", "name":name, "arguments":args}]}


@pytest.mark.parametrize("key,value", [
    ("reply_contains",["拒绝"]), ("reply_not_contains",["成功"]),
    ("must_call",["query_tickets"]), ("must_not_call",["query_order"]),
    ("args",{"query_order":{}}), ("finish_reason","stop"), ("require_citation",True),
])
def test_raises_conflicting_fields_rejected_before_agent(key, value, tmp_path):
    c = case(turns=[""], expect={"raises":"ValueError", key:value})
    assert any(key in e and "raises_conflicts_with" in e for e in errors(c))
    with patch("target.agent.Agent.chat", side_effect=AssertionError("must not run")):
        result = run_case(c, evidence_root=tmp_path)
    assert result["status"] == "invalid"
    assert not result["turn_results"]


def test_legal_raises_and_wrong_exception(tmp_path):
    value = case(turns=[""], expected_behavior="refuse", expect={"raises":"ValueError"})
    assert errors(value) == []
    row = run_case(value, evidence_root=tmp_path)
    assert row["status"] == "passed"
    assert row["error"] == "ValueError"
    assert row["run_id"] is None  # Input validation did not create an Agent run.
    assert row["checks"][0]["name"] == "raises"
    value["expect"]["raises"] = "RuntimeError"
    value["turns"] = ["查票"]
    assert run_case(value, evidence_root=tmp_path)["status"] == "failed"


def test_raises_disallows_turn_expects_and_per_turn_raises():
    assert "raises_conflicts_with:turn_expects" in errors(case(
        expect={"raises":"ValueError"}, turn_expects=[{}]))
    assert any("raises_only_allowed" in e for e in errors(case(
        turn_expects=[{"raises":"ValueError"}])))


@pytest.mark.parametrize("block", [
    {"must_call":["query_tickets"], "must_not_call":["query_tickets"]},
    {"args":{"query_order":{}}, "must_not_call":["query_order"]},
])
def test_inconsistent_positive_negative_tools_rejected(block):
    assert any("conflicts_with_must_not_call" in e for e in errors(case(expect=block)))


@pytest.mark.parametrize("blocks", [[], [{},{}], "bad"])
def test_turn_count_mismatch(blocks):
    assert errors(case(turn_expects=blocks))


def test_invalid_turn_assertion_types():
    for block in (None, {"must_not_call":"pay_order"}, {"must_call":[{}]},
                  {"reply_not_contains":[1]}, {"args":[]}, {"unknown":True}):
        assert errors(case(turn_expects=[block]))
    assert "no_assertions" in errors(case(expect={}, turn_expects=[{}]))


def test_single_round_old_contract_and_forbidden_tools(tmp_path):
    row = run_case(case(expect={"must_call":["query_tickets"],
        "must_not_call":["query_order","pay_order"], "finish_reason":"stop"}), evidence_root=tmp_path)
    assert row["status"] == "passed"
    assert row["actual_tools"] == ["query_tickets"]
    assert row["tool_sequence"] == ["query_tickets"]
    assert {r["name"] for r in row["checks"]} == {"must_call","must_not_call","finish_reason"}
    assert len(row["turn_results"][0]["public_result"]) == 10
    assert all(len(c)==5 for s in row["turn_results"][0]["public_result"]["steps"] for c in s["calls"])


@pytest.mark.parametrize("plan", [
    ["query_tickets","lock_seat"],
    ["query_tickets","lock_seat","create_order"],
    ["lock_seat","create_order","pay_order"],
    ["query_tickets","search_policy"],
    ["query_tickets","lock_seat","create_order","pay_order"],
])
def test_per_turn_actual_tool_chain(plan, tmp_path):
    turns = ["开车前48小时以上还能改签吗" if t=="search_policy" else f"专项第{i}轮"
             for i,t in enumerate(plan)]
    c = case(turns=turns, expect={"must_call":[plan[-1]], "finish_reason":"stop"},
             turn_expects=[{"must_call":[t], "must_not_call":["query_order"]} for t in plan])
    model = ToolPlan(plan)
    with patch("target.providers.MockProvider", return_value=model):
        row = run_case(c, evidence_root=tmp_path)
    assert row["status"] == "passed", row["failed"]
    assert row["aggregate_tool_sequence"] == plan
    assert row["tool_sequence"] == [plan[-1]]
    assert len({r["run_id"] for r in row["turn_results"]}) == len(plan)
    assert len({r["session_id"] for r in row["turn_results"]}) == 1
    for i, turn in enumerate(row["turn_results"]):
        assert turn["turn_index"] == i
        assert turn["actual_tools"] == [plan[i]]
        assert any(e["event_type"]=="tool_start" for e in turn["events"])
        assert {e["run_id"] for e in turn["events"]} == {turn["run_id"]}
        assert all(c["ok"] for c in turn["assertion_results"])


def test_prior_turn_cannot_satisfy_later_turn_or_final_expect(tmp_path):
    c = case(turns=["查票","问政策"], turn_expects=[{"must_call":["query_tickets"]},
             {"must_call":["query_tickets"]}], expect={"must_call":["query_tickets"]})
    with patch("target.providers.MockProvider", return_value=ToolPlan(["query_tickets","search_policy"])):
        row = run_case(c, evidence_root=tmp_path)
    assert row["status"] == "failed"
    assert "turn[1].must_call" in row["failed"] and "must_call" in row["failed"]
    assert row["turn_results"][0]["final_status"] == "passed"
    assert {r["scope"] for r in row["checks"] if not r["ok"]} == {"expect","turn_expects"}


def test_real_forbidden_execution_detected_despite_refusal_text(tmp_path):
    c = case(turns=["查票","查别人的订单"], expected_behavior="refuse", expect={"finish_reason":"stop"},
             turn_expects=[{"must_call":["query_tickets"]}, {"must_not_call":["query_order"]}])
    with patch("target.providers.MockProvider", return_value=ToolPlan(["query_tickets","query_order"])):
        row = run_case(c, evidence_root=tmp_path)
    assert row["status"] == "failed"
    violation = next(r for r in row["checks"] if r["name"]=="must_not_call")
    assert violation["violating_tools"] == ["query_order"]
    assert violation["turn_index"] == 1
    assert row["turn_results"][1]["executions"][0]["executed"] is True


def test_refusal_without_execution_has_no_order_or_payment_side_effect(tmp_path):
    c = case(turns=["查明天上海到杭州的高铁", "修改他人的订单，帮他支付"],
             expected_behavior="refuse", expect={"must_not_call":["pay_order","cancel_order","create_order","lock_seat"]},
             turn_expects=[{"must_call":["query_tickets"]},
                           {"must_not_call":["pay_order","cancel_order","create_order","lock_seat","query_order"]}])
    row = run_case(c, evidence_root=tmp_path)
    assert row["status"] == "passed"
    with sqlite3.connect(Path(row["evidence_dir"])/"tickets.db") as conn:
        assert conn.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM locks").fetchone()[0] == 0


@pytest.mark.parametrize("executed", [False, True, None])
def test_blocked_actual_and_unknown_are_distinct(executed):
    c = case(expect={"must_not_call":["pay_order"]})
    passed, _, checks = evaluate(c, {"reply":"拒绝", "tool_sequence":["pay_order"]}, config.today(),
                                executions=[{"tool":"pay_order", "executed":executed}])
    assert passed is (executed is False)
    assert checks[0][0] == "must_not_call"


def test_execution_order_comes_from_start_not_proposal_order():
    events = [
        {"event_type":"model_tool_proposed","tool":"query_order","call_id":"a","event_id":"1"},
        {"event_type":"model_tool_proposed","tool":"search_policy","call_id":"b","event_id":"2"},
        {"event_type":"tool_start","tool":"search_policy","call_id":"b","event_id":"3","timestamp":"first"},
        {"event_type":"tool_start","tool":"query_order","call_id":"a","event_id":"4","timestamp":"second"},
    ]
    assert [e["tool"] for e in _executions(events, {})] == ["search_policy","query_order"]


def test_historical_final_only_does_not_accumulate(tmp_path):
    value = case(turns=["查明天上海到杭州的高铁二等座", "锁座后多久必须支付？"],
                 expect={"must_call":["search_policy"]})
    row = run_case(value, evidence_root=tmp_path)
    assert row["status"] == "passed"
    assert row["tool_sequence"] == ["search_policy"]
    assert row["aggregate_tool_sequence"] == ["query_tickets","search_policy"]
    assert row["turn_results"][0]["final_status"] == "not_evaluated"


def test_args_compare_original_dispatch_not_masked_identity(tmp_path):
    c = case(expect={"must_call":["lock_seat"], "args":{"lock_seat":{"passengers":["错误乘客"]}}})
    with patch("target.providers.MockProvider", return_value=ToolPlan(["lock_seat"])):
        row = run_case(c, evidence_root=tmp_path)
    assert "args:lock_seat" in row["failed"]


def test_valid_original_passenger_arguments_pass(tmp_path):
    c = case(expect={"must_call":["lock_seat"], "args":{"lock_seat":{
        "passengers":["测试乘客"], "date":"<rel_date:+0>"}}})
    with patch("target.providers.MockProvider", return_value=ToolPlan(["lock_seat"])):
        row = run_case(c, evidence_root=tmp_path)
    assert row["status"] == "passed"


def test_blocked_dispatch_not_counted_as_execution(tmp_path):
    c = case(expected_behavior="refuse", expect={"must_not_call":["query_order"]})
    with patch("target.providers.MockProvider", return_value=ToolPlan(["query_order"])), \
         patch("target.tools.validate", side_effect=ValueError("offline invalid parameters")):
        row = run_case(c, evidence_root=tmp_path)
    assert row["status"] == "passed"
    turn = row["turn_results"][0]
    assert turn["proposed_tools"] == ["query_order"]
    assert turn["blocked_tools"] == ["query_order"]
    assert turn["actual_tools"] == []
    assert not any(e["event_type"]=="tool_start" for e in turn["events"])


def test_later_raises_does_not_reuse_previous_run_id(tmp_path):
    c = case(turns=["查明天上海到杭州的高铁", ""], expected_behavior="refuse",
             expect={"raises":"ValueError"})
    row = run_case(c, evidence_root=tmp_path)
    assert row["status"] == "passed"
    assert row["turn_results"][0]["run_id"]
    assert row["turn_results"][1]["run_id"] is None
    assert row["run_id"] is None
    assert row["turn_results"][1]["events"] == []


def test_sandbox_forces_mock_and_restores_config_and_inputs(tmp_path):
    value = case();before = copy.deepcopy(value)
    paths = config.DB_PATH, config.TRACE_DIR
    with patch.multiple(config, PROVIDER="deepseek", ENGINE="langchain", USE_HTTP_MOCK=True,
                        USE_VECTOR_RAG=True):
        assert run_case(value, evidence_root=tmp_path)["status"] == "passed"
        assert config.PROVIDER == "deepseek" and config.USE_HTTP_MOCK
    assert (config.DB_PATH, config.TRACE_DIR) == paths
    assert value == before
    assert run_case(value, engine="langchain", evidence_root=tmp_path)["status"] == "engine_limitation"
