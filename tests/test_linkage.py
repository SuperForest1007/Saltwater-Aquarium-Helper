# -*- coding: utf-8 -*-
"""
元素联动诊断 单元测试
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from water_quality import analyze_element, analyze_all, linkage_diagnosis
from datetime import date


def _analyze(element, values, start=2025, month=1):
    """构建某元素的时序并分析。"""
    recs = [(date(start, month, 1 + i).isoformat(), v) for i, v in enumerate(values)]
    return analyze_element(recs, element)


class TestLinkageDiagnosis:
    def test_mg_low_ca_falling(self):
        """镁低+钙降 → 触发R1镁钙析出。"""
        analysis = {
            "镁": _analyze("镁", [1260, 1250, 1240, 1230, 1220]),
            "钙": _analyze("钙", [420, 415, 410, 405, 400]),
            "KH": _analyze("KH", [7.5, 7.5, 7.5, 7.5, 7.5]),
            "NO3": _analyze("NO3", [5, 5, 5, 5, 5]),
            "PO4": _analyze("PO4", [0.05, 0.05, 0.05, 0.05, 0.05]),
        }
        findings = linkage_diagnosis(analysis)
        assert any("镁" in f["title"] for f in findings)

    def test_no3_low_po4_high(self):
        """NO3低+PO4高 → 提示两项同时异常，不套固定比例。"""
        analysis = {
            "镁": _analyze("镁", [1280, 1280, 1280, 1280, 1280]),
            "钙": _analyze("钙", [420, 420, 420, 420, 420]),
            "KH": _analyze("KH", [7.5, 7.5, 7.5, 7.5, 7.5]),
            "NO3": _analyze("NO3", [0.5, 0.5, 0.5, 0.5, 0.5]),
            "PO4": _analyze("PO4", [0.15, 0.15, 0.15, 0.15, 0.15]),
        }
        findings = linkage_diagnosis(analysis)
        assert any("NO₃偏低且PO₄偏高" in f["title"] for f in findings)

    def test_ca_high_kh_low(self):
        """钙高+KH低 → 提示复核，而不是直接断言发生沉淀。"""
        analysis = {
            "镁": _analyze("镁", [1280, 1280, 1280, 1280, 1280]),
            "钙": _analyze("钙", [455, 455, 455, 455, 455]),
            "KH": _analyze("KH", [6.5, 6.5, 6.5, 6.5, 6.5]),
            "NO3": _analyze("NO3", [5, 5, 5, 5, 5]),
            "PO4": _analyze("PO4", [0.05, 0.05, 0.05, 0.05, 0.05]),
        }
        findings = linkage_diagnosis(analysis)
        assert any("钙偏高且碱度偏低" in f["title"] for f in findings)

    def test_normal_no_findings(self):
        """全部正常 → 无发现。"""
        analysis = {
            "镁": _analyze("镁", [1280, 1280, 1280, 1280, 1280]),
            "钙": _analyze("钙", [420, 420, 420, 420, 420]),
            "KH": _analyze("KH", [7.5, 7.5, 7.5, 7.5, 7.5]),
            "NO3": _analyze("NO3", [5, 5, 5, 5, 5]),
            "PO4": _analyze("PO4", [0.05, 0.05, 0.05, 0.05, 0.05]),
        }
        findings = linkage_diagnosis(analysis)
        assert findings == []

    def test_priority_sorted(self):
        """发现按优先级降序。"""
        analysis = {
            "镁": _analyze("镁", [1240, 1230, 1220, 1210, 1200]),
            "钙": _analyze("钙", [420, 415, 410, 405, 400]),
            "KH": _analyze("KH", [7.5, 7.4, 7.3, 7.2, 7.1]),
            "NO3": _analyze("NO3", [0.5, 0.5, 0.5, 0.5, 0.5]),
            "PO4": _analyze("PO4", [0.15, 0.15, 0.15, 0.15, 0.15]),
        }
        findings = linkage_diagnosis(analysis)
        prios = [f["priority"] for f in findings]
        assert prios == sorted(prios, reverse=True)
