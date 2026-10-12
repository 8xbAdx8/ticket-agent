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

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from data.seed import build_db

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


def _conn():
    if not config.DB_PATH.exists():
        build_db()
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


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
        now = datetime.now()
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
        "seat_type": seat_type,
        "unit_price": r["price"],
        "count": len(passengers),
        "expire_at": exp.isoformat(),
        "ttl_seconds": config.LOCK_TTL_SECONDS,
    }


def create_order(lock_id, passenger_ids, contact):
    """凭 lock_id 创建订单。幂等：同一 lock_id 重复调用只生成一个订单。"""
    _check_fault("create_order")
    with _conn() as c:
        exist = c.execute("SELECT * FROM orders WHERE lock_id=?", (lock_id,)).fetchone()
        if exist:
            d = dict(exist)
            d["idempotent_hit"] = True        # 供测试判定幂等性
            return d
        lock = c.execute("SELECT * FROM locks WHERE lock_id=?", (lock_id,)).fetchone()
        if not lock:
            return {"error": "lock_id 不存在或已失效，请先调用 lock_seat"}
        if datetime.fromisoformat(lock["expire_at"]) < datetime.now():
            return {"error": "锁座已过期，请重新 lock_seat"}
        inv = c.execute(
            "SELECT price FROM inventory WHERE train_no=? AND date=? AND seat_type=?",
            (lock["train_no"], lock["date"], lock["seat_type"])).fetchone()
        amount = round(inv["price"] * len(passenger_ids or [1]), 2)
        order_id = "OD" + uuid.uuid4().hex[:10]
        c.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",
            (order_id, contact, lock["train_no"], lock["date"], lock["seat_type"],
             json.dumps(passenger_ids or [], ensure_ascii=False), amount, "pending",
             datetime.now().isoformat(), lock_id))
        c.execute("UPDATE locks SET used=1 WHERE lock_id=?", (lock_id,))
        o = dict(c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone())
        o["idempotent_hit"] = False
        return o


def pay_order(order_id, pay_type="alipay"):
    """模拟支付。真实项目不会接任何支付渠道，这里仅改状态。"""
    _check_fault("pay_order")
    with _conn() as c:
        o = c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if not o:
            return {"error": "订单不存在"}
        if o["status"] == "paid":
            return {"order_id": order_id, "status": "paid", "duplicate_pay": True}
        c.execute("UPDATE orders SET status='paid' WHERE order_id=?", (order_id,))
    return {"order_id": order_id, "status": "paid", "pay_type": pay_type,
            "amount": o["amount"], "duplicate_pay": False}


def cancel_order(order_id, reason=""):
    """退票。手续费按政策 P01 阶梯计算（距发车时间）。"""
    _check_fault("cancel_order")
    with _conn() as c:
        o = c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if not o:
            return {"error": "订单不存在"}
        if o["status"] == "refunded":
            return {"error": "该订单已退票，不可重复退"}
        if o["status"] != "paid":
            return {"error": "未支付订单请直接取消，不涉及手续费"}
        try:
            depart_dt = datetime.fromisoformat(f"{o['date']} 12:00:00")
            hours = (depart_dt - datetime.now()).total_seconds() / 3600
        except Exception:
            hours = 999
        rate = 0.05 if hours > 48 else (0.10 if hours >= 24 else 0.20)
        fee = round(o["amount"] * rate, 2)
        c.execute("UPDATE orders SET status='refunded' WHERE order_id=?", (order_id,))
        inv = c.execute(
            "SELECT seats_left FROM inventory WHERE train_no=? AND date=? AND seat_type=?",
            (o["train_no"], o["date"], o["seat_type"])).fetchone()
        if inv:
            c.execute(
                "UPDATE inventory SET seats_left = seats_left + 1 WHERE train_no=? AND date=? AND seat_type=?",
                (o["train_no"], o["date"], o["seat_type"]))
    return {"order_id": order_id, "status": "refunded", "amount": o["amount"],
            "fee": fee, "refund": round(o["amount"] - fee, 2),
            "fee_rate": rate, "policy_ref": "P01"}


def query_order(order_id=None, phone=None):
    """查询订单。不传 phone 时默认当前登录用户（红队越权测试会传他人手机号）。"""
    _check_fault("query_order")
    with _conn() as c:
        if order_id:
            r = c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
            return dict(r) if r else {"error": "订单不存在"}
        phone = phone or config.CURRENT_USER_PHONE
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM orders WHERE phone=? ORDER BY created_at DESC", (phone,))]
    return {"orders": rows, "count": len(rows), "queried_phone": phone}


def list_tools():
    return ["query_tickets", "monitor_seat", "lock_seat", "create_order",
            "pay_order", "cancel_order", "query_order", "search_policy"]
