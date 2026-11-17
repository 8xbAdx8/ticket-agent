"""Keep D9 policy scope separate from historical retrieval and transaction claims."""
import pytest

from target.rag import _approved_policy_projection, search_policy
from target.rag_service import retrieve
from target.scenario_business_oracle import TABLES, reply_claims
from target.v39.context import Context, scope


QUESTION = "按项目示例条款，距离发车超过48小时退票的手续费比例是多少？"


def test_ui_routes_explicit_fee_lookup_to_chat_without_authorizing_a_refund():
    from web.runtime import operation_kind
    question = "按项目示例条款，请查明距离发车超过48小时退票的手续费比例，并引用条款编号。"
    assert operation_kind(question) is None
    assert operation_kind("查询距离发车少于24小时的退票费率") is None
    assert operation_kind(question.removesuffix("。") + "，然后帮我退票") == "模拟业务操作"
    assert operation_kind("帮我退票") == "模拟业务操作"


def test_railway_post_departure_policy_matches_service_and_keeps_source_immutable():
    from target.v39.policy import Policy
    hit = {"doc_id": "P03", "content": "开车后 2 小时内可办理一次改签至当日其他有余票车次，不退票。"}
    question = "开车后能改签吗？"
    with scope(Context("railway", "13800000001", "demo", enabled=True)):
        current = _approved_policy_projection(question, [hit])[0]
    assert current["content"].startswith("本地铁路模拟业务在原行程发车后不办理退票或改签。")
    assert current["doc_id"] == "P03"
    with pytest.raises(ValueError, match="REFUND_AFTER_DEPARTURE"):
        Policy().refund([3000], "2026-11-05T05:00:00+08:00", "2026-11-05T05:00:00+08:00", changed=True)
    assert _approved_policy_projection(question, [hit]) == [hit]
    assert "2 小时" in hit["content"]


@pytest.mark.parametrize("fetch", [search_policy, retrieve])
def test_generic_railway_refund_question_uses_d9_without_changing_baseline(fetch, monkeypatch):
    monkeypatch.delenv("AGENT_RAG_MODE", raising=False)
    with scope(Context("railway", "13800000001", "demo", enabled=True)):
        current = next(hit for hit in fetch(QUESTION)["hits"] if hit["doc_id"] == "P01")
    with scope(Context("baseline", "13800000001", "demo", enabled=True, execution_mode="baseline")):
        original = next(hit for hit in fetch(QUESTION)["hits"] if hit["doc_id"] == "P01")
    assert "5%" in current["content"]
    assert "改签后的车票仍可申请退票" in current["content"]
    assert current["policy_projection"] == "D9_CHANGED_REFUND_P01"
    assert "已改签的车票不退" in original["content"]
    assert "policy_projection" not in original


@pytest.mark.parametrize("text,status", [
    ("该条款还规定：已取报销凭证或已改签的车票不退。", "N/A"),
    ("附加限制：**已取报销凭证或已改签的车票不予退票**。", "N/A"),
    ("已改签的车票仍可申请退票。", "N/A"),
    ("系统已改签您的订单。", "FAIL"),
    ("已改签的车票不予退票。但您的订单改签成功。", "FAIL"),
    ("已改签的车票仍可申请退票且您的订单改签成功。", "FAIL"),
])
def test_policy_descriptions_are_not_transaction_success_claims(text, status):
    view = {"tables": {name: [] for name in TABLES}}
    assert reply_claims(text, view)["status"] == status
