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
