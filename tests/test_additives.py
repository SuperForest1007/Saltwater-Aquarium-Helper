# -*- coding: utf-8 -*-
"""
添加剂计算 & 试算表 API 测试
"""
import pytest


class TestAdditives:
    def test_get_additives(self, test_client):
        """试算表数据可获取，包含核心元素分组。"""
        r = test_client.get("/api/additives")
        assert r.status_code == 200
        data = r.json()
        assert "groups" in data
        groups = data["groups"]
        assert len(groups) >= 5  # 核心/进阶/微量/营养/治疗
        # 第一个分组是核心元素
        assert groups[0]["title"] == "核心元素"
        names = [e["name"] for e in groups[0]["elements"]]
        assert names == ["KH 碱度", "钙 Ca", "镁 Mg"]  # 顺序：KH→钙→镁

    def test_calc_additive_ca(self, test_client):
        """钙添加量计算：400L提40ppm氯化钙二水(40,147)。"""
        r = test_client.post("/api/calc/additive", json={
            "water_liters": 400, "conc_delta": 40, "v1": 40, "v2": 147
        })
        assert r.status_code == 200
        # round(40*(147/40)*400)/1000 = round(58800)/1000 = 58.8
        assert r.json()["grams"] == 58.8

    def test_calc_additive_kh(self, test_client):
        """KH添加：100L提2dKH碳酸氢钠(2.8,84)。"""
        r = test_client.post("/api/calc/additive", json={
            "water_liters": 100, "conc_delta": 2, "v1": 2.8, "v2": 84
        })
        assert r.status_code == 200
        # round(2*(84/2.8)*100)/1000 = round(6000)/1000 = 6.0
        assert r.json()["grams"] == 6.0

    def test_calc_additive_zero_guard(self, test_client):
        """非法输入（0水量）应返回0而不是报错。"""
        r = test_client.post("/api/calc/additive", json={
            "water_liters": 0, "conc_delta": 10, "v1": 40, "v2": 147
        })
        assert r.status_code == 200
        assert r.json()["grams"] == 0

    def test_calc_auto_judge(self, test_client):
        """自动判断：钙360低于下限，建议补充。"""
        r = test_client.post("/api/calc/auto", json={
            "water_liters": 400, "current_value": 360,
            "ideal_low": 400, "ideal_high": 440,
            "v1": 40, "v2": 147, "unit": "ppm"
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "low"
        assert data["grams"] > 0

    def test_calc_auto_in_range(self, test_client):
        """自动判断：值在范围内，无需添加。"""
        r = test_client.post("/api/calc/auto", json={
            "water_liters": 400, "current_value": 420,
            "ideal_low": 400, "ideal_high": 440,
            "v1": 40, "v2": 147, "unit": "ppm"
        })
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["grams"] == 0
