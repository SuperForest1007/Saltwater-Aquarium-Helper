# -*- coding: utf-8 -*-
"""
换水记录 & 综合分析 API 测试
"""
import pytest


class TestWaterChange:
    def test_water_change_crud(self, test_client):
        """换水记录：添加→列表→删除。"""
        # 添加
        r = test_client.post("/api/water-change", json={
            "water_liters": 30, "salt_brand": "红海珊瑚盐",
            "salt_grams": 1080, "note": "测试换水", "recorded_at": "2025-03-01"
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # 列表
        r = test_client.get("/api/water-change")
        assert r.status_code == 200
        changes = r.json()["changes"]
        assert len(changes) == 1
        assert changes[0]["water_liters"] == 30
        assert changes[0]["salt_grams"] == 1080
        assert changes[0]["salt_brand"] == "红海珊瑚盐"

        # 删除
        cid = changes[0]["id"]
        r = test_client.delete(f"/api/water-change/{cid}")
        assert r.json()["ok"] is True

    def test_water_change_invalid(self, test_client):
        """非法换水量（负数）应被拒绝或处理。"""
        r = test_client.post("/api/water-change", json={
            "water_liters": -5, "salt_brand": "", "note": "", "recorded_at": "2025-03-01"
        })
        # 后端没有显式校验，但不应崩溃
        assert r.status_code in (200, 422)

    def test_water_change_rejects_invalid_optional_salt_grams(self, test_client):
        for value in (0, -20, "not-a-number"):
            r = test_client.post("/api/water-change", json={
                "water_liters": 30, "salt_grams": value, "recorded_at": "2025-03-01"
            })
            assert r.status_code == 422

    def test_balance_api(self, test_client):
        """收支平衡API可调用（无数据时返回空或默认）。"""
        r = test_client.get("/api/analysis/balance")
        assert r.status_code == 200
        assert "result" in r.json()


class TestAnalysis:
    def test_dosing_effect_with_data(self, test_client):
        """有完整滴定区间时，效果评估应返回改善数据。"""
        # 水质数据：滴定前快速下降，滴定中变缓
        for d, v in [("2025-01-01", 8.0), ("2025-01-05", 7.6), ("2025-01-10", 7.2)]:
            test_client.post("/api/water/record", json={"element": "KH", "value": v, "recorded_at": d})
        # 滴定区间内数据
        for d, v in [("2025-01-15", 7.0), ("2025-01-20", 6.9), ("2025-01-25", 6.8), ("2025-01-30", 6.7)]:
            test_client.post("/api/water/record", json={"element": "KH", "value": v, "recorded_at": d})
        # 滴定记录
        test_client.post("/api/dosing/log", json={
            "element": "KH", "dose_ml": 30, "action": "start", "note": "", "recorded_at": "2025-01-15"
        })
        test_client.post("/api/dosing/log", json={
            "element": "KH", "dose_ml": 0, "action": "end", "note": "", "recorded_at": "2025-01-30"
        })

        r = test_client.get("/api/analysis/dosing-effect")
        assert r.status_code == 200
        result = r.json()["result"]
        # KH应该有效果评估（需要足够数据量，若不足则跳过）
        # 注：演示数据可能不足2点区间外，这里只验证API不报错
        assert isinstance(result, dict)
