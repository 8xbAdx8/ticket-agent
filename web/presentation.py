"""读取已执行工具的完整结果；不额外查询、不改变公共 Trace。"""
import ast
import copy
import html
import json
from pathlib import Path

TOOL_LABELS = {"query_tickets": "查询余票", "monitor_seat": "候补监控", "lock_seat": "锁座",
               "create_order": "创建订单", "pay_order": "支付订单", "cancel_order": "取消/退票",
               "query_order": "查询订单", "search_policy": "检索政策"}
STATUS_LABELS = {"pending": "待支付", "paid": "已支付", "cancelled": "已取消", "refunded": "已退票", "expired": "已过期"}


def escape(value):
    return html.escape(str(value), quote=True)


def turn_cursor(agent, sid):
    return len(agent.sessions.get(sid, []))


def collect_results(agent, sid, cursor, trace):
    if agent.langchain_engine is not None:
        raw = [{"tool": e["tool"], "result": e["result"]}
               for e in agent.langchain_engine.last_events if e.get("event") == "tool_end"]
    else:
        raw = []
        for message in agent.sessions.get(sid, [])[cursor:]:
            if message.get("role") == "tool":
                try:
                    raw.append({"tool": message["name"], "result": json.loads(message["content"])})
                except (ValueError, TypeError, KeyError):
                    return []
    calls = [c for step in trace["steps"] for c in step["calls"]]
    if len(raw) != len(calls) or any(r["tool"] != c["tool"] for r, c in zip(raw, calls)):
        return []
    return copy.deepcopy([dict(r, ok=c["ok"]) for r, c in zip(raw, calls)])


def ticket_cards(result):
    cards = []
    for t in result.get("trains", [])[:20]:
        stock = t.get("seats_left")
        label = f"余票 {stock} 张" if isinstance(stock, (int, float)) and stock > 0 else "已售罄"
        cards.append(f'''<div class="ticket-card">
          <div><strong>{escape(t.get('train_no', ''))}</strong><div class="muted">{escape(t.get('seat_type', ''))} · {escape(t.get('date', ''))}</div></div>
          <div class="route"><b>{escape(t.get('depart', ''))} <span>→</span> {escape(t.get('arrive', ''))}</b><div class="muted">{escape(t.get('from_city', ''))} → {escape(t.get('to_city', ''))}</div></div>
          <div class="price"><strong>¥{escape(t.get('price', ''))}</strong><div class="stock">{escape(label)}</div></div></div>''')
    return "".join(cards)


def order_card(result):
    status = STATUS_LABELS.get(result.get("status"), result.get("status", "未知"))
    details = " · ".join(str(result[k]) for k in ("train_no", "date", "seat_type") if k in result)
    money = f"<div class='order-money'>订单金额 <strong>¥{escape(result['amount'])}</strong></div>" if "amount" in result else ""
    refund = f"<p>手续费 ¥{escape(result['fee'])} · 退款 ¥{escape(result.get('refund', 0))}</p>" if "fee" in result else ""
    duplicate = "<p>订单已支付，本次没有重复扣款。</p>" if result.get("duplicate_pay") else ""
    return f'''<div class="order-card"><div class="order-top">模拟订单 <span>{escape(status)}</span></div>
      <strong>{escape(details)}</strong><div class="muted">订单号 {escape(result.get('order_id', ''))}</div>{money}{refund}{duplicate}</div>'''


def policy_cards(result):
    return "".join(f'''<div class="policy-card"><div class="stock">{escape(h.get('doc_id', ''))} · 检索来源</div>
      <strong>{escape(h.get('title', ''))}</strong><p>{escape(h.get('content', ''))}</p>
      <div class="muted">{escape(h.get('source', ''))}</div></div>'''
      for h in result.get("hits", []))


def code_excerpt(root, relative, name, owner=None):
    text = (Path(root) / relative).read_text(encoding="utf-8")
    tree = ast.parse(text)
    scope = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner) if owner else tree
    node = next(n for n in ast.walk(scope) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return node.lineno, "\n".join(text.splitlines()[node.lineno-1:node.end_lineno])
