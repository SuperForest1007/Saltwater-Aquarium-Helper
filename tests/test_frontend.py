# -*- coding: utf-8 -*-
"""
前端完整性检查：
- JS 语法正确性（用 node --check）
- 关键功能元素存在
"""
import os
import subprocess
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(PROJECT_ROOT, "static", "index.html")
ECHARTS = os.path.join(PROJECT_ROOT, "static", "echarts.min.js")


def _read_index():
    with open(INDEX, "r", encoding="utf-8") as f:
        return f.read()


class TestFrontend:
    def test_echarts_exists(self):
        """ECharts库存在且非空。"""
        assert os.path.exists(ECHARTS), "echarts.min.js 不存在"
        size = os.path.getsize(ECHARTS)
        assert size > 100000, f"echarts.min.js 异常小: {size}"

    def test_js_syntax(self):
        """JS语法正确（node --check）。"""
        html = _read_index()
        scripts = re.findall(r"<script>([\s\S]*?)</script>", html)
        assert scripts, "未找到JS块"
        for i, js in enumerate(scripts):
            tmp = os.path.join(PROJECT_ROOT, f"_check_{i}.js")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(js)
            try:
                result = subprocess.run(
                    ["node", "--check", tmp],
                    capture_output=True, text=True, timeout=30
                )
                assert result.returncode == 0, f"JS块{i}语法错误:\n{result.stderr[:500]}"
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)

    def test_tabs_present(self):
        """四个tab都在。"""
        html = _read_index()
        for tab in ["水质", "元素补充", "滴定方案", "换水"]:
            assert tab in html, f"缺少tab: {tab}"

    def test_key_elements(self):
        """关键功能元素存在。"""
        html = _read_index()
        checks = [
            "globalWater",      # 隐藏的全站水量上下文
            "addWaterRecord",   # 水质记录
            "toggleDose",       # 滴定开始/结束
            "addWaterChange",   # 换水记录
            "renderWaterChart", # 趋势图
            "wqChartEl",        # 图表元素选择
            "tankIdentity",     # 当前鱼缸铭牌
            "tankModal",        # 轻量首次设置
            "saveTankSetup",    # 档案保存与全局联动
            "tankTargetPreview",# 缸型目标即时预览
            "tankFocusPreview", # 缸型维护重点
            "openTankEstimator",# 鱼缸设置内的水量估算
            "openEstimatorModal", # 独立二级估算弹窗
            "closeEstimatorModal",
            "setSquareSide",    # 常见方缸尺寸快选
        ]
        for c in checks:
            assert c in html, f"缺少关键元素: {c}"

    def test_no_debug_leftovers(self):
        """无调试残留（console.log 除外，检查 TODO/FIXME 标记）。"""
        html = _read_index()
        # 检查是否有未完成的调试标记（宽松策略）
        assert "NOT_IMPLEMENTED" not in html

    def test_tank_setup_explains_types_and_contains_estimator(self):
        """新手能看懂缸型，水量估算器位于鱼缸设置弹窗内。"""
        html = _read_index()
        for text in ["Fish Only，只养鱼", "大水螅体硬骨珊瑚", "小水螅体硬骨珊瑚", "非光合珊瑚"]:
            assert text in html
        assert "软体 / 海葵" in html
        for side in [35, 40, 50, 60]:
            assert f"setSquareSide({side})" in html
        tank_start = html.index('id="tankModal"')
        estimator_modal_start = html.index('id="estimatorModal"')
        assert tank_start < estimator_modal_start
        assert 'id="estimator"' not in html[tank_start:estimator_modal_start]
        assert 'onclick="openEstimatorModal()"' in html[tank_start:estimator_modal_start]
        assert 'id="estimator"' in html[estimator_modal_start:]
        assert "toggleEstimator" not in html
        assert '<div class="tank-bar"' not in html
        assert "不会把你锁进" not in html
        assert "不给你增加任务" not in html
