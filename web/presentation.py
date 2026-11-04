"""读取已执行工具的完整结果；不额外查询、不改变公共 Trace。"""
import ast
import copy
import html
import json
from pathlib import Path

TOOL_LABELS = {"query_tickets": "查询余票", "monitor_seat": "候补监控", "lock_seat": "锁座",
               "create_order": "创建订单", "pay_order": "支付订单", "cancel_order": "取消/退票",
               "query_order": "查询订单", "search_policy": "检索政策",
               "railway_search_stations": "查询车站", "railway_query_trips": "查询静态车次", "railway_trip_stops": "查询经停站",
               "railway_check_inventory": "查询模拟余票", "railway_quote_fare": "生成模拟报价", "railway_get_order": "查询本人订单",
               "railway_create_order": "创建模拟订单", "railway_pay_order": "模拟支付", "railway_cancel_order": "取消模拟订单",
               "railway_refund_order": "模拟退票", "railway_change_order": "模拟改签"}
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


def _duration(train):
    try:
        from datetime import datetime
        depart = datetime.strptime(train["depart"], "%H:%M")
        arrive = datetime.strptime(train["arrive"], "%H:%M")
        minutes = int((arrive - depart).total_seconds() / 60) % 1440
        return f"{minutes // 60}小时{minutes % 60:02}分"
    except (ValueError, TypeError, KeyError):
        return "车程未提供"


def ticket_cards(result):
    """Structured train rows: one ``ticket-card`` per train, aligned columns."""
    trains = result.get("trains", [])[:20]
    if not trains:
        return ""
    cards = []
    source=result.get('data_source') or {}
    source_label=('SYNTHETIC_TEST_FIXTURE · 非真实数据' if source.get('classification')=='SYNTHETIC_TEST_FIXTURE' else '历史快照 · 非实时余票') if source.get('mode')=='snapshot' else '演示数据 · 不真实出票'
    if source.get('mode')=='live':
        source_label='SYNTHETIC_TEST_FIXTURE · 非真实数据' if source.get('classification')=='SYNTHETIC_TEST_FIXTURE' else '独立只读查询 · 非实时保证'
    for t in trains:
        stock = t.get("seats_left")
        if type(stock) in (int, float):
            label, sold = f"余票 {stock} 张", stock <= 0
        else:
            label, sold = "余票未提供", False
        price = "票价未提供" if t.get("price") is None else "¥" + str(t["price"])
        cards.append(f'''<div class="ticket-card">
          <div class="tc-train"><strong>{escape(t.get('train_no') or '车次未提供')}</strong><div class="muted">{escape(source_label)}</div></div>
          <div class="tc-route"><b>{escape(t.get('depart') or '—')} <span class="tc-arrow">→</span> {escape(t.get('arrive') or '—')}</b>
            <div class="muted">{escape(t.get('from_city') or '—')} → {escape(t.get('to_city') or '—')} · {escape(_duration(t))}</div></div>
          <div class="tc-seat"><b>{escape(t.get('seat_type') or '席别未提供')}</b><div class="muted">{escape(t.get('date') or '日期未提供')}</div></div>
          <div class="tc-fare"><b>{escape(price)}</b><div class="{'sold' if sold else 'stock'}">{escape(label)}</div></div></div>''')
    head = ('<div class="ta-train-head"><span>车次</span><span>行程</span>'
            '<span>席别 / 日期</span><span>票价 / 余票</span></div>')
    return '<div class="ta-trains">' + head + "".join(cards) + "</div>"


def order_card(result):
    status = result.get("display_status") or STATUS_LABELS.get(result.get("status"), result.get("status", "未知"))
    details = " · ".join(str(result[k]) for k in ("train_no", "date", "seat_type") if k in result)
    money = f"<div class='order-money'>订单金额 <strong>¥{escape(result['amount'])}</strong></div>" if "amount" in result else ""
    refund = f"<p>手续费 ¥{escape(result['fee'])} · 退款 {escape('¥'+str(result['refund']) if result.get('refund') is not None else '未提供')}</p>" if "fee" in result else ""
    duplicate = "<p>演示订单已标记支付，本次未重复处理，不会真实扣款。</p>" if result.get("duplicate_pay") else ""
    method = {'alipay': '支付宝', 'wechat': '微信', 'card': '银行卡'}.get(result.get('pay_type'), '未记录')
    payment = '<p>演示支付方式：'+escape(method)+'</p>' if result.get('status')=='paid' else ''
    if result.get('refund_record'):
        r=result['refund_record']
        refund=f"<p>手续费 ¥{escape(r['fee'])} · 退款 ¥{escape(r['refund'])} · {escape(r['policy_ref'])}</p>"
    if result.get('reschedule'):
        payment += '<p>已改签 · 新票面金额 ¥'+escape(result['reschedule']['new_amount'])+' · 差价仅记录</p>'
    return f'''<div class="order-card"><div class="order-top">演示订单 <span>{escape(status)}</span></div>
      <strong>{escape(details)}</strong><div class="muted">订单号 {escape(result.get('order_id', ''))}</div>{money}{refund}{duplicate}{payment}
      <div class="muted">仅模拟订单和支付状态，不会真实出票、扣款或退款。</div></div>'''


def policy_cards(result):
    return "".join(f'''<div class="policy-card"><div class="stock">{escape(h.get('doc_id', ''))} · 项目内示例政策</div>
      <strong>{escape(h.get('title', ''))}</strong><p>{escape(h.get('content', ''))}</p>
      <div class="muted">仅供演示，请核对适用条件。</div></div>'''
      for h in result.get("hits", []))


def code_excerpt(root, relative, name, owner=None):
    text = (Path(root) / relative).read_text(encoding="utf-8")
    tree = ast.parse(text)
    scope = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner) if owner else tree
    node = next(n for n in ast.walk(scope) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return node.lineno, "\n".join(text.splitlines()[node.lineno-1:node.end_lineno])
