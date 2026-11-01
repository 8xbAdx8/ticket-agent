# -*- coding: utf-8 -*-
"""模拟票务后端：纯 Python 函数核心（零部署，直接被工具层调用）。

两种形态共用这一份逻辑：
  1. tools.py 直接 import 本模块（默认，零依赖）
  2. mock_api.py 用 FastAPI 包一层，通过 HTTP 暴露（视频演示更好看）

所有数据为自建虚构数据，不与任何真实票务系统交互。
"""
import sqlite3
import uuid
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
from contextvars import ContextVar

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from data.seed import build_db
_DATABASE_OVERRIDE = ContextVar("ticket_database_override",default=None)


@contextmanager
def database_scope(path):
    """测试线程的独立DB作用域；默认业务路径不变，不修改全局config。"""
    token=_DATABASE_OVERRIDE.set(Path(path))
    try:
        yield
    finally:
        _DATABASE_OVERRIDE.reset(token)

# ---------------- 故障注入（供边界测试与变异测试使用）----------------
FAULTS = {}   # {"query_tickets": "timeout"}  支持 timeout / error / empty


def set_fault(tool_name, mode):
    FAULTS[tool_name] = mode


def clear_faults():
    FAULTS.clear()


class ToolFault(Exception):
    def __init__(self, tool, mode):
        super().__init__(f"{tool} injected fault: {mode}")
        self.tool, self.mode = tool, mode


def _check_fault(tool_name):
    mode = FAULTS.get(tool_name)
    if mode == "timeout":
        raise ToolFault(tool_name, "timeout")
    if mode == "error":
        raise ToolFault(tool_name, "error")


@contextmanager
def _conn():
    path=_DATABASE_OVERRIDE.get() or config.DB_PATH
    if not path.exists():
        build_db(path)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    try:
        c.execute("BEGIN IMMEDIATE")
        _release_expired(c)
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def _release_expired(c):
    """在业务访问时回收过期占座；无后台任务，已支付的库存不释放。"""
    for lock in c.execute("SELECT * FROM locks WHERE used < 2 AND expire_at <= ?",
                          (config.now().isoformat(),)).fetchall():
        order = c.execute("SELECT status FROM orders WHERE lock_id=?", (lock["lock_id"],)).fetchone()
        if order and order["status"] == "paid":
            continue
        if order and order["status"] != "pending":
            c.execute("UPDATE locks SET used=2 WHERE lock_id=?", (lock["lock_id"],))
            continue
        _release(c, lock["train_no"], lock["date"], lock["seat_type"], lock["passengers"])
        c.execute("UPDATE locks SET used=2 WHERE lock_id=?", (lock["lock_id"],))
        c.execute("UPDATE orders SET status='expired' WHERE lock_id=? AND status='pending'", (lock["lock_id"],))


def _release(c, train_no, day, seat, passengers):
    c.execute("UPDATE inventory SET seats_left=seats_left+? WHERE train_no=? AND date=? AND seat_type=?",
              (len(json.loads(passengers)), train_no, day, seat))


def _owned_order(c, order_id):
    return c.execute("SELECT * FROM orders WHERE order_id=? AND phone=?",
                     (order_id, config.CURRENT_USER_PHONE)).fetchone()


# ---------------- 工具实现 ----------------

def query_tickets(from_city, to_city, date, seat_type=None, kind=None):
    """查询指定日期的车次与余票。date 必须是 YYYY-MM-DD。"""
    _check_fault("query_tickets")
    sql = "SELECT kind,train_no,from_city,to_city,date,depart,arrive,seat_type,price,seats_left FROM inventory WHERE 1=1"
    args = []
    if from_city:
        sql += " AND from_city LIKE ?"; args.append(f"%{from_city}%")
    if to_city:
        sql += " AND to_city LIKE ?"; args.append(f"%{to_city}%")
    if date:
        sql += " AND date = ?"; args.append(date)
    if seat_type:
        sql += " AND seat_type = ?"; args.append(seat_type)
    if kind:
        sql += " AND kind = ?"; args.append(kind)
    sql += " ORDER BY seats_left DESC, depart ASC LIMIT 20"
    if FAULTS.get("query_tickets") == "empty":
        return {"trains": [], "count": 0}
    with _conn() as c:
        rows = [dict(r) for r in c.execute(sql, args)]
    return {"trains": rows, "count": len(rows)}


def monitor_seat(train_no, date, seat_type, duration_min=30):
    """订阅指定车次余票监控（模拟候补）。"""
    _check_fault("monitor_seat")
    task_id = "MON" + uuid.uuid4().hex[:8]
    with _conn() as c:
        r = c.execute(
            "SELECT seats_left FROM inventory WHERE train_no=? AND date=? AND seat_type=?",
            (train_no, date, seat_type)).fetchone()
    if not r:
        return {"error": "未找到班次，不能创建候补监控"}
    if r["seats_left"] > 0:
        return {"error": "尚有余票，请先查询或锁座"}
    return {
        "task_id": task_id,
        "train_no": train_no,
        "date": date,
        "seat_type": seat_type,
        "duration_min": duration_min,
        "current_seats": r["seats_left"] if r else 0,
        "status": "monitoring",
    }


def lock_seat(train_no, date, seat_type, passengers):
    """锁座：占住座位并返回有时效的 lock_id。"""
    _check_fault("lock_seat")
    if not isinstance(passengers, list) or not passengers:
        return {"error": "passengers 必须是非空数组"}
    with _conn() as c:
        r = c.execute(
            "SELECT seats_left,price FROM inventory WHERE train_no=? AND date=? AND seat_type=?",
            (train_no, date, seat_type)).fetchone()
        if not r:
            return {"error": f"未找到 {train_no} {date} {seat_type} 的可售席位"}
        if r["seats_left"] < len(passengers):
            return {"error": "余票不足", "seats_left": r["seats_left"]}
        lock_id = "LK" + uuid.uuid4().hex[:8]
        now = config.now()
        exp = now + timedelta(seconds=config.LOCK_TTL_SECONDS)
        c.execute(
            "INSERT INTO locks VALUES (?,?,?,?,?,?,?,0)",
            (lock_id, train_no, date, seat_type, json.dumps(passengers, ensure_ascii=False),
             now.isoformat(), exp.isoformat()))
        c.execute(
            "UPDATE inventory SET seats_left = seats_left - ? WHERE train_no=? AND date=? AND seat_type=?",
            (len(passengers), train_no, date, seat_type))
    return {
        "lock_id": lock_id,
        "train_no": train_no,
        "date": date,
        "seat_type": seat_type,
        "passengers": passengers,
        "unit_price": r["price"],
        "count": len(passengers),
        "expire_at": exp.isoformat(),
        "ttl_seconds": config.LOCK_TTL_SECONDS,
    }


def create_order(lock_id, passenger_ids, contact):
    """凭 lock_id 创建订单。幂等：同一 lock_id 重复调用只生成一个订单。"""
    _check_fault("create_order")
    if contact != config.CURRENT_USER_PHONE:
        return {"error": "仅可为当前模拟用户创建订单"}
    with _conn() as c:
        exist = c.execute("SELECT * FROM orders WHERE lock_id=?", (lock_id,)).fetchone()
        if exist:
            d = dict(exist)
            d["idempotent_hit"] = True        # 供测试判定幂等性
            return d
        lock = c.execute("SELECT * FROM locks WHERE lock_id=?", (lock_id,)).fetchone()
        if not lock:
            return {"error": "lock_id 不存在或已失效，请先调用 lock_seat"}
        if lock["used"] == 2 or datetime.fromisoformat(lock["expire_at"]) <= config.now():
            return {"error": "锁座已过期，请重新 lock_seat"}
        if passenger_ids != json.loads(lock["passengers"]):
            return {"error": "下单乘客必须与锁座乘客一致"}
        inv = c.execute(
            "SELECT price FROM inventory WHERE train_no=? AND date=? AND seat_type=?",
            (lock["train_no"], lock["date"], lock["seat_type"])).fetchone()
        amount = round(inv["price"] * len(passenger_ids), 2)
        order_id = "OD" + uuid.uuid4().hex[:10]
        c.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",
            (order_id, contact, lock["train_no"], lock["date"], lock["seat_type"],
             json.dumps(passenger_ids or [], ensure_ascii=False), amount, "pending",
             config.now().isoformat(), lock_id))
        c.execute("UPDATE locks SET used=1 WHERE lock_id=?", (lock_id,))
        o = dict(c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone())
        o["idempotent_hit"] = False
        return o


def pay_order(order_id, pay_type="alipay", *, expected_amount=None):
    """模拟支付。真实项目不会接任何支付渠道，这里仅改状态。"""
    _check_fault("pay_order")
    with _conn() as c:
        o = _owned_order(c, order_id)
        if not o:
            return {"error": "订单不存在"}
        if expected_amount is not None:
            from target.payment_qr import yuan
            if yuan(o['amount']) != yuan(expected_amount):
                return {"error": "订单金额已变化，请核对后重新确认"}
        if o["status"] == "paid":
            return {"order_id": order_id, "status": "paid", "duplicate_pay": True}
        if o["status"] != "pending":
            return {"error": "当前订单状态不可支付", "status": o["status"]}
        # Keep the original 10-column orders table and public tool schema intact.
        # The unique order key and status update share BEGIN IMMEDIATE/rollback.
        c.execute('''CREATE TABLE IF NOT EXISTS demo_payments (
            order_id TEXT PRIMARY KEY, pay_type TEXT NOT NULL,
            amount REAL NOT NULL, paid_at TEXT NOT NULL)''')
        c.execute('INSERT INTO demo_payments VALUES (?,?,?,?)',
                  (order_id, pay_type, o['amount'], config.now().isoformat()))
        c.execute("UPDATE orders SET status='paid' WHERE order_id=?", (order_id,))
    return {"order_id": order_id, "status": "paid", "pay_type": pay_type,
            "amount": o["amount"], "duplicate_pay": False}


def cancel_order_by_train(train_no, date, seat_type=None, passenger=None):
    """Read-only candidate selection; even one match never cancels implicitly."""
    from contextlib import closing
    from target.order_refund import match
    path=_DATABASE_OVERRIDE.get() or config.DB_PATH
    if not path.is_file():return {"orders":[],"count":0,"message":"你没有该车次的可退订单。"}
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as c:
        c.row_factory=sqlite3.Row
        return match(c,train_no,date,seat_type,passenger)


def cancel_order(order_id, reason="", *, expected=None, source=None):
    """Original business entry; shared quote, atomic refund and inventory record."""
    _check_fault("cancel_order")
    from target.order_refund import quote,page_event
    with _conn() as c:
        o=_owned_order(c,order_id)
        if not o:return {"error":"订单不存在"}
        actual=quote(c,o)
        if actual.get('error'):return actual
        if expected is not None and actual!=expected:
            return {"error":"订单或退票费用已变化，请重新预览"}
        status='refunded' if o['status']=='paid' else 'cancelled'
        result={k:v for k,v in actual.items() if k!='snapshot_sha256'}
        result.update(status=status,refunded_at=config.now().isoformat())
        c.execute('CREATE TABLE IF NOT EXISTS refunds (order_id TEXT PRIMARY KEY,detail TEXT NOT NULL)')
        c.execute('INSERT INTO refunds VALUES (?,?)',(order_id,json.dumps(result,ensure_ascii=False)))
        c.execute('UPDATE orders SET status=? WHERE order_id=?',(status,order_id))
        _release(c,o['train_no'],o['date'],o['seat_type'],o['passengers'])
        c.execute('UPDATE locks SET used=2 WHERE lock_id=?',(o['lock_id'],))
        if source=='page':page_event(c,'refund',order_id,result)
    return result


def query_order(order_id=None, phone=None):
    """查询订单。不传 phone 时默认当前登录用户（红队越权测试会传他人手机号）。"""
    _check_fault("query_order")
    if phone and phone != config.CURRENT_USER_PHONE:
        return {"error": "不可查询其他用户订单"}
    with _conn() as c:
        if order_id:
            r = _owned_order(c, order_id)
            return _order_with_payment(c, r) if r else {"error": "订单不存在"}
        phone = phone or config.CURRENT_USER_PHONE
        rows = [_order_with_payment(c, r) for r in c.execute(
            "SELECT * FROM orders WHERE phone=? ORDER BY created_at DESC", (phone,))]
    return {"orders": rows, "count": len(rows), "queried_phone": phone}


def _order_with_payment(c, row):
    result = dict(row)
    from target.order_refund import rescheduled, exists
    result['has_reschedules']=rescheduled(c,result['order_id'])
    if result['has_reschedules']:
        record=c.execute('SELECT detail FROM reschedules WHERE order_id=?',(result['order_id'],)).fetchone()
        result['reschedule']=json.loads(record['detail'])
    if exists(c,'refunds'):
        record=c.execute('SELECT detail FROM refunds WHERE order_id=?',(result['order_id'],)).fetchone()
        if record:result['refund_record']=json.loads(record['detail'])
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='demo_payments'").fetchone():
        payment = c.execute('SELECT pay_type,paid_at FROM demo_payments WHERE order_id=?',
                            (result['order_id'],)).fetchone()
        if payment:
            result.update(dict(payment))
    return result


def list_tools():
    return ["query_tickets", "monitor_seat", "lock_seat", "create_order",
            "pay_order", "cancel_order", "query_order", "search_policy"]
