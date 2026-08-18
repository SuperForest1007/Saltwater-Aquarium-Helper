# -*- coding: utf-8 -*-
"""公开测试前的输入、趋势与连接稳定性回归。"""
from datetime import date, timedelta

from water_quality import analyze_element


def test_record_endpoints_reject_unknown_values_and_bad_dates(test_client):
    future = (date.today() + timedelta(days=1)).isoformat()
    cases = [
        ("/api/water/record", {"element": "未知", "value": 8, "recorded_at": date.today().isoformat()}),
        ("/api/water/record", {"element": "KH", "value": 8, "recorded_at": "2025/01/01"}),
        ("/api/water-change", {"water_liters": 20, "recorded_at": future}),
        ("/api/dosing/log", {"element": "KH", "dose_ml": 10, "action": "暂停", "recorded_at": date.today().isoformat()}),
    ]
    for path, payload in cases:
        response = test_client.post(path, json=payload)
        assert response.status_code == 422, (path, response.text)


def test_record_endpoints_limit_user_text(test_client):
    response = test_client.post("/api/water/record", json={
        "element": "KH", "value": 8, "note": "海" * 201,
        "recorded_at": date.today().isoformat(),
    })
    assert response.status_code == 422


def test_missing_deletes_return_404(test_client):
    for path in (
        "/api/water/record/99999",
        "/api/water-change/99999",
        "/api/dosing/log/99999",
    ):
        assert test_client.delete(path).status_code == 404


def test_trend_uses_recent_window_instead_of_old_history():
    records = [
        ("2025-01-01", 6.0),
        ("2025-01-10", 7.0),
        ("2025-02-01", 8.0),
        ("2025-12-01", 8.5),
        ("2025-12-08", 8.1),
        ("2025-12-15", 7.7),
    ]
    result = analyze_element(records, "KH")
    assert result["signals"]["direction"] == "falling"
    assert result["signals"]["count"] == 6
    assert result["signals"]["trend_count"] == 3
    assert len(result["records"]) == 6


def test_today_freshness_follows_saved_maintenance_cycle(test_client):
    assert test_client.put("/api/tank", json={
        "name": "周期测试缸", "water_liters": 100, "tank_type": "混养",
        "stage": "稳定期", "started_at": "2025-01-01",
        "custom_targets": {}, "salt_brand": "",
    }).status_code == 200
    test_client.get("/api/maintenance")
    assert test_client.put("/api/maintenance/rule/water_core", json={
        "interval_days": 3, "enabled": True,
    }).status_code == 200
    measured = (date.today() - timedelta(days=4)).isoformat()
    assert test_client.post("/api/water/record", json={
        "element": "KH", "value": 8, "recorded_at": measured,
    }).status_code == 200

    evidence = test_client.get("/api/today").json()["evidence"]
    kh = next(item for item in evidence if item["element"] == "KH")
    assert kh["state"] == "stale"
    assert kh["freshness_days"] == 3


def test_import_skips_unknown_future_and_oversized_content(test_client):
    future = (date.today() + timedelta(days=1)).isoformat()
    payload = {
        "water_records": [
            {"element": "未知", "value": 1, "recorded_at": date.today().isoformat()},
            {"element": "KH", "value": 8, "note": "n" * 250, "recorded_at": date.today().isoformat()},
            {"element": "NO3", "value": 2, "recorded_at": future},
        ],
        "dosing_log": [],
        "water_change": [],
    }
    result = test_client.post("/api/import", json=payload).json()
    assert result["inserted"] == 1
    assert result["skipped"] == 2
    record = test_client.get("/api/water/records").json()["records"][0]
    assert len(record["note"]) == 200
