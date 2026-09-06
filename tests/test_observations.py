# -*- coding: utf-8 -*-
from datetime import date


def _tank_payload():
    return {
        "name": "客厅混养缸", "water_liters": 120, "tank_type": "混养",
        "stage": "稳定期", "started_at": "2026-01-01", "custom_targets": {},
        "salt_brand": "",
    }


class TestReefObservations:
    def test_today_offers_lightweight_reef_round_without_livestock_profile(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        data = test_client.get("/api/today").json()
        action = next(item for item in data["actions"] if item["task_key"] == "reef_round")
        assert action["action_type"] == "observe"
        assert action["title"] == "看一圈"
        assert data["observation"] is None

    def test_saving_observation_updates_today_and_recent_events(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        response = test_client.post("/api/observations", json={
            "status": "changed", "tags": ["coral", "fish"], "note": "右侧榔头比昨天缩一点",
        })
        assert response.status_code == 200
        saved = response.json()["observation"]
        assert saved["status"] == "changed"
        assert saved["tags"] == ["coral", "fish"]

        today = test_client.get("/api/today").json()
        assert today["observation"]["is_today"] is True
        assert today["observation"]["summary"] == "右侧榔头比昨天缩一点"
        assert all(item["task_key"] != "reef_round" for item in today["actions"])
        event = next(item for item in today["recent_events"] if item["kind"] == "observation")
        assert event["title"] == "看过一圈"
        assert "有点变化" in event["detail"]

    def test_observation_payload_rejects_unknown_status_tags_and_long_note(self, test_client):
        assert test_client.post("/api/observations", json={"status": "bad"}).status_code == 422
        assert test_client.post("/api/observations", json={
            "status": "watch", "tags": ["unknown"],
        }).status_code == 422
        assert test_client.post("/api/observations", json={
            "status": "watch", "note": "x" * 201,
        }).status_code == 422

    def test_observations_are_backed_up_and_imported_idempotently(self, test_client):
        test_client.put("/api/tank", json=_tank_payload())
        test_client.post("/api/observations", json={
            "status": "good", "tags": [], "note": "今天整体开得很好",
        })
        backup = test_client.get("/api/export/json").json()
        assert backup["schema_version"] == 6
        assert len(backup["reef_observations"]) == 1
        assert backup["reef_observations"][0]["recorded_at"].startswith(date.today().isoformat())

        first = test_client.post("/api/import", json=backup).json()
        assert first["inserted"] == 0
        assert first["skipped"] >= 1
        assert len(test_client.get("/api/observations").json()["observations"]) == 1
