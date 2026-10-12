# -*- coding: utf-8 -*-
"""生成模拟票务数据（高铁为主 + 机票少量）。

运行： python data/seed.py
说明：全部为自建虚构数据，不与任何真实票务系统交互。
"""
import sqlite3
import random
import argparse
from datetime import date, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
DB_PATH = config.DB_PATH

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

# 按任务书 D3 里程碑扩展为 30 条高铁线路、5 条机票线路；均为虚构班次。
ROUTES += [
    ("高铁", fc, tc, f"G{200 + i}", 100.0 + i * 13, 120 + i * 5)
    for i, (fc, tc) in enumerate([
        ("上海", "南京"), ("南京", "北京"), ("杭州", "南京"), ("广州", "深圳"),
        ("长沙", "广州"), ("武汉", "南京"), ("西安", "北京"), ("成都", "重庆"),
        ("重庆", "武汉"), ("厦门", "福州"), ("上海", "合肥"), ("合肥", "武汉"),
        ("北京", "天津"), ("天津", "济南"), ("济南", "上海"), ("郑州", "西安"),
        ("郑州", "北京"), ("南昌", "杭州"), ("长沙", "南昌"), ("广州", "南宁"),
        ("贵阳", "昆明"), ("成都", "贵阳"), ("深圳", "杭州"), ("福州", "杭州"),
    ])
]
ROUTES += [("机票", "广州", "成都", "CZ80", 1100.0, 130),
           ("机票", "深圳", "北京", "ZH90", 1500.0, 180)]

SEAT_TYPES = {
    "高铁": ["二等座", "一等座", "商务座"],
    "机票": ["经济舱", "公务舱"],
}
SEAT_RATE = {
    "二等座": 1.0, "一等座": 1.6, "商务座": 3.0,
    "经济舱": 1.0, "公务舱": 2.8,
}
HOT_ROUTES = {("北京", "上海"), ("北京", "广州")}   # 热点线路：故意放出无票组合，用于抢票/候补场景


def build_db(db_path=None, *, reset=False):
    db_path = Path(db_path or config.DB_PATH)
    if db_path.exists() and not reset:
        raise FileExistsError("数据库已存在；仅对隔离测试库使用 --reset 明确重置")
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY,
            kind TEXT, train_no TEXT, from_city TEXT, to_city TEXT,
            date TEXT, depart TEXT, arrive TEXT,
            seat_type TEXT, price REAL, seats_left INTEGER CHECK(seats_left >= 0),
            UNIQUE(train_no,date,seat_type)
        );
        CREATE TABLE locks (
            lock_id TEXT PRIMARY KEY, train_no TEXT, date TEXT, seat_type TEXT,
            passengers TEXT, created_at TEXT, expire_at TEXT, used INTEGER DEFAULT 0
        );
        CREATE TABLE orders (
            order_id TEXT PRIMARY KEY, phone TEXT, train_no TEXT, date TEXT,
            seat_type TEXT, passengers TEXT, amount REAL,
            status TEXT, created_at TEXT, lock_id TEXT UNIQUE
        );
        CREATE TABLE users (
            phone TEXT PRIMARY KEY, name TEXT, id_card TEXT
        );
        """
    )
    rng = random.Random(20261012)
    today = config.today()
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
                        seats = rng.randint(0, 5)
                    else:
                        seats = rng.randint(1, 200)
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
    print(f"已生成 {len(rows)} 条虚构余票记录")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成虚构数据；不会默认覆盖现有库")
    parser.add_argument("--path", type=Path)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    build_db(args.path, reset=args.reset)
