# -*- coding: utf-8 -*-
"""
水质记录存储 - SQLite
"""
import sqlite3, os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "water_records.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS water_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            element TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT,
            note TEXT,
            recorded_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_element_time ON water_records(element, recorded_at)")
    conn.commit()
    conn.close()

def add_record(element, value, unit, note="", recorded_at=None):
    conn = get_db()
    if recorded_at is None:
        recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur = conn.execute(
        "INSERT INTO water_records (element, value, unit, note, recorded_at, created_at) VALUES (?,?,?,?,?,?)",
        (element, value, unit, note, recorded_at, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

def get_records(element=None, limit=500):
    conn = get_db()
    if element:
        rows = conn.execute(
            "SELECT * FROM water_records WHERE element=? ORDER BY recorded_at ASC LIMIT ?",
            (element, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM water_records ORDER BY recorded_at ASC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_records_grouped(limit=500):
    """按元素分组: {元素: [(date_str, value), ...]}"""
    conn = get_db()
    rows = conn.execute(
        "SELECT element, recorded_at, value FROM water_records ORDER BY recorded_at ASC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    grouped = {}
    for r in rows:
        grouped.setdefault(r["element"], []).append((r["recorded_at"], r["value"]))
    return grouped

def update_record(rid, element, value, unit, note="", recorded_at=None):
    """更新一条水质记录。"""
    if recorded_at is None:
        recorded_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = get_db()
    cur = conn.execute(
        "UPDATE water_records SET element=?, value=?, unit=?, note=?, recorded_at=? WHERE id=?",
        (element, value, unit, note, recorded_at, rid)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0

def delete_record(rid):
    conn = get_db()
    cur = conn.execute("DELETE FROM water_records WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0

def get_elements():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT element FROM water_records ORDER BY element").fetchall()
    conn.close()
    return [r["element"] for r in rows]


# ============ 滴定记录（自动留痕） ============

def init_dosing_log():
    """滴定记录表：每次滴定量发生变化时自动记录一条。"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dosing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            element TEXT NOT NULL,
            dose_ml REAL NOT NULL,
            note TEXT,
            action TEXT DEFAULT 'start',
            recorded_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def add_dosing_log(element, dose_ml, note="", recorded_at=None, action="start"):
    """记录一次滴定设置变化。"""
    conn = get_db()
    if recorded_at is None:
        recorded_at = datetime.now().strftime("%Y-%m-%d")
    if note == "" and action:
        note = "开始滴定" if action == "start" else "结束滴定"
    cur = conn.execute(
        "INSERT INTO dosing_log (element, dose_ml, note, action, recorded_at, created_at) VALUES (?,?,?,?,?,?)",
        (element, dose_ml, note, action, recorded_at, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

def get_dosing_logs(element=None):
    conn = get_db()
    if element:
        rows = conn.execute(
            "SELECT * FROM dosing_log WHERE element=? ORDER BY recorded_at ASC", (element,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM dosing_log ORDER BY recorded_at ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_last_dose(element):
    """获取某元素最近的滴定量。"""
    conn = get_db()
    row = conn.execute(
        "SELECT dose_ml FROM dosing_log WHERE element=? ORDER BY recorded_at DESC, id DESC LIMIT 1",
        (element,)
    ).fetchone()
    conn.close()
    return row["dose_ml"] if row else None

def update_dosing_log(rid, element, dose_ml, note="", recorded_at=None, action="start"):
    """更新一条滴定记录。"""
    if recorded_at is None:
        recorded_at = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    cur = conn.execute(
        "UPDATE dosing_log SET element=?, dose_ml=?, note=?, action=?, recorded_at=? WHERE id=?",
        (element, dose_ml, note, action, recorded_at, rid)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0

def delete_dosing_log(rid):
    conn = get_db()
    cur = conn.execute("DELETE FROM dosing_log WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ============ 换水记录 ============

def init_water_change():
    """换水记录表：记录每次换水的日期/水量/盐品牌/备注。"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS water_change (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            water_liters REAL NOT NULL,
            salt_brand TEXT,
            note TEXT,
            recorded_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def add_water_change(water_liters, salt_brand="", note="", recorded_at=None):
    conn = get_db()
    if recorded_at is None:
        recorded_at = datetime.now().strftime("%Y-%m-%d")
    cur = conn.execute(
        "INSERT INTO water_change (water_liters, salt_brand, note, recorded_at, created_at) VALUES (?,?,?,?,?)",
        (water_liters, salt_brand, note, recorded_at, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid

def get_water_changes(limit=100):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM water_change ORDER BY recorded_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_water_change(rid, water_liters, salt_brand="", note="", recorded_at=None):
    """更新一条换水记录。"""
    if recorded_at is None:
        recorded_at = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    cur = conn.execute(
        "UPDATE water_change SET water_liters=?, salt_brand=?, note=?, recorded_at=? WHERE id=?",
        (water_liters, salt_brand, note, recorded_at, rid)
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0

def delete_water_change(rid):
    conn = get_db()
    cur = conn.execute("DELETE FROM water_change WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0
