# -*- coding: utf-8 -*-
"""
智能建议增强测试：supplement 补充量信息 + 建议与操作联动
"""


class TestAdviceSupplement:
    def test_supplement_when_low(self, test_client):
        """元素偏低时，建议应带 supplement（需补数值/目标值）。"""
        # KH 低于下限（8.0），3条下降记录
        for d, v in [("2025-01-01", 7.6), ("2025-01-08", 7.3), ("2025-01-15", 7.0)]:
            test_client.post("/api/water/record", json={"element": "KH", "value": v, "recorded_at": d})
        r = test_client.get("/api/water/analysis")
        advice = r.json()["analysis"]["KH"]["advice"]
        assert advice["supplement"] is not None
        assert advice["supplement"]["delta"] > 0
        assert advice["supplement"]["unit"] == "dKH"
        # 目标值应在理想范围内（补到中值 10）
        assert 8 <= advice["supplement"]["target"] <= 12

    def test_no_supplement_when_ok(self, test_client):
        """元素正常时无 supplement。"""
        for d, v in [("2025-01-01", 8.5), ("2025-01-08", 8.6), ("2025-01-15", 8.5)]:
            test_client.post("/api/water/record", json={"element": "KH", "value": v, "recorded_at": d})
        r = test_client.get("/api/water/analysis")
        advice = r.json()["analysis"]["KH"]["advice"]
        assert advice["supplement"] is None

    def test_no_supplement_when_high(self, test_client):
        """元素偏高时无 supplement（不应建议补充）。"""
        for d, v in [("2025-01-01", 470), ("2025-01-08", 475), ("2025-01-15", 472)]:
            test_client.post("/api/water/record", json={"element": "钙", "value": v, "recorded_at": d})
        r = test_client.get("/api/water/analysis")
        advice = r.json()["analysis"]["钙"]["advice"]
        assert advice["supplement"] is None

    def test_supplement_consistent_with_ideals(self, test_client):
        """supplement 的 target 必须与理想范围一致（防数值漂移）。"""
        # 镁偏低
        for d, v in [("2025-01-01", 1250), ("2025-01-08", 1240), ("2025-01-15", 1230)]:
            test_client.post("/api/water/record", json={"element": "镁", "value": v, "recorded_at": d})
        r = test_client.get("/api/water/analysis")
        advice = r.json()["analysis"]["镁"]["advice"]
        ideals = test_client.get("/api/water/ideals").json()["ideals"]["镁"]
        assert ideals["low"] <= advice["supplement"]["target"] <= ideals["high"]
        # delta = 目标 - 当前
        current = r.json()["analysis"]["镁"]["current"]
        assert abs(advice["supplement"]["delta"] - (advice["supplement"]["target"] - current)) < 0.1
