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
            "todayBoard",       # 本缸今日海况
            "loadTodayDashboard",
            "todayEvidence",    # 专业判断依据
            "todayRhythm",      # 智能维护节奏
            "maintenanceModal", # 周期调整
            "completeMaintenance",
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

    def test_mobile_layout_guards(self):
        """关键手机布局保持紧凑，不被行内样式或超窄屏断点改乱。"""
        html = _read_index()
        assert ".tank-type-grid { grid-template-columns: 1fr; }" not in html
        assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in html
        assert '<div class="chart-controls" style=' not in html
        assert ".chart-controls { display: grid !important;" in html
        assert ".dose-row.consume-row { grid-template-columns: repeat(4, minmax(0, 1fr));" in html
        assert ".dose-head.consume-head { grid-template-columns: repeat(4, minmax(0, 1fr));" in html
        assert "const chartZoom = narrow" in html
        assert "return narrow ? month + '-' + day" in html
        assert "show: !narrow" in html
        assert 'class="est-row est-dim-row"' in html
        assert 'class="est-dim-inputs"' in html
        assert 'class="today-board tone-neutral"' in html
        assert "最多只列三项" in html
        assert "查看判断依据与维护节奏" in html

    def test_public_beta_stability_guards(self):
        """网络中断、零基准与历史内容都有明确保护。"""
        html = _read_index()
        assert 'id="connectionState"' in html
        assert "async function apiResponse" in html
        assert "method === 'GET' ? 1 : 0" in html
        assert "window.addEventListener('offline'" in html
        assert "@media (prefers-reduced-motion: reduce)" in html
        assert "const denominator = Math.abs(base)" in html
        assert "escapeToday(r.note || '')" in html
        assert "escapeToday(l.element)" in html
        assert "escapeToday(c.salt_brand || '—')" in html
        # 业务代码不得绕开统一请求层；唯一 fetch 位于 apiResponse 内。
        assert html.count("fetch(") == 1

    def test_salt_calculation_can_record_completed_water_change(self):
        html = _read_index()
        assert 'id="saltRecordBtn"' in html
        assert "recordCalculatedWaterChange" in html
        assert "salt_grams: grams" in html
        assert 'id="wcSaltGrams"' in html
        assert 'id="saltReferenceBody"' in html
        assert "updateSaltReferenceVisibility" in html
        assert "参考表已收起" in html

    def test_product_flow_hierarchy_and_single_sources(self):
        html = _read_index()
        simple = html[html.index('id="wqSimple"'):html.index('id="wqPro"')]
        pro = html[html.index('id="wqPro"'):html.index('<!-- Toast 提示 -->')]
        assert 'id="wqLinkage"' not in simple
        assert 'id="wqBalance"' not in simple
        assert 'id="wqLinkage"' in pro
        assert 'id="wqBalance"' in pro
        assert "一次纠偏" in html
        assert "长期维持" in html

        salt = html[html.index('id="panel-salt"'):html.index('id="panel-water"')]
        assert 'class="dose-card salt-calculator-card"' in salt
        assert 'class="dose-card water-change-history-card"' in salt
        assert '<details class="manual-record-details">' in salt
        assert "#panel-salt .salt-calculator-card { order: 1; }" in html
        assert "#panel-salt .water-change-history-card { order: 2; }" in html

        dosing_code = html[html.index('async function initDosing'):html.index('function setCalcTab')]
        assert "coef:" not in dosing_code
        assert "/api/dosing/daily" in dosing_code
        assert "localStorage.setItem('dosing_mix'" not in html
        assert "localStorage.setItem('tank_water'" not in html
        assert 'id="k_f" value=' not in html
        assert 'id="g_f" value=' not in html
        assert 'id="m_f" value=' not in html

    def test_dosing_copy_describes_plan_state_not_device_control(self):
        html = _read_index()
        assert "只记录方案状态，不会控制设备" in html
        assert "启用此方案" in html
        assert "停用此方案" in html
        assert "const actionMap = { start: '启用方案', end: '停用方案', adjust: '调整剂量' }" in html
        assert "days > 14" not in html
