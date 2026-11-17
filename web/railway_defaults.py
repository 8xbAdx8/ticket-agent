"""V3.9.4 stable defaults for the original workspace.

All railway values below are real, read-only GTFS static records.  Inventory
lookups are local V3.9 simulation only; no model or external railway API is
called here.
"""
from __future__ import annotations

from dataclasses import dataclass
import uuid

import config
from target.execution_config import scope as effective_scope
from target.v39.context import scope as context_scope
from target.v39.registry import dispatch, service_scope


def default_service_date():
    """Business clock, not the wall clock: TICKET_TEST_MODE pins a fixed day.

    Every sample date in the user workspace must come from here so that quick
    prompts, placeholders, panels and the demo stay inside the static feed's
    95-day service window under both normal and test clocks.
    """
    return config.today()


# Compatibility alias for existing callers (including the V3.9.4 regression
# suite).  No literal date is stored; new UI code should call
# default_service_date() at render time instead of reading this constant.
DEMO_SERVICE_DATE = default_service_date().isoformat()
DEMO_ORIGIN = "上海虹桥"
DEMO_DESTINATION = "杭州东"
DEMO_ORIGIN_CITY = "上海"
DEMO_DESTINATION_CITY = "杭州"
DEMO_SEAT_CLASS = "SECOND"
DEMO_SEAT_LABEL = "二等座"
DEMO_PASSENGER = "张三"
DEMO_TRAIN = "G7541"
# Deterministic mapping for the built-in sample route only.  A customer query
# must never rely on this table: the two-level station picker submits an
# explicit stop_id chosen by the user (see user_features.ticket_search_panel).
PREFERRED = {
    "上海": "上海虹桥", "杭州": "杭州东", "北京": "北京南", "广州": "广州南",
    "南京": "南京南", "成都": "成都东", "武汉": "武汉", "长沙": "长沙南",
}

# The static adapter accepts 1..50 rows per page; 50 is the interface maximum.
PAGE_LIMIT = 50


class DefaultQueryError(ValueError):
    def __init__(self, code, status="INTERNAL_ERROR"):
        super().__init__(code)
        self.code = code
        self.status = status


def prepare(session):
    """Attach the same trusted V3.9 service/context as the original Agent."""
    from web import v39_bridge
    try:
        prepared = v39_bridge.prepare(session)
    except Exception as exc:  # do not expose raw exception to the user
        raise DefaultQueryError("RAILWAY_INTERNAL_ERROR", "INTERNAL_ERROR") from exc
    if not prepared:
        raise DefaultQueryError("V39_FEATURE_DISABLED", "DATA_UNAVAILABLE")
    return prepared


def _run(prepared, name, args, session=None):
    service, ctx, effective = prepared
    try:
        with context_scope(ctx), service_scope(service), effective_scope(effective):
            result, ok, elapsed = dispatch(name, args)
        if session is not None:
            service.page_event(ctx, name, args, result, ok, elapsed)
            row = dict(id=uuid.uuid4().hex, source="default_query", tool=name,
                       args=args, result=result, ok=ok)
            from web.railway_queries import record
            record(session,row)
        return result, ok
    except Exception as exc:
        code = str(exc) if isinstance(exc, ValueError) else "RAILWAY_INTERNAL_ERROR"
        return dict(error=code, simulation=True), False


def _station(prepared, name, session=None):
    result, ok = _run(prepared, "railway_search_stations",
                      {"name": name, "limit": 50}, session)
    if not ok:
        raise DefaultQueryError(str(result.get("error") or "RAILWAY_INTERNAL_ERROR"),
                                classify(result, False)[0])
    rows = list(result.get("data") or [])
    if not rows:
        raise DefaultQueryError("NO_STATION_MATCH", "NOT_FOUND")
    exact = [r for r in rows if r.get("stop_name") == name]
    preferred = [r for r in rows if r.get("stop_name") == PREFERRED.get(name)]
    chosen = preferred or exact
    if not chosen and len(rows) == 1:
        chosen = rows  # a single candidate is unambiguous
    if not chosen:
        # Never silently take rows[0] when several stations match.  The
        # customer picker must ask the user to choose an explicit stop_id.
        raise DefaultQueryError("STATION_AMBIGUOUS", "INPUT_INVALID")
    return chosen[0], rows, result


def classify(result, ok):
    """Map a Registry result to the six user-facing V3.9.4 states."""
    result = result if isinstance(result, dict) else {}
    if ok:
        status = result.get("status")
        if status in ("FOUND", "SIMULATED_AVAILABLE"):
            return "FOUND", "查询成功"
        if status in ("NO_MATCH", "EMPTY", "NOT_FOUND"):
            return "NOT_FOUND", "没有匹配结果"
        if status in ("INVENTORY_NOT_CONFIGURED",):
            return "NOT_FOUND", "没有模拟库存"
        if status in ("INVENTORY_SOLD_OUT",):
            return "FOUND", "模拟库存已售罄"
        return "FOUND", "查询成功"
    error = str(result.get("error") or "")
    if error in ("INVALID_RAILWAY_ARGUMENTS", "STATION_ID_REQUIRED", "INVALID_CURSOR",
                 "INVALID_STATION_NAME", "NO_STATION_MATCH", "INVALID_INTERVAL",
                 "STATION_AMBIGUOUS"):
        return "INPUT_INVALID", "查询条件不完整或格式不正确"
    if error in ("STATIC_DATA_IDENTITY_MISMATCH", "SQLITE_ERROR", "DATABASE_ERROR",
                 "STATIC_DATA_UNAVAILABLE", "DATASET_IDENTITY_MISMATCH"):
        return "DATA_UNAVAILABLE", "静态数据源暂不可用"
    if error in ("V39_TOOL_NOT_ALLOWED", "V39_CONFIG_MISMATCH", "V39_CONTEXT_REQUIRED",
                 "V39_SERVICE_UNAVAILABLE", "V39_LIVE_NOT_AUTHORIZED"):
        return "TOOL_EXECUTION_FAILED", "当前会话未开放此查询"
    return "TOOL_EXECUTION_FAILED", "查询执行失败"


def resolve_trips(session, origin, destination, service_date, *, seat_class=DEMO_SEAT_CLASS,
                  limit=PAGE_LIMIT):
    if hasattr(session, "error"):
        session.error = None
    prepared = prepare(session)
    o, oc, _ = _station(prepared, origin, session)
    d, dc, _ = _station(prepared, destination, session)
    result, ok = _run(prepared, "railway_query_trips", {
        "service_date": service_date, "origin_stop_id": o["stop_id"],
        "destination_stop_id": d["stop_id"], "limit": int(limit),
    }, session)
    if not ok:
        status, message = classify(result, False)
        raise DefaultQueryError(str(result.get("error") or "RAILWAY_INTERNAL_ERROR"), status)
    rows = list(result.get("data") or [])
    inventory = None
    if rows:
        inventory, inv_ok = _run(prepared, "railway_check_inventory", {
            "trip_id": rows[0]["trip_id"], "service_date": service_date,
            "origin_stop_id": o["stop_id"], "destination_stop_id": d["stop_id"],
            "seat_class": seat_class, "quantity": 1,
        }, session)
        if not inv_ok:
            inventory = {"error": inventory.get("error", "INVENTORY_UNAVAILABLE")}
    return {
        "origin": o, "destination": d, "origin_candidates": oc,
        "destination_candidates": dc, "trips": result, "rows": rows,
        "inventory": inventory, "seat_class": seat_class,
        "status": "FOUND" if rows else "NOT_FOUND",
    }


def default_demo(session):
    return resolve_trips(session, DEMO_ORIGIN, DEMO_DESTINATION,
                         default_service_date().isoformat(),
                         seat_class=DEMO_SEAT_CLASS, limit=PAGE_LIMIT)
