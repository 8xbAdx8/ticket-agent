"""V3.9.4 default-use-case and query-reliability tests (development only).

These tests use the isolated SQLite namespace supplied by run_v39_tests and
never call a model provider or an external railway/payment service.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import os
import uuid

import pytest
import config

from target.baggage import calculate_baggage
from target.order_read_model import orders
from target.v39.context import Context, scope
from target.v39.policy import Policy
from target.v39.registry import dispatch, service_scope
from target.v39.static import RailwayStatic
from target.v39.service import Service
from target.v39.store import Store
from web import railway_defaults as defaults
from web.demo import (start_demo, _step_query, _step_order, _step_pay,
                      _step_order_query)
from web.runtime import Conversation


def _base():
    explicit = Path(os.environ.get("RAILWAY_SIM_DB_PATH", ""))
    if explicit.is_file() or explicit.suffix == ".sqlite":
        explicit = explicit.parent
    base = explicit if explicit.exists() else Path(__file__).resolve().parents[2] / "artifacts/runtime"
    # Keep every test inside an allowed v394-* namespace.
    return base / ("v394-test-" + uuid.uuid4().hex)


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("RAILWAY_SIMULATION_ENABLED", "1")
    root = _base()
    monkeypatch.setenv("RAILWAY_SIM_DB_PATH", str(root / "simulation.sqlite"))
    monkeypatch.setenv("AGENT_PROVIDER", "mock")
    s = Conversation("user", engine="legacy", live=False, root=root / "session")
    return s


@pytest.fixture
def prepared(session):
    return defaults.prepare(session)


@pytest.fixture
def demo_db(monkeypatch):
    monkeypatch.setenv("RAILWAY_SIMULATION_ENABLED", "1")
    root = _base()
    monkeypatch.setenv("RAILWAY_SIM_DB_PATH", str(root / "demo.sqlite"))
    return root / "demo.sqlite"


def _cdb(path):
    import sqlite3
    return sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)


# T077
def test_t077_default_ticket_case_uses_real_static_trips(session):
    result = defaults.default_demo(session)
    assert result["status"] == "FOUND"
    assert result["origin"]["stop_name"] == defaults.DEMO_ORIGIN
    assert result["destination"]["stop_name"] == defaults.DEMO_DESTINATION
    assert result["rows"], "default route must have real GTFS rows"
    assert result["trips"]["source"] == "GTFS_SQLITE"
    assert result["trips"]["data_type"] == "STATIC_SCHEDULE"
    assert result["trips"]["real_time"] is False


# T078
def test_t078_default_date_exists_in_static_schedule():
    result = RailwayStatic().trips(defaults.DEMO_SERVICE_DATE, "VNP", "AOH", limit=5)
    assert result["status"] == "FOUND"
    assert result["total_count"] > 0
    assert result["dataset_version"] == "gtfs-20261101-063437"
    assert result["database_sha256"] == "e32f0cd41b45532ea7aedf4c72a6ffc24f6eaa23c042ee8f35cb02aa50735c69"


# T079
def test_t079_default_city_names_preserve_real_ambiguity(session):
    result = defaults.resolve_trips(session, "上海", "杭州", defaults.DEMO_SERVICE_DATE)
    assert len(result["origin_candidates"]) > 1
    assert len(result["destination_candidates"]) > 1
    assert result["origin"]["stop_name"] == "上海虹桥"
    assert result["destination"]["stop_name"] == "杭州东"


# T080
def test_t080_static_trip_is_joined_to_local_inventory(session):
    result = defaults.default_demo(session)
    inv = result["inventory"]
    assert inv["simulation"] is True
    assert inv["status"] in ("SIMULATED_AVAILABLE", "INVENTORY_SOLD_OUT",
                             "INVENTORY_NOT_CONFIGURED")
    if inv["status"] == "SIMULATED_AVAILABLE":
        assert type(inv["available"]) is int and inv["available"] >= 1


# T081
def test_t081_sold_out_inventory_is_a_normal_state(monkeypatch):
    monkeypatch.setenv("RAILWAY_SIMULATION_ENABLED", "1")
    root = _base()
    path = root / "soldout.sqlite"
    service = Service(Store(path), RailwayStatic(), policy=Policy())
    service.start()
    service.scenario("v394-soldout", "gtfs-20261101-063437", name="sold_out")
    ctx = Context("S-soldout", "U", "v394-soldout", enabled=True, provider="mock",
                  tool_whitelist=("railway_check_inventory",))
    trip = RailwayStatic().trips(defaults.DEMO_SERVICE_DATE, "AOH", "HGH", limit=1)["data"][0]
    result = service.inventory(ctx, trip_id=trip["trip_id"], service_date=defaults.DEMO_SERVICE_DATE,
                               origin_stop_id="AOH", destination_stop_id="HGH",
                               seat_class="SECOND", quantity=1)
    assert result["status"] == "INVENTORY_SOLD_OUT"
    assert result["available"] == 0
    assert result["simulation"] is True


# T082
def test_t082_unknown_train_is_not_a_failure():
    result = RailwayStatic().trips(defaults.DEMO_SERVICE_DATE, train_no="NO-SUCH-TRAIN", limit=5)
    assert result["status"] == "NO_MATCH"
    assert result["data"] == []
    assert result["real_time"] is False


# T083
def test_t083_empty_station_input_is_input_invalid(session):
    with pytest.raises(defaults.DefaultQueryError) as exc:
        defaults.resolve_trips(session, "", defaults.DEMO_DESTINATION, defaults.DEMO_SERVICE_DATE)
    assert exc.value.status == "INPUT_INVALID"


# T084
def test_t084_default_trip_query_has_real_total_and_page(session):
    result = defaults.default_demo(session)
    data = result["trips"]
    assert data["total_count"] >= data["returned_count"] > 0
    assert data["returned_count"] == len(data["data"])
    assert data["has_more"] is True
    assert data["next_cursor"]


# T085
def test_t085_station_search_returns_real_candidates():
    result = RailwayStatic().stations("上海", limit=50)
    assert result["status"] == "FOUND"
    assert result["total_count"] == 5
    assert {r["stop_name"] for r in result["data"]} >= {"上海", "上海虹桥", "上海南"}
    assert result["selection_required"] is True


# T086
def test_t086_trip_stops_uses_the_real_trip_id(session):
    result = defaults.default_demo(session)
    trip = result["rows"][0]
    stops = RailwayStatic().trip(trip["trip_id"], defaults.DEMO_SERVICE_DATE)
    assert stops["status"] == "FOUND"
    assert len(stops["data"]["stops"]) >= 2
    assert {stops["data"]["stops"][0]["stop_id"], stops["data"]["stops"][-1]["stop_id"]}


# T087
def test_t087_default_trip_pagination_has_no_duplicates():
    static = RailwayStatic()
    first = static.trips(defaults.DEMO_SERVICE_DATE, "AOH", "HGH", limit=20)
    second = static.trips(defaults.DEMO_SERVICE_DATE, "AOH", "HGH", limit=20,
                          cursor=first["next_cursor"])
    ids1 = [r["trip_id"] for r in first["data"]]
    ids2 = [r["trip_id"] for r in second["data"]]
    assert len(ids1) == 20 and len(ids2) == 20
    assert not set(ids1) & set(ids2)
    assert first["total_count"] == second["total_count"]


# T088
def test_t088_static_identity_failure_is_data_unavailable(session, monkeypatch):
    prepared = defaults.prepare(session)
    static = prepared[0].static
    def broken():
        raise ValueError("STATIC_DATA_IDENTITY_MISMATCH")
    monkeypatch.setattr(static, "_open", broken)
    with pytest.raises(defaults.DefaultQueryError) as exc:
        defaults.resolve_trips(session, defaults.DEMO_ORIGIN, defaults.DEMO_DESTINATION,
                               defaults.DEMO_SERVICE_DATE)
    assert exc.value.status == "DATA_UNAVAILABLE"


# T089
def test_t089_agent_side_panel_error_does_not_pollute_chat(monkeypatch):
    from web.user_features import query
    fake = SimpleNamespace(read_only=False, live=False, results=[], error={"category": "AGENT"},
                           sid="S", send=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        query(fake, "查询", "query_tickets")
    assert fake.error is None
    assert fake.panel_error["source"] == "user_feature"


# T090
def test_t090_right_rail_query_error_has_own_state(session, prepared):
    from web.railway_queries import query
    service, ctx, effective = prepared
    session.error = {"category": "STALE"}
    row = query(session, service, ctx, effective, "railway_query_trips",
                {"service_date": "bad", "limit": 20})
    assert row["ok"] is False
    assert session.error == {"category": "STALE"}


# T091
def test_t091_new_session_has_clean_error_state(monkeypatch):
    monkeypatch.setenv("RAILWAY_SIMULATION_ENABLED", "1")
    root = _base()
    monkeypatch.setenv("RAILWAY_SIM_DB_PATH", str(root / "simulation.sqlite"))
    one = Conversation("user", engine="legacy", live=False, root=root / "one")
    two = Conversation("user", engine="legacy", live=False, root=root / "two")
    assert one.error is None and two.error is None
    assert one.sid != two.sid


# T092
def test_t092_request_error_is_cleared_before_default_retry(session, monkeypatch):
    session.error = {"category": "TOOL_EXECUTION_FAILED"}
    result = defaults.default_demo(session)
    assert result["status"] == "FOUND"
    assert session.error is None


# T093
def test_t093_policy_default_explains_p01_and_d9(session):
    from target.v39.policy import PRODUCT, Policy
    assert PRODUCT["approved"] is True
    assert PRODUCT["profile"] == "CHANGED_REFUND_P01"
    assert Policy().max_changes == 1
    text = Path(config.POLICY_PATH).read_text(encoding="utf-8")
    assert "P01" in text and "48" in text and ("5%" in text or "5" in text)


# T094
def test_t094_order_empty_state_is_not_an_error(session):
    rows = orders(session.root / "tickets.db")
    assert rows == []
    assert session.error is None


# T095
def test_t095_order_with_data_is_read_from_own_database(demo_db):
    from web.demo import _step_query, _step_order
    demo = start_demo()
    _step_query(demo)
    _step_order(demo)
    assert demo.get("order_id")
    with _cdb(Path(os.environ["RAILWAY_SIM_DB_PATH"])) as c:
        assert c.execute("SELECT COUNT(*) FROM v39_orders").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM v39_transactions").fetchone()[0] == 0
    row = demo["service"].order(demo["ctx"], demo["order_id"])
    assert row["order_status"] == "PENDING_PAYMENT"


# T096
def test_t096_refund_fee_default_uses_half_up_p01():
    policy = Policy()
    departure = "2026-11-11T12:00:00+00:00"
    now = "2026-11-08T12:00:00+00:00"
    result = policy.refund([10000], departure, now, changed=True)
    assert result == [{"amount_fen": 10000, "fee_fen": 500, "net_fen": 9500}]
    later = policy.refund([10000], "2026-11-09T12:00:00+00:00", now, changed=True)
    assert later[0]["fee_fen"] == 1000


# T097
def test_t097_p06_baggage_default_is_defined():
    result = calculate_baggage("成人", 25, 50, 40, 30)
    assert result["policy_ref"] == "P06"
    assert result["excess_kg"] == "5"
    assert result["weight_fee_yuan"] == "25"
    assert result["size_status"] == "符合"


# T098
def test_t098_four_step_demo_closes_real_local_flow(demo_db):
    demo = start_demo()
    _step_query(demo)
    _step_order(demo)
    _step_pay(demo)
    _step_order_query(demo)
    assert demo["stage"] == 4
    assert demo["error"] is None
    assert demo["order_id"]
    with _cdb(Path(os.environ["RAILWAY_SIM_DB_PATH"])) as c:
        assert c.execute("SELECT COUNT(*) FROM v39_orders").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM v39_transactions").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM v39_proposals").fetchone()[0] == 2


# T099
def test_t099_confirmation_is_required_before_order_creation(session, prepared):
    service, ctx, _ = prepared
    result = defaults.default_demo(session)
    quote = service.quote(ctx, trip_id=result["rows"][0]["trip_id"],
                          service_date=defaults.DEMO_SERVICE_DATE,
                          origin_stop_id=result["origin"]["stop_id"],
                          destination_stop_id=result["destination"]["stop_id"],
                          seat_class="SECOND", passenger_count=1)
    proposal = service.propose(ctx, "CREATE_ORDER", {
        "quote_id": quote["quote"]["quote_id"], "passengers": ["张三"],
        "contact": ctx.owner_phone})
    with _cdb(Path(os.environ["RAILWAY_SIM_DB_PATH"])) as c:
        assert c.execute("SELECT COUNT(*) FROM v39_orders").fetchone()[0] == 0
    confirmed = service.confirm(ctx, proposal["proposal_id"])
    assert confirmed.get("order_id")


# T100
def test_t100_default_demo_does_not_create_transactions_before_confirmation(demo_db):
    demo = start_demo()
    _step_query(demo)
    with _cdb(Path(os.environ["RAILWAY_SIM_DB_PATH"])) as c:
        assert c.execute("SELECT COUNT(*) FROM v39_orders").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM v39_transactions").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM v39_proposals").fetchone()[0] == 0
