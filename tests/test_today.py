# -*- coding: utf-8 -*-
from datetime import date, timedelta


def _tank_payload(tank_type="混养", stage="稳定期"):
    return {
        "name": "客厅混养缸", "water_liters": 180, "tank_type": tank_type,
        "stage": stage, "started_at": "2026-01-01", "custom_targets": {}, "salt_brand": "",
    }


def _add_record(client, element, value, days_ago=1):
    recorded_at = (date.today() - timedelta(days=days_ago)).isoformat()
    return client.post("/api/water/record", json={"element": element, "value": value, "recorded_at": recorded_at})


class TestTodayDashboard:
    def test_unconfigured_tank_is_not_falsely_judged(self, test_client):
        data = test_client.get("/api/today").json()
        assert data["status"]["code"] == "setup"
        assert data["evidence"] == []

    def test_dashboard_seeds_professional_maintenance_rhythm(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        data = test_client.get("/api/today").json()
        keys = {item["task_key"] for item in data["rhythm"]}
        assert keys == {"water_core", "nutrients", "water_change", "mechanical_filter", "skimmer_cup"}
        assert len(data["actions"]) <= 3
        assert data["status"]["code"] == "insufficient"

    def test_fresh_stable_records_produce_stable_status_with_evidence(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        for element, value in {"KH": 8.0, "钙": 420, "镁": 1320, "NO3": 5, "PO4": 0.06}.items():
            _add_record(test_client, element, value, 2)
            _add_record(test_client, element, value, 1)
        data = test_client.get("/api/today").json()
        assert data["status"]["code"] == "stable"
        assert data["coverage"]["count"] == 5
        assert len(data["evidence"]) == 5
        assert "只判断已记录的数据" in data["basis_note"]

    def test_fresh_abnormal_trend_is_prioritized(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        _add_record(test_client, "KH", 10.5, 2)
        _add_record(test_client, "KH", 12.5, 1)
        data = test_client.get("/api/today").json()
        assert data["status"]["code"] == "priority"
        assert data["actions"][0]["task_key"] == "water_warning"
        assert data["actions"][0]["target_tab"] == "water"

    def test_single_stable_low_nutrient_is_attention_not_emergency(self, test_client):
        test_client.put("/api/tank", json=_tank_payload("LPS"))
        _add_record(test_client, "PO4", 0.008, 1)
        data = test_client.get("/api/today").json()
        assert data["status"]["code"] == "attention"
        assert data["status"]["tone"] == "warn"
        assert data["actions"][0]["timing"] == "建议复核"
        assert not data["status"]["summary"].startswith("🪸")

    def test_rules_can_be_customized_without_resetting_to_defaults(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        test_client.get("/api/today")
        response = test_client.put("/api/maintenance/rule/water_change", json={"interval_days": 21, "enabled": True})
        assert response.status_code == 200
        rules = test_client.get("/api/maintenance").json()["rules"]
        rule = next(item for item in rules if item["task_key"] == "water_change")
        assert rule["interval_days"] == 21
        assert rule["is_custom"] is True
        test_client.get("/api/today")
        rules = test_client.get("/api/maintenance").json()["rules"]
        assert next(item for item in rules if item["task_key"] == "water_change")["interval_days"] == 21

    def test_completing_equipment_task_starts_its_rhythm(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        before = test_client.get("/api/today").json()["rhythm"]
        assert next(item for item in before if item["task_key"] == "skimmer_cup")["state"] == "untracked"
        response = test_client.post("/api/maintenance/event", json={"task_key": "skimmer_cup", "action": "complete"})
        assert response.status_code == 200
        after = test_client.get("/api/today").json()["rhythm"]
        task = next(item for item in after if item["task_key"] == "skimmer_cup")
        assert task["state"] == "later"
        assert task["timing"] == "7 天后"

    def test_postpone_moves_an_overdue_task_forward(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        for element, value in {"KH": 8, "钙": 420, "镁": 1320}.items():
            _add_record(test_client, element, value, 10)
        before = test_client.get("/api/today").json()["rhythm"]
        assert next(item for item in before if item["task_key"] == "water_core")["state"] == "overdue"
        response = test_client.post("/api/maintenance/event", json={
            "task_key": "water_core", "action": "postpone", "snooze_days": 3,
        })
        assert response.status_code == 200
        after = test_client.get("/api/today").json()["rhythm"]
        task = next(item for item in after if item["task_key"] == "water_core")
        assert task["state"] == "soon"
        assert task["timing"] == "3 天后"

    def test_maintenance_is_in_full_backup(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        test_client.get("/api/today")
        test_client.post("/api/maintenance/event", json={"task_key": "skimmer_cup", "action": "complete"})
        backup = test_client.get("/api/export/json").json()
        assert backup["schema_version"] == 5
        assert len(backup["maintenance_rules"]) == 5
        assert backup["maintenance_events"][0]["task_key"] == "skimmer_cup"

    def test_frequency_analysis_uses_custom_maintenance_interval(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        test_client.get("/api/today")
        test_client.put("/api/maintenance/rule/water_core", json={"interval_days": 21, "enabled": True})
        _add_record(test_client, "KH", 8.0, 10)
        kh = test_client.get("/api/analysis/frequency").json()["result"]["KH"]
        assert kh["interval_days"] == 21
        assert kh["stale"] is False
        assert "21 天周期" in kh["msg"]
