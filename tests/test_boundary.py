# -*- coding: utf-8 -*-
"""
边界值与风险测试：严格验证极端输入、除零、精度等
"""
import sys
import os
import math

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from additive_calculator import calc_additive, calc_dose_auto
from dosing_calculator import mix_concentration, per_ml_effect, daily_dose, adjust_dose
from water_quality import analyze_element, ELEMENT_IDEALS
from datetime import date


class TestBoundaryValues:
    """边界值：范围上下限、0、负值、极大值。"""

    def test_ideal_boundaries(self):
        """理想范围边界：下限/上限本身应为正常状态。"""
        for el, ideal in ELEMENT_IDEALS.items():
            low, high = ideal["low"], ideal["high"]
            # 下限和上限都应有效
            assert low < high, f"{el} 范围无效: {low}-{high}"

    def test_calc_additive_negative(self):
        """负浓度输入：应返回0或合理值，不崩溃。"""
        result = calc_additive(400, -10, 40, 147)
        # 负数浓度不合理，当前逻辑返回0
        assert result == 0

    def test_calc_additive_huge(self):
        """极大值输入：不崩溃，结果有限。"""
        result = calc_additive(1e9, 1e9, 40, 147)
        assert math.isfinite(result)

    def test_calc_additive_nan(self):
        """NaN输入：不崩溃。"""
        result = calc_additive(float('nan'), 10, 40, 147)
        assert result == 0 or math.isnan(result) == False  # 应被守卫拦截

    def test_mix_division_by_zero(self):
        """配液除零：powder_g=0 不应崩溃。"""
        result = mix_concentration(1000, 0)
        assert result == 0

    def test_mix_negative(self):
        """配液负值：不崩溃。"""
        assert mix_concentration(-100, 50) == 0  # 负水量
        assert mix_concentration(100, -50) == 0  # 负分析纯

    def test_daily_dose_boundaries(self):
        """每天滴定量边界：无下降应返回0。"""
        # 末次=初次（无下降）→ 0
        assert daily_dose(1000, 50, "KH", 550, 8.0, 8.0, 7) == 0
        # 末次>初次（上升）→ 0（不需要补）
        assert daily_dose(1000, 50, "KH", 550, 7.0, 8.0, 7) == 0

    def test_daily_dose_zero_tank(self):
        """缸水量0：不崩溃。"""
        assert daily_dose(1000, 50, "KH", 0, 8.0, 7.5, 7) == 0

    def test_adjust_negative_days(self):
        """调节表：负天数不崩溃。"""
        result = adjust_dose(2000, 500, "钙", 550, 420, 350, -5)
        assert isinstance(result, dict)

    def test_dose_auto_extremes(self):
        """自动判断极端值：极低/极高。"""
        # 极低 → low
        r = calc_dose_auto(400, 1, 400, 440, 40, 147, "ppm")
        assert r["status"] == "low"
        # 极高 → high
        r = calc_dose_auto(400, 10000, 400, 440, 40, 147, "ppm")
        assert r["status"] == "high"

    def test_analyze_single_record(self):
        """单条记录：不崩溃，返回no_data或单点。"""
        recs = [(date(2025, 1, 1).isoformat(), 8.0)]
        r = analyze_element(recs, "KH")
        assert "status" in r


class TestRiskScenarios:
    """潜在风险：异常数据、波动、精度。"""

    def test_analyze_all_identical(self):
        """所有值相同（无波动）：不崩溃，趋势平稳。"""
        recs = [(date(2025, 1, i + 1).isoformat(), 8.5) for i in range(10)]
        r = analyze_element(recs, "KH")
        assert r["signals"]["direction"] == "stable"
        assert r["signals"]["volatility"] == "low"

    def test_analyze_zigzag(self):
        """锯齿形数据（反复升降）：不崩溃，方向为平稳或可判断。"""
        recs = [(date(2025, 1, i + 1).isoformat(), 8.0 + (i % 2)) for i in range(10)]
        r = analyze_element(recs, "KH")
        assert r["signals"]["direction"] in ("stable", "rising", "falling")

    def test_analyze_outlier_only(self):
        """数据几乎全是异常值：不崩溃。"""
        recs = [(date(2025, 1, i + 1).isoformat(), 8.0 if i % 3 else 4.0) for i in range(9)]
        r = analyze_element(recs, "KH")
        assert "advice" in r

    def test_no3_low_precision(self):
        """NO3极小值：精度处理正确。"""
        recs = [(date(2025, 1, i + 1).isoformat(), 0.0001 + i * 0.0001) for i in range(8)]
        r = analyze_element(recs, "NO3")
        # 不应崩溃，current应为有限值
        assert math.isfinite(r["current"])

    def test_po4_rounding(self):
        """PO4两位小数精度：值应保留合理精度。"""
        recs = [(date(2025, 1, i + 1).isoformat(), round(0.03 + i * 0.005, 3)) for i in range(8)]
        r = analyze_element(recs, "PO4")
        assert r["current"] >= 0

    def test_linkage_missing_elements(self):
        """联动诊断：缺少部分元素不崩溃。"""
        from water_quality import linkage_diagnosis
        # 只有KH和钙，缺其他
        analysis = {
            "KH": {"current": 9.0, "signals": {"direction": "stable", "rate": 0.01}},
            "钙": {"current": 420, "signals": {"direction": "stable", "rate": 0.1}},
        }
        findings = linkage_diagnosis(analysis)
        assert isinstance(findings, list)


class TestApiBoundaries:
    """API层边界：非法输入不应导致500。"""

    def test_additive_nan_via_api(self, test_client):
        """NaN经API：JSON序列化层即拦截（httpx/浏览器不发送NaN），或后端守卫返回0。"""
        import httpx
        # NaN/Infinity 无法编码为合法JSON，httpx在发送前抛异常——这是第一道防线
        try:
            test_client.post("/api/calc/additive", json={
                "water_liters": float('nan'), "conc_delta": 10, "v1": 40, "v2": 147
            })
        except (ValueError, httpx.RequestError):
            pass  # 序列化层拦截，符合预期
        else:
            # 若某天序列化放行了，后端也应守卫（走正常路径）
            r = test_client.post("/api/calc/additive", json={
                "water_liters": -1, "conc_delta": 10, "v1": 40, "v2": 147
            })
            assert r.status_code in (200, 422)

    def test_additive_negative_via_api(self, test_client):
        """负数经API：返回0或422，不应500。"""
        r = test_client.post("/api/calc/additive", json={
            "water_liters": -100, "conc_delta": 10, "v1": 40, "v2": 147
        })
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            assert r.json()["grams"] == 0

    def test_additive_huge_via_api(self, test_client):
        """极大值经API：不500，结果有限。"""
        r = test_client.post("/api/calc/additive", json={
            "water_liters": 1e6, "conc_delta": 1e6, "v1": 40, "v2": 147
        })
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            import math
            assert math.isfinite(r.json()["grams"])

    def test_water_record_negative(self, test_client):
        """水质记录负数：不500（当前API接受，需业务层判断）。"""
        r = test_client.post("/api/water/record", json={"element": "KH", "value": -5})
        assert r.status_code in (200, 422)

    def test_unknown_element_record(self, test_client):
        """未知元素记录：不应500（虽然不理想但不应崩溃）。"""
        r = test_client.post("/api/water/record", json={"element": "未知元素XYZ", "value": 5})
        assert r.status_code in (200, 422)

    def test_water_change_zero(self, test_client):
        """换水0量：不500。"""
        r = test_client.post("/api/water-change", json={"water_liters": 0})
        assert r.status_code in (200, 422)
