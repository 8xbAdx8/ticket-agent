"""Deterministic evidence packets for P2 generation (no model, no network)."""
import config
from data.seed import ROUTES, SEAT_TYPES
from target.rag_store import documents
from target.tools import TOOLS

DIMENSION_DOCS = {
    "功能准确性": ["P01", "P02", "P11"],
    "工具调用": ["P02", "P11", "P12"],
    "RAG": ["P01", "P06", "P07"],
    "多轮": ["P02", "P11", "P12"],
    "安全": ["P12", "P13"],
    "边界": ["P06", "P15", "P11"],
    "性能": ["P11", "P12"],
}
DIMENSION_TOOLS = {
    "功能准确性": ["query_tickets", "search_policy"],
    "工具调用": ["query_tickets", "lock_seat", "create_order", "pay_order", "query_order"],
    "RAG": ["search_policy"],
    "多轮": ["query_tickets", "lock_seat", "create_order", "pay_order"],
    "安全": ["query_order", "pay_order", "cancel_order"],
    "边界": ["query_tickets", "monitor_seat", "lock_seat"],
    "性能": ["query_tickets", "monitor_seat"],
}
BUSINESS_STATES = {
    "多轮": ["locked", "order_pending", "paid"],
    "安全": ["paid"],
    "边界": ["lock_expired", "payment_failed"],
}


def corpus_docs():
    out = {}
    for chunk in documents(config.POLICY_PATH):
        out.setdefault(chunk["doc_id"], {
            "doc_id": chunk["doc_id"], "title": chunk["title"], "content": chunk["content"],
            "chunk_id": chunk["chunk_id"], "version": chunk["version"], "source": chunk["source"],
        })
    return out


def tool_specs():
    specs = {}
    for item in TOOLS:
        fn = item["function"]
        params = fn["parameters"]
        specs[fn["name"]] = {
            "name": fn["name"], "description": fn.get("description", ""),
            "required": list(params.get("required", [])),
            "properties": {k: {kk: vv for kk, vv in v.items() if kk in ("type", "enum", "description")}
                           for k, v in params.get("properties", {}).items()},
            "enums": {k: v["enum"] for k, v in params.get("properties", {}).items() if "enum" in v},
        }
    return specs


def environment():
    """Executable fixture domain: only these dates, routes, trains and seats exist."""
    routes = [{"kind": kind, "from": fc, "to": tc,
               "trains": [f"{prefix}{index:02d}" for index in (1, 2, 3)]}
              for kind, fc, tc, prefix, _base, _mins in ROUTES]
    return {
        "relative_dates": [f"<rel_date:+{day}>" for day in range(7)],
        "date_rule": "date 参数只能使用 relative_dates 中的宏，禁止写绝对日期",
        "routes": routes,
        "seat_types": {kind: list(seats) for kind, seats in SEAT_TYPES.items()},
        "hot_routes_without_second_class": ["北京-上海", "北京-广州"],
        "stateful_tools": ["create_order", "pay_order", "cancel_order", "query_order"],
        "stateful_rule": "有状态工具只能作为多轮对话的最后动作；不要为 lock_id/order_id/phone 编造具体值",
    }


def build(dimension, docs=None, tools=None):
    docs = docs or corpus_docs()
    tools = tools or tool_specs()
    wanted = [docs[d] for d in DIMENSION_DOCS[dimension] if d in docs]
    packet = {
        "schema": "ticket-p2-packet/1",
        "packet_id": "ev-" + DIMENSION_DOCS[dimension][0].lower() + "-" + str(abs(hash(dimension)) % 10000).zfill(4),
        "dimension": dimension,
        "docs": [{"doc_id": d["doc_id"], "title": d["title"], "chunk_id": d["chunk_id"],
                  "version": d["version"], "content": d["content"]} for d in wanted],
        "tools": [tools[t] for t in DIMENSION_TOOLS[dimension]],
        "business_states": BUSINESS_STATES.get(dimension, []),
        "environment": environment(),
        "allowed_entities": [d["doc_id"] for d in wanted] + DIMENSION_TOOLS[dimension],
    }
    return packet


def build_all():
    docs, tools = corpus_docs(), tool_specs()
    return {dimension: build(dimension, docs, tools) for dimension in DIMENSION_DOCS}
