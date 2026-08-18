# -*- coding: utf-8 -*-
"""海水缸档案与维护记录的 SQLite 存储层。"""
import json
import math
import os
import sqlite3
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), "water_records.db")
TANK_TYPES = ("FOT", "软体", "LPS", "SPS", "NPS", "混养")
TANK_STAGES = ("筹备中", "开缸期", "稳定期", "调整期")
WATER_ELEMENTS = ("KH", "钙", "镁", "NO3", "PO4")
DOSING_ELEMENTS = ("KH", "钙", "镁")
DOSING_ACTIONS = ("start", "end", "adjust")
ELEMENT_UNITS = {"KH": "dKH", "钙": "ppm", "镁": "ppm", "NO3": "ppm", "PO4": "ppm"}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn, table, column, definition):
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_active_tank(conn):
    """创建单缸档案并返回当前档案 id；以后扩展多缸时无需改记录结构。"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tanks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '我的鱼缸',
            water_liters REAL,
            tank_type TEXT NOT NULL DEFAULT '混养',
            stage TEXT NOT NULL DEFAULT '稳定期',
            started_at TEXT,
            custom_targets TEXT NOT NULL DEFAULT '{}',
            salt_brand TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            setup_complete INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    row = conn.execute("SELECT id FROM tanks WHERE is_active=1 ORDER BY id LIMIT 1").fetchone()
    if row:
        return row["id"]
    row = conn.execute("SELECT id FROM tanks ORDER BY id LIMIT 1").fetchone()
    if row:
        conn.execute("UPDATE tanks SET is_active=1, updated_at=? WHERE id=?", (_now(), row["id"]))
        return row["id"]
    cur = conn.execute(
        """INSERT INTO tanks
           (name, water_liters, tank_type, stage, started_at, custom_targets,
            salt_brand, is_active, setup_complete, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        ("我的鱼缸", None, "混养", "稳定期", "", "{}", "", 1, 0, _now(), _now()),
    )
    return cur.lastrowid


def init_db():
    """初始化档案和水质表，并把旧版无 tank_id 数据迁移到默认鱼缸。"""
    conn = get_db()
    tank_id = _ensure_active_tank(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS water_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            element TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT,
            note TEXT,
            recorded_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            tank_id INTEGER
        )
    """)
    _ensure_column(conn, "water_records", "tank_id", "INTEGER")
    conn.execute("UPDATE water_records SET tank_id=? WHERE tank_id IS NULL", (tank_id,))
    conn.execute("CREATE INDEX IF NOT EXISTS idx_element_time ON water_records(element, recorded_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_water_tank_element_time ON water_records(tank_id, element, recorded_at)")
    conn.commit()
    conn.close()


def get_active_tank_id(conn=None):
    own_conn = conn is None
    conn = conn or get_db()
    tank_id = _ensure_active_tank(conn)
    if own_conn:
        conn.commit()
        conn.close()
    return tank_id


def _tank_dict(row):
    data = dict(row)
    try:
        data["custom_targets"] = json.loads(data.get("custom_targets") or "{}")
    except (TypeError, json.JSONDecodeError):
        data["custom_targets"] = {}
    data["is_active"] = bool(data.get("is_active"))
    data["setup_complete"] = bool(data.get("setup_complete"))
    return data


def get_active_tank():
    conn = get_db()
    tank_id = _ensure_active_tank(conn)
    row = conn.execute("SELECT * FROM tanks WHERE id=?", (tank_id,)).fetchone()
    conn.commit()
    conn.close()
    return _tank_dict(row)


def update_active_tank(name, water_liters, tank_type, stage, started_at="",
                       custom_targets=None, salt_brand=""):
    """保存当前鱼缸；当前版本只开放一个活动鱼缸。"""
    if tank_type not in TANK_TYPES:
        raise ValueError("不支持的鱼缸类型")
    if stage not in TANK_STAGES:
        raise ValueError("不支持的鱼缸阶段")
    water_liters = float(water_liters)
    if not math.isfinite(water_liters) or water_liters <= 0:
        raise ValueError("实际水量必须是大于 0 的有限数字")
    targets_json = json.dumps(custom_targets or {}, ensure_ascii=False, separators=(",", ":"))
    conn = get_db()
    tank_id = _ensure_active_tank(conn)
    conn.execute(
        """UPDATE tanks SET name=?, water_liters=?, tank_type=?, stage=?, started_at=?,
           custom_targets=?, salt_brand=?, setup_complete=1, updated_at=? WHERE id=?""",
        ((name or "我的鱼缸").strip()[:40], water_liters, tank_type, stage,
         started_at or "", targets_json, (salt_brand or "").strip()[:80], _now(), tank_id),
    )
    conn.commit()
    conn.close()
    return get_active_tank()


def add_record(element, value, unit, note="", recorded_at=None, tank_id=None):
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    recorded_at = recorded_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    cur = conn.execute(
        """INSERT INTO water_records
           (element, value, unit, note, recorded_at, created_at, tank_id)
           VALUES (?,?,?,?,?,?,?)""",
        (element, value, unit, note, recorded_at, _now(), tank_id),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def get_records(element=None, limit=500, tank_id=None):
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    if element:
        rows = conn.execute(
            """SELECT * FROM (
                   SELECT * FROM water_records WHERE tank_id=? AND element=?
                   ORDER BY recorded_at DESC, id DESC LIMIT ?
               ) ORDER BY recorded_at ASC, id ASC""",
            (tank_id, element, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM (
                   SELECT * FROM water_records WHERE tank_id=?
                   ORDER BY recorded_at DESC, id DESC LIMIT ?
               ) ORDER BY recorded_at ASC, id ASC""",
            (tank_id, limit),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_records_grouped(limit=500, tank_id=None):
    """按元素分组: {元素: [(date_str, value), ...]}。"""
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    rows = conn.execute(
        """SELECT element, recorded_at, value FROM (
               SELECT id, element, recorded_at, value FROM water_records
               WHERE tank_id=? ORDER BY recorded_at DESC, id DESC LIMIT ?
           ) ORDER BY recorded_at ASC, id ASC""",
        (tank_id, limit),
    ).fetchall()
    conn.close()
    grouped = {}
    for row in rows:
        grouped.setdefault(row["element"], []).append((row["recorded_at"], row["value"]))
    return grouped


def update_record(rid, element, value, unit, note="", recorded_at=None):
    recorded_at = recorded_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = get_db()
    tank_id = get_active_tank_id(conn)
    cur = conn.execute(
        """UPDATE water_records SET element=?, value=?, unit=?, note=?, recorded_at=?
           WHERE id=? AND tank_id=?""",
        (element, value, unit, note, recorded_at, rid, tank_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delete_record(rid):
    conn = get_db()
    tank_id = get_active_tank_id(conn)
    cur = conn.execute("DELETE FROM water_records WHERE id=? AND tank_id=?", (rid, tank_id))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_elements():
    conn = get_db()
    tank_id = get_active_tank_id(conn)
    rows = conn.execute(
        "SELECT DISTINCT element FROM water_records WHERE tank_id=? ORDER BY element", (tank_id,)
    ).fetchall()
    conn.close()
    return [row["element"] for row in rows]


def init_dosing_log():
    conn = get_db()
    tank_id = _ensure_active_tank(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dosing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            element TEXT NOT NULL,
            dose_ml REAL NOT NULL,
            note TEXT,
            action TEXT DEFAULT 'start',
            recorded_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            tank_id INTEGER
        )
    """)
    _ensure_column(conn, "dosing_log", "tank_id", "INTEGER")
    conn.execute("UPDATE dosing_log SET tank_id=? WHERE tank_id IS NULL", (tank_id,))
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dosing_tank_time ON dosing_log(tank_id, element, recorded_at)")
    conn.commit()
    conn.close()


def add_dosing_log(element, dose_ml, note="", recorded_at=None, action="start", tank_id=None):
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    recorded_at = recorded_at or datetime.now().strftime("%Y-%m-%d")
    if note == "" and action:
        note = "开始滴定" if action == "start" else "结束滴定"
    cur = conn.execute(
        """INSERT INTO dosing_log
           (element, dose_ml, note, action, recorded_at, created_at, tank_id)
           VALUES (?,?,?,?,?,?,?)""",
        (element, dose_ml, note, action, recorded_at, _now(), tank_id),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def get_dosing_logs(element=None, tank_id=None):
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    if element:
        rows = conn.execute(
            "SELECT * FROM dosing_log WHERE tank_id=? AND element=? ORDER BY recorded_at ASC, id ASC",
            (tank_id, element),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM dosing_log WHERE tank_id=? ORDER BY recorded_at ASC, id ASC", (tank_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_last_dose(element):
    conn = get_db()
    tank_id = get_active_tank_id(conn)
    row = conn.execute(
        """SELECT dose_ml FROM dosing_log WHERE tank_id=? AND element=?
           ORDER BY recorded_at DESC, id DESC LIMIT 1""",
        (tank_id, element),
    ).fetchone()
    conn.close()
    return row["dose_ml"] if row else None


def update_dosing_log(rid, element, dose_ml, note="", recorded_at=None, action="start"):
    recorded_at = recorded_at or datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    tank_id = get_active_tank_id(conn)
    cur = conn.execute(
        """UPDATE dosing_log SET element=?, dose_ml=?, note=?, action=?, recorded_at=?
           WHERE id=? AND tank_id=?""",
        (element, dose_ml, note, action, recorded_at, rid, tank_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delete_dosing_log(rid):
    conn = get_db()
    tank_id = get_active_tank_id(conn)
    cur = conn.execute("DELETE FROM dosing_log WHERE id=? AND tank_id=?", (rid, tank_id))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def init_water_change():
    conn = get_db()
    tank_id = _ensure_active_tank(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS water_change (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            water_liters REAL NOT NULL,
            salt_grams REAL,
            salt_brand TEXT,
            note TEXT,
            recorded_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            tank_id INTEGER
        )
    """)
    _ensure_column(conn, "water_change", "salt_grams", "REAL")
    _ensure_column(conn, "water_change", "tank_id", "INTEGER")
    conn.execute("UPDATE water_change SET tank_id=? WHERE tank_id IS NULL", (tank_id,))
    conn.execute("CREATE INDEX IF NOT EXISTS idx_change_tank_time ON water_change(tank_id, recorded_at)")
    conn.commit()
    conn.close()


def init_maintenance():
    """初始化维护节奏与完成记录。"""
    conn = get_db()
    tank_id = _ensure_active_tank(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tank_id INTEGER NOT NULL,
            task_key TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            interval_days INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            is_custom INTEGER NOT NULL DEFAULT 0,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tank_id, task_key)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tank_id INTEGER NOT NULL,
            task_key TEXT NOT NULL,
            action TEXT NOT NULL,
            note TEXT,
            recorded_at TEXT NOT NULL,
            snooze_until TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_maintenance_rule_tank ON maintenance_rules(tank_id, task_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_maintenance_event_tank_time ON maintenance_events(tank_id, task_key, recorded_at)")
    conn.commit()
    conn.close()


def ensure_maintenance_rules(defaults, tank_id=None):
    """写入默认规则；只更新未被用户自定义过的规则。"""
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    for item in defaults:
        metadata = json.dumps({
            "icon": item.get("icon", "·"),
            "elements": item.get("elements", []),
            "record_source": item.get("record_source", "maintenance"),
        }, ensure_ascii=False, separators=(",", ":"))
        existing = conn.execute(
            "SELECT id, is_custom FROM maintenance_rules WHERE tank_id=? AND task_key=?",
            (tank_id, item["task_key"]),
        ).fetchone()
        if existing is None:
            conn.execute(
                """INSERT INTO maintenance_rules
                   (tank_id, task_key, title, category, interval_days, enabled, is_custom, metadata, created_at, updated_at)
                   VALUES (?,?,?,?,?,1,0,?,?,?)""",
                (tank_id, item["task_key"], item["title"], item["category"], int(item["interval_days"]),
                 metadata, _now(), _now()),
            )
        elif not existing["is_custom"]:
            conn.execute(
                """UPDATE maintenance_rules SET title=?, category=?, interval_days=?, metadata=?, updated_at=?
                   WHERE id=?""",
                (item["title"], item["category"], int(item["interval_days"]), metadata, _now(), existing["id"]),
            )
    conn.commit()
    conn.close()
    return get_maintenance_rules(tank_id)


def get_maintenance_rules(tank_id=None):
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    rows = conn.execute(
        "SELECT * FROM maintenance_rules WHERE tank_id=? ORDER BY id", (tank_id,)
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item.update(json.loads(item.pop("metadata", "{}") or "{}"))
        except (TypeError, json.JSONDecodeError):
            item.pop("metadata", None)
        item["enabled"] = bool(item.get("enabled"))
        item["is_custom"] = bool(item.get("is_custom"))
        result.append(item)
    return result


def update_maintenance_rule(task_key, interval_days, enabled=True, tank_id=None):
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    cur = conn.execute(
        """UPDATE maintenance_rules SET interval_days=?, enabled=?, is_custom=1, updated_at=?
           WHERE tank_id=? AND task_key=?""",
        (int(interval_days), 1 if enabled else 0, _now(), tank_id, task_key),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def add_maintenance_event(task_key, action, note="", recorded_at=None, snooze_until=None, tank_id=None):
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    recorded_at = recorded_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    cur = conn.execute(
        """INSERT INTO maintenance_events
           (tank_id, task_key, action, note, recorded_at, snooze_until, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (tank_id, task_key, action, (note or "").strip()[:200], recorded_at, snooze_until, _now()),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def get_maintenance_events(limit=500, tank_id=None):
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    rows = conn.execute(
        """SELECT * FROM maintenance_events WHERE tank_id=?
           ORDER BY recorded_at DESC, id DESC LIMIT ?""",
        (tank_id, limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_water_change(water_liters, salt_brand="", note="", recorded_at=None, tank_id=None, salt_grams=None):
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    recorded_at = recorded_at or datetime.now().strftime("%Y-%m-%d")
    cur = conn.execute(
        """INSERT INTO water_change
           (water_liters, salt_grams, salt_brand, note, recorded_at, created_at, tank_id)
           VALUES (?,?,?,?,?,?,?)""",
        (water_liters, salt_grams, salt_brand, note, recorded_at, _now(), tank_id),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def get_water_changes(limit=100, tank_id=None):
    conn = get_db()
    tank_id = tank_id or get_active_tank_id(conn)
    rows = conn.execute(
        """SELECT * FROM water_change WHERE tank_id=?
           ORDER BY recorded_at DESC, id DESC LIMIT ?""",
        (tank_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_water_change(rid, water_liters, salt_brand="", note="", recorded_at=None, salt_grams=None):
    recorded_at = recorded_at or datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    tank_id = get_active_tank_id(conn)
    cur = conn.execute(
        """UPDATE water_change SET water_liters=?, salt_grams=?, salt_brand=?, note=?, recorded_at=?
           WHERE id=? AND tank_id=?""",
        (water_liters, salt_grams, salt_brand, note, recorded_at, rid, tank_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delete_water_change(rid):
    conn = get_db()
    tank_id = get_active_tank_id(conn)
    cur = conn.execute("DELETE FROM water_change WHERE id=? AND tank_id=?", (rid, tank_id))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def export_all():
    return {
        "schema_version": 4,
        "tank": get_active_tank(),
        "water_records": get_records(limit=100000),
        "dosing_log": get_dosing_logs(),
        "water_change": get_water_changes(limit=100000),
        "maintenance_rules": get_maintenance_rules(),
        "maintenance_events": get_maintenance_events(limit=100000),
    }


def _count_matching(conn, table, conditions, params):
    row = conn.execute("SELECT COUNT(*) FROM " + table + " WHERE " + conditions, params).fetchone()
    return row[0]


def import_all(data):
    """导入新旧备份。旧备份自动归入当前鱼缸，记录按内容去重。"""
    if not isinstance(data, dict):
        return 0, 0

    tank = data.get("tank")
    if isinstance(tank, dict) and tank.get("water_liters"):
        try:
            update_active_tank(
                tank.get("name") or "我的鱼缸", tank["water_liters"],
                tank.get("tank_type") or "混养", tank.get("stage") or "稳定期",
                tank.get("started_at") or "", tank.get("custom_targets") or {},
                tank.get("salt_brand") or "",
            )
        except (TypeError, ValueError):
            pass

    inserted = 0
    skipped = 0
    conn = get_db()
    tank_id = get_active_tank_id(conn)

    def valid_date(value):
        if not value:
            return False
        try:
            parsed = datetime.fromisoformat(str(value))
            return parsed.date() <= datetime.now().date()
        except (TypeError, ValueError):
            return False

    for record in data.get("water_records") or []:
        try:
            element = record["element"]
            value = float(record["value"])
            recorded_at = str(record.get("recorded_at") or "")
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if (element not in WATER_ELEMENTS or not math.isfinite(value) or value < 0
                or (value == 0 and element not in ("NO3", "PO4")) or not valid_date(recorded_at)):
            skipped += 1
            continue
        if _count_matching(conn, "water_records",
                           "tank_id=? AND element=? AND value=? AND recorded_at=?",
                           (tank_id, element, value, recorded_at)):
            skipped += 1
            continue
        conn.execute(
            """INSERT INTO water_records
               (element, value, unit, note, recorded_at, created_at, tank_id)
               VALUES (?,?,?,?,?,?,?)""",
            (element, value, ELEMENT_UNITS[element], str(record.get("note") or "")[:200],
             recorded_at, _now(), tank_id),
        )
        inserted += 1

    for record in data.get("dosing_log") or []:
        try:
            element = record["element"]
            dose_ml = float(record["dose_ml"])
            recorded_at = str(record.get("recorded_at") or "")
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        action = str(record.get("action") or "start")
        if (element not in DOSING_ELEMENTS or action not in DOSING_ACTIONS
                or not math.isfinite(dose_ml) or dose_ml <= 0 or not valid_date(recorded_at)):
            skipped += 1
            continue
        if _count_matching(conn, "dosing_log",
                           "tank_id=? AND element=? AND dose_ml=? AND recorded_at=?",
                           (tank_id, element, dose_ml, recorded_at)):
            skipped += 1
            continue
        conn.execute(
            """INSERT INTO dosing_log
               (element, dose_ml, note, action, recorded_at, created_at, tank_id)
               VALUES (?,?,?,?,?,?,?)""",
            (element, dose_ml, str(record.get("note") or "")[:200], action,
             recorded_at, _now(), tank_id),
        )
        inserted += 1

    for record in data.get("water_change") or []:
        try:
            water_liters = float(record["water_liters"])
            salt_grams_raw = record.get("salt_grams")
            salt_grams = float(salt_grams_raw) if salt_grams_raw not in (None, "") else None
            recorded_at = str(record.get("recorded_at") or "")
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if (not math.isfinite(water_liters) or water_liters <= 0
                or (salt_grams is not None and (not math.isfinite(salt_grams) or salt_grams <= 0))
                or not valid_date(recorded_at)):
            skipped += 1
            continue
        if _count_matching(conn, "water_change",
                           "tank_id=? AND water_liters=? AND recorded_at=?",
                           (tank_id, water_liters, recorded_at)):
            skipped += 1
            continue
        conn.execute(
            """INSERT INTO water_change
               (water_liters, salt_grams, salt_brand, note, recorded_at, created_at, tank_id)
               VALUES (?,?,?,?,?,?,?)""",
            (water_liters, salt_grams, str(record.get("salt_brand") or "")[:80],
             str(record.get("note") or "")[:200], recorded_at, _now(), tank_id),
        )
        inserted += 1

    for rule in data.get("maintenance_rules") or []:
        try:
            task_key = str(rule["task_key"])
            interval_days = int(rule["interval_days"])
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if not task_key or not 1 <= interval_days <= 365:
            skipped += 1
            continue
        metadata = json.dumps({
            "icon": rule.get("icon", "·"), "elements": rule.get("elements", []),
            "record_source": rule.get("record_source", "maintenance"),
        }, ensure_ascii=False, separators=(",", ":"))
        existing = conn.execute(
            "SELECT id FROM maintenance_rules WHERE tank_id=? AND task_key=?", (tank_id, task_key)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE maintenance_rules SET title=?, category=?, interval_days=?, enabled=?,
                   is_custom=1, metadata=?, updated_at=? WHERE id=?""",
                (str(rule.get("title") or task_key)[:80], str(rule.get("category") or "维护")[:40],
                 interval_days, 1 if rule.get("enabled", True) else 0, metadata, _now(), existing["id"]),
            )
            skipped += 1
        else:
            conn.execute(
                """INSERT INTO maintenance_rules
                   (tank_id, task_key, title, category, interval_days, enabled, is_custom, metadata, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,1,?,?,?)""",
                (tank_id, task_key, str(rule.get("title") or task_key)[:80],
                 str(rule.get("category") or "维护")[:40], interval_days,
                 1 if rule.get("enabled", True) else 0, metadata, _now(), _now()),
            )
            inserted += 1

    for event in data.get("maintenance_events") or []:
        task_key = str(event.get("task_key") or "")
        action = str(event.get("action") or "")
        recorded_at = str(event.get("recorded_at") or "")
        if not task_key or action not in ("complete", "postpone") or not valid_date(recorded_at):
            skipped += 1
            continue
        if _count_matching(conn, "maintenance_events",
                           "tank_id=? AND task_key=? AND action=? AND recorded_at=?",
                           (tank_id, task_key, action, recorded_at)):
            skipped += 1
            continue
        conn.execute(
            """INSERT INTO maintenance_events
               (tank_id, task_key, action, note, recorded_at, snooze_until, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (tank_id, task_key, action, str(event.get("note") or "")[:200], recorded_at,
             event.get("snooze_until"), _now()),
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted, skipped
