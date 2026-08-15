# -*- coding: utf-8 -*-
"""
计算引擎单元测试：算法正确性（不依赖API）
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from additive_calculator import (
    calc_additive, calc_salt_add, calc_water_adjust, calc_dose_auto,
    get_all_additives,
)
from dosing_calculator import (
    mix_concentration, per_ml_effect, daily_dose, adjust_dose,
)
from water_quality import analyze_element


class TestAdditiveCalculator:
    def test_formula_ca(self):
        """钙公式：round(40*(147/40)*400)/1000 = 58.8。"""
        assert calc_additive(400, 40, 40, 147) == 58.8

    def test_formula_kh(self):
        """KH公式：round(2*(84/2.8)*100)/1000 = 6.0。"""
        assert calc_additive(100, 2, 2.8, 84) == 6.0

    def test_zero_input(self):
        """0输入返回0。"""
        assert calc_additive(0, 10, 40, 147) == 0
        assert calc_additive(400, 0, 40, 147) == 0

    def test_salt_add(self):
        """海水素：200L提2ppt → 420-440克。"""
        r = calc_salt_add(200, 2)
        assert r == "420-440 克"

    def test_water_adjust(self):
        """盐度调节：33→35, 300L → 添加海水18升。"""
        r = calc_water_adjust(33, 35, 300)
        assert "18" in r

    def test_dose_auto_low(self):
        """自动判断：低于下限建议补充。"""
        r = calc_dose_auto(400, 360, 400, 440, 40, 147, "ppm")
        assert r["status"] == "low"
        assert r["grams"] > 0

    def test_dose_auto_ok(self):
        """自动判断：范围内无需添加。"""
        r = calc_dose_auto(400, 420, 400, 440, 40, 147, "ppm")
        assert r["status"] == "ok"
        assert r["grams"] == 0

    def test_all_additives_complete(self):
        """全部添加剂数据完整（每个元素有添加物）。"""
        groups = get_all_additives()
        assert len(groups) == 5
        for g in groups:
            assert g["elements"], f"分组 {g['title']} 无元素"
            for e in g["elements"]:
                assert e["additives"], f"元素 {e['name']} 无添加物"
                assert e["conc_presets"], f"元素 {e['name']} 无浓度预设"


class TestDosingCalculator:
    def test_mix_concentration(self):
        """配液浓度：2000/500 = 4。"""
        assert mix_concentration(2000, 500) == 4

    def test_per_ml_effect(self):
        """每ml提升：钙 4*0.004 = 0.016。"""
        assert per_ml_effect(2000, 500, "钙") == 0.016

    def test_daily_dose(self):
        """每天滴定量：550L KH 8→7.5 7天 → 24。"""
        assert daily_dose(1000, 50, "KH", 550, 8.0, 7.5, 7) == 24

    def test_adjust_dose(self):
        """调节：钙目标420当前350 → 62。"""
        r = adjust_dose(2000, 500, "钙", 550, 420, 350, 10)
        assert r["final_dose"] == 62


class TestWaterQualityEngine:
    def test_analyze_falling(self):
        """持续下降 → 趋势falling + 建议。"""
        from datetime import date
        recs = [(date(2025, 1, 1 + i).isoformat(), 8.0 - i * 0.1) for i in range(10)]
        r = analyze_element(recs, "KH")
        assert r["signals"]["direction"] == "falling"
        assert r["advice"]["summary"]

    def test_analyze_stable(self):
        """平稳数据 → 趋势stable。"""
        from datetime import date
        recs = [(date(2025, 1, i + 1).isoformat(), 7.5) for i in range(8)]
        r = analyze_element(recs, "KH")
        assert r["signals"]["direction"] == "stable"

    def test_analyze_no_data(self):
        """无数据 → no_data状态。"""
        r = analyze_element([], "KH")
        assert r["status"] == "no_data"

    def test_analyze_anomaly(self):
        """异常骤降 → anomaly检测。"""
        from datetime import date
        import random
        random.seed(42)
        recs = [(date(2025, 1, i + 1).isoformat(), 7.5 + random.uniform(-0.1, 0.1)) for i in range(9)]
        recs.append((date(2025, 1, 10).isoformat(), 5.5))
        r = analyze_element(recs, "KH")
        assert r["signals"]["anomaly"] == "down"

    def test_analyze_prediction(self):
        """趋势预测：还在范围内但下降 → 预测。"""
        from datetime import date
        recs = [(date(2025, 1, 1 + i).isoformat(), 7.6 - i * 0.05) for i in range(8)]
        r = analyze_element(recs, "KH")
        assert r["prediction"] is not None
        assert "跌破" in r["prediction"]["msg"]
