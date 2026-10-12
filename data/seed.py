# -*- coding: utf-8 -*-
"""生成模拟票务数据（高铁为主 + 机票少量）。

运行： python data/seed.py
说明：全部为自建虚构数据，不与任何真实票务系统交互。
"""
import sqlite3
import random
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "tickets.db"

ROUTES = [
    # (交通方式, 出发, 到达, 车次前缀, 基准价, 耗时分钟)
    ("高铁", "北京", "上海", "G1", 553.0, 300),
    ("高铁", "北京", "广州", "G7", 862.0, 480),
    ("高铁", "上海", "杭州", "G73", 73.0, 60),
    ("高铁", "武汉", "长沙", "G11", 164.0, 90),
    ("高铁", "成都", "西安", "D19", 263.0, 240),
    ("高铁", "深圳", "厦门", "D23", 245.0, 210),
    ("机票", "北京", "成都", "CA41", 1280.0, 165),
    ("机票", "上海", "广州", "MU53", 980.0, 140),
    ("机票", "杭州", "西安", "HU62", 760.0, 150),
]

SEAT_TYPES = {
    "高铁": ["二等座", "一等座", "商务座"],
    "机票": ["经济舱", "公务舱"],
}
SEAT_RATE = {
    "二等座": 1.0, "一等座": 1.6, "商务座": 3.0,
    "经济舱": 1.0, "公务舱": 2.8,
}
HOT_ROUTES = {("北京", "上海"), ("北京", "广州")}   # 热点线路：故意放出无票组合，用于抢票/候补场景


def build_db(db_path=DB_PATH):
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY,
            kind TEXT, train_no TEXT, from_city TEXT, to_city TEXT,
            date TEXT, depart TEXT, arrive TEXT,
            seat_type TEXT, price REAL, seats_left INTEGER
        );
        CREATE TABLE locks (
            lock_id TEXT PRIMARY KEY, train_no TEXT, date TEXT, seat_type TEXT,
            passengers TEXT, created_at TEXT, expire_at TEXT, used INTEGER DEFAULT 0
        );
        CREATE TABLE orders (
            order_id TEXT PRIMARY KEY, phone TEXT, train_no TEXT, date TEXT,
            seat_type TEXT, passengers TEXT, amount REAL,
            status TEXT, created_at TEXT, lock_id TEXT
        );
        CREATE TABLE users (
            phone TEXT PRIMARY KEY, name TEXT, id_card TEXT
        );
        """
    )
    random.seed(20261012)
    today = date.today()
    rows = []
    for idx, (kind, fc, tc, prefix, base, mins) in enumerate(ROUTES):
        for d in range(7):
            day = (today + timedelta(days=d)).isoformat()
            for s_no in range(3):                       # 每条线每天 3 个班次
                train_no = f"{prefix}{s_no + 1:02d}"
                depart = f"{6 + s_no * 3:02d}:{(s_no * 17) % 60:02d}"
                arrive = f"{(6 + s_no * 3 + mins // 60) % 24:02d}:{(mins + s_no * 17) % 60:02d}"
                for seat in SEAT_TYPES[kind]:
                    price = round(base * SEAT_RATE[seat], 1)
                    if (fc, tc) in HOT_ROUTES and d <= 1 and seat == "二等座":
                        seats = 0                        # 近期热点车次无票 -> 触发抢票/候补
                    elif seat in ("商务座", "公务舱"):
                        seats = random.randint(0, 5)
                    else:
                        seats = random.randint(0, 200)
                    rows.append((kind, train_no, fc, tc, day, depart, arrive, seat, price, seats))
    cur.executemany(
        "INSERT INTO inventory (kind,train_no,from_city,to_city,date,depart,arrive,seat_type,price,seats_left) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)", rows
    )
    cur.executemany(
        "INSERT INTO users VALUES (?,?,?)",
        [("13800000001", "张三", "110101200301010011"),
         ("13900000002", "李四", "110101200301010022")],
    )
    conn.commit()
    conn.close()
    print(f"已生成 {len(rows)} 条余票记录 -> {db_path}")
    return len(rows)


if __name__ == "__main__":
    build_db()
