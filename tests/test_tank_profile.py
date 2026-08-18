# -*- coding: utf-8 -*-
"""“我的鱼缸”单缸底座、缸型目标和旧库迁移测试。"""
import sqlite3

import pytest


def profile_payload(tank_type="混养", **overrides):
    payload = {
        "name": "客厅主缸",
        "water_liters": 156,
        "tank_type": tank_type,
        "stage": "稳定期",
        "started_at": "2025-01-02",
        "custom_targets": {},
        "salt_brand": "",
    }
    payload.update(overrides)
    return payload


class TestTankProfileApi:
    def test_default_profile_is_lightweight_and_incomplete(self, test_client):
        response = test_client.get("/api/tank")
        assert response.status_code == 200
        tank = response.json()["tank"]
        assert tank["name"] == "我的鱼缸"
        assert tank["tank_type"] == "混养"
        assert tank["water_liters"] is None
        assert tank["setup_complete"] is False

    @pytest.mark.parametrize("tank_type", ["FOT", "软体", "LPS", "SPS", "NPS", "混养"])
    def test_all_requested_tank_types_can_be_saved(self, test_client, tank_type):
        response = test_client.put("/api/tank", json=profile_payload(tank_type))
        assert response.status_code == 200
        tank = response.json()["tank"]
        assert tank["tank_type"] == tank_type
        assert tank["water_liters"] == 156
        assert tank["setup_complete"] is True

    def test_options_expose_exact_requested_types(self, test_client):
        data = test_client.get("/api/tank/options").json()
        assert [item["value"] for item in data["types"]] == ["FOT", "软体", "LPS", "SPS", "NPS", "混养"]
        assert data["stages"] == ["筹备中", "开缸期", "稳定期", "调整期"]
        fot = next(item for item in data["types"] if item["value"] == "FOT")
        assert "只养鱼" in fot["description"]
        assert fot["targets"]["NO3"]["high"] == 30
        assert any("过滤负担" in item for item in fot["focus"])
        soft = next(item for item in data["types"] if item["value"] == "软体")
        assert "海葵不是软体珊瑚" in soft["description"]
        sps = next(item for item in data["types"] if item["value"] == "SPS")
        assert "小水螅体" in sps["description"]
        assert sps["targets"]["KH"]["high"] == 9

    def test_invalid_type_and_future_started_date_are_rejected(self, test_client):
        bad_type = profile_payload("淡水")
        assert test_client.put("/api/tank", json=bad_type).status_code == 422
        future = profile_payload(started_at="2999-01-01")
        assert test_client.put("/api/tank", json=future).status_code == 422

    def test_sps_profile_changes_effective_targets(self, test_client):
        test_client.put("/api/tank", json=profile_payload("SPS"))
        data = test_client.get("/api/water/ideals").json()
        assert data["tank_type"] == "SPS"
        assert data["source"] == "tank_profile"
        assert data["ideals"]["KH"]["high"] == 9
        assert data["ideals"]["PO4"]["low"] == 0.02

    def test_custom_target_overrides_profile_safely(self, test_client):
        payload = profile_payload("LPS", custom_targets={"NO3": {"low": 3, "high": 12}})
        response = test_client.put("/api/tank", json=payload)
        assert response.status_code == 200
        ideals = response.json()["effective_targets"]
        assert ideals["NO3"]["low"] == 3
        assert ideals["NO3"]["high"] == 12

        invalid = profile_payload(custom_targets={"NO3": {"low": 12, "high": 3}})
        assert test_client.put("/api/tank", json=invalid).status_code == 422

    def test_existing_records_remain_linked_after_profile_edit(self, test_client):
        test_client.post("/api/water/record", json={"element": "KH", "value": 8.2, "recorded_at": "2025-04-01"})
        test_client.put("/api/tank", json=profile_payload("LPS"))
        records = test_client.get("/api/water/records").json()["records"]
        assert len(records) == 1
        assert records[0]["tank_id"] == test_client.get("/api/tank").json()["tank"]["id"]

    def test_backup_contains_profile_and_old_backup_remains_compatible(self, test_client):
        test_client.put("/api/tank", json=profile_payload("NPS"))
        backup = test_client.get("/api/export/json").json()
        assert backup["schema_version"] == 2
        assert backup["tank"]["tank_type"] == "NPS"

        old_backup = {
            "water_records": [{"element": "NO3", "value": 8, "unit": "ppm", "recorded_at": "2025-05-01"}],
            "dosing_log": [],
            "water_change": [],
        }
        result = test_client.post("/api/import", json=old_backup).json()
        assert result["inserted"] == 1
        assert test_client.get("/api/water/records").json()["records"][0]["tank_id"] == backup["tank"]["id"]


def test_old_database_rows_are_migrated_to_default_tank(tmp_path, monkeypatch):
    import water_store

    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE water_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            element TEXT NOT NULL, value REAL NOT NULL, unit TEXT, note TEXT,
            recorded_at TEXT NOT NULL, created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        """INSERT INTO water_records (element,value,unit,note,recorded_at,created_at)
           VALUES ('KH',8.0,'dKH','','2025-01-01','2025-01-01')"""
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(water_store, "DB_PATH", str(db_path))
    water_store.init_db()
    water_store.init_dosing_log()
    water_store.init_water_change()

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(water_records)").fetchall()}
    migrated = conn.execute("SELECT tank_id FROM water_records").fetchone()[0]
    tank_id = conn.execute("SELECT id FROM tanks WHERE is_active=1").fetchone()[0]
    conn.close()
    assert "tank_id" in columns
    assert migrated == tank_id
