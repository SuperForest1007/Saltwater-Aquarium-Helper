# -*- coding: utf-8 -*-
"""
目标调节 API（滴定用量调节）测试
"""


class TestAdjustDose:
    def test_adjust_increase(self, test_client):
        """目标高于当前：需每天增加滴量。"""
        r = test_client.post("/api/dosing/adjust", json={
            "ro_water_ml": 1000, "powder_g": 50, "element": "KH",
            "tank_liters": 550, "target_value": 9.0, "current_value": 7.5,
            "plan_days": 10, "current_dose_ml": 0
        })
        assert r.status_code == 200
        d = r.json()
        assert d["need_delta"] > 0          # 需升 1.5 dKH
        assert d["daily_delta"] > 0
        assert d["need_dose"] > 0           # 每天需增加的 ml
        assert d["final_dose"] >= d["need_dose"]

    def test_adjust_decrease(self, test_client):
        """目标低于当前：need_dose 为负方向（不强制加滴）。"""
        r = test_client.post("/api/dosing/adjust", json={
            "ro_water_ml": 1000, "powder_g": 50, "element": "KH",
            "tank_liters": 550, "target_value": 8.0, "current_value": 11.0,
            "plan_days": 7, "current_dose_ml": 20
        })
        assert r.status_code == 200
        d = r.json()
        assert d["need_delta"] < 0
        # need_dose 向下取整为 0 或负 → 说明需减少（前端会提示暂停/减少）
        assert d["final_dose"] <= 20

    def test_adjust_invalid(self, test_client):
        """非法参数不崩溃。"""
        r = test_client.post("/api/dosing/adjust", json={
            "ro_water_ml": 1000, "powder_g": 50, "element": "KH",
            "tank_liters": 0, "target_value": 9, "current_value": 8,
            "plan_days": 0, "current_dose_ml": 0
        })
        assert r.status_code == 200
        assert r.json()["need_dose"] == 0

    def test_adjust_roundtrip_math(self, test_client):
        """数值一致性：need_dose 应等于 水量×日增减×每ml提升量。"""
        # 已知配液 1000ml/50g KH → 稀释比 20，系数0.03 → 每ml提升 0.6
        r = test_client.post("/api/dosing/adjust", json={
            "ro_water_ml": 1000, "powder_g": 50, "element": "KH",
            "tank_liters": 100, "target_value": 9.0, "current_value": 8.0,
            "plan_days": 10, "current_dose_ml": 0
        })
        d = r.json()
        # daily_delta = 0.1 dKH/天；每ml提升 20×0.03=0.6；need_dose = 100×0.1×0.6 = 6
        assert abs(d["need_dose"] - 6) <= 1
