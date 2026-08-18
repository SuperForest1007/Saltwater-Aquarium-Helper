# -*- coding: utf-8 -*-
"""
滴定方案 API 测试
"""
import pytest


class TestDosing:
    def test_dosing_meta(self, test_client):
        """滴定元素系数与默认配比。"""
        r = test_client.get("/api/dosing/meta")
        assert r.status_code == 200
        data = r.json()
        assert set(data["factors"].keys()) == {"钙", "镁", "KH", "钾"}
        assert data["factors"]["钙"] == 0.004

    def test_dosing_mix(self, test_client):
        """配液浓度：2000ml/500g钙 → 对比浓度4。"""
        r = test_client.post("/api/dosing/mix", json={
            "ro_water_ml": 2000, "powder_g": 500
        })
        assert r.status_code == 200
        assert r.json()["concentration"] == 4

    def test_dosing_daily(self, test_client):
        """每天滴定量：550L, KH 8→7.5, 7天, 50g/1000ml。"""
        r = test_client.post("/api/dosing/daily", json={
            "ro_water_ml": 1000, "powder_g": 50, "element": "KH",
            "tank_liters": 550, "first_value": 8.0, "last_value": 7.5,
            "interval_days": 7
        })
        assert r.status_code == 200
        data = r.json()
        assert data["per_ml_effect"] == 0.6  # 20*0.03
        # round(550 * (0.5/7) * 0.6) = round(23.57) = 24
        assert data["daily_dose_ml"] == 24
        assert data["daily_consumption"] == pytest.approx(0.071, abs=0.001)

    def test_dosing_element_is_restricted_to_supported_profile_elements(self, test_client):
        r = test_client.post("/api/dosing/daily", json={
            "ro_water_ml": 1000, "powder_g": 500, "element": "钾",
            "tank_liters": 100, "first_value": 400, "last_value": 390,
            "interval_days": 7,
        })
        assert r.status_code == 422

    def test_dosing_adjust(self, test_client):
        """调节表：钙目标420当前350，10天。"""
        r = test_client.post("/api/dosing/adjust", json={
            "ro_water_ml": 2000, "powder_g": 500, "element": "钙",
            "tank_liters": 550, "target_value": 420, "current_value": 350,
            "plan_days": 10, "current_dose_ml": 0
        })
        assert r.status_code == 200
        data = r.json()
        assert data["need_delta"] == 70
        assert data["final_dose"] == 62

    def test_dosing_log_crud(self, test_client):
        """滴定记录：添加→列表→删除。"""
        # 添加
        r = test_client.post("/api/dosing/log", json={
            "element": "KH", "dose_ml": 30, "action": "start",
            "note": "测试开始", "recorded_at": "2025-01-01"
        })
        assert r.status_code == 200
        log_id = r.json()["id"]

        # 列表
        r = test_client.get("/api/dosing/logs")
        assert r.status_code == 200
        logs = r.json()["logs"]
        assert any(l["id"] == log_id and l["action"] == "start" for l in logs)

        # 删除
        r = test_client.delete(f"/api/dosing/log/{log_id}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # 确认删除
        r = test_client.get("/api/dosing/logs")
        assert not any(l["id"] == log_id for l in r.json()["logs"])
