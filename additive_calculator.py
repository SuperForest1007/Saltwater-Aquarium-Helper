# -*- coding: utf-8 -*-
"""
海水添加剂试算表 - 核心数据模块

分组设计:
  - 核心组(最常用): 钙/KH/镁 —— 珊瑚日常消耗最大, 几乎每周都要补
  - 进阶组: 锶/钾 —— 视饲养方向补充
  - 微量组: 碘/溴/氟 —— 换水通常可维持
  - 营养组: NO3/磷酸盐 —— 仅提供可按化学计量验证的补充计算

安全边界:
  - 碳源降 NO3 受菌群、PO4、蛋分和溶氧等影响，不能套用分子量公式，故不提供自动剂量。
  - 铜药/福马林等治疗浓度随制剂和隔离缸条件变化，故不在通用计算器中提供。

每组带说明文字(detail), 帮助用户理解每个元素的意义。
"""

# 分组结构:
#   id: 分组标识
#   title: 分组标题
#   badge: 分组徽标(常用度提示)
#   collapsed: 默认是否折叠
#   note: 分组说明
#   elements: 元素列表
#     每个元素: {
#       name: 名称
#       ideal: 理想浓度
#       unit: 单位 (ppm/dkh)
#       detail: 一句话说明
#       tip: 补充说明(可选)
#       direction: up/down
#       conc_presets: 常用浓度选项
#       additives: [(名称, v1, v2, 饱和浓度或备注), ...]
#     }
ADDITIVE_GROUPS = [
    # ═══════════ 核心组: 钙/KH/镁 ═══════════
    {
        "id": "core",
        "title": "核心元素",
        "badge": "优先关注",
        "collapsed": False,
        "note": "礁岩缸常关注的三项；测试频率应按缸体阶段、消耗速度和近期调整决定，测试后也不等于必须补充。",
        "elements": [
            {
                "name": "KH 碱度",
                "ideal": "7-11",
                "unit": "dKH",
                "detail": "参与海水缓冲体系并影响钙化；短期大幅变化通常比处于参考区间内的细小差异更值得警惕。",
                "tip": "通用参考约 7-11dKH；具体目标需结合营养盐、珊瑚类型和长期稳定值，不必追求单一数字。",
                "direction": "up",
                "conc_presets": ["0.1", "0.5", "1", "2", "3", "4", "5"],
                "additives": [
                    ("碳酸氢钠 NaHCO3", 2.8, 84, "78"),
                ],
            },
            {
                "name": "钙 Ca",
                "ideal": "400-450",
                "unit": "ppm",
                "detail": "珊瑚骨骼和藻类生长的核心元素，SPS硬骨消耗尤其快。",
                "tip": "通用参考约 400-450ppm；请结合盐度、测试误差与碱度趋势判断，不建议仅凭一次读数追值。",
                "direction": "up",
                "conc_presets": ["5", "10", "20", "30", "40", "50", "75"],
                "additives": [
                    ("氯化钙 CaCl2·2H2O", 40, 147, "745"),
                    ("氯化钙(无水) CaCl2", 40, 111, "745"),
                    ("氢氧化钙 Ca(OH)2", 40, 74, "饱和1.85"),
                ],
            },
            {
                "name": "镁 Mg",
                "ideal": "1250-1400",
                "unit": "ppm",
                "detail": "参与维持钙、碱度与碳酸盐体系的稳定；镁偏低时碳酸钙更容易非生物沉淀。",
                "tip": "通用参考约 1250-1400ppm（随盐度而变），先确认盐度和复测结果再调整。",
                "direction": "up",
                "conc_presets": ["30", "50", "75", "100", "150", "200"],
                "additives": [
                    ("氯化镁 MgCl2·6H2O", 24, 204, "542"),
                    ("氯化镁(无水) MgCl2", 24, 98, "542"),
                    ("硫酸镁 MgSO4·7H2O", 24, 246, "255"),
                ],
            },
        ],
    },

    # ═══════════ 进阶组: 锶/钾 ═══════════
    {
        "id": "advanced",
        "title": "进阶元素",
        "badge": "视情况补充",
        "collapsed": True,
        "note": "取决于饲养方向（SPS/LPS）和生物密度，不必每周都测。",
        "elements": [
            {
                "name": "锶 Sr",
                "ideal": "8-9",
                "unit": "ppm",
                "detail": "可进入珊瑚骨骼，但其实际需求与独立补充收益并不能仅由钙消耗直接推定。",
                "tip": "海水中常见约 8ppm；没有可靠检测或明确方案时，不建议为追数值单独补充。",
                "direction": "up",
                "conc_presets": ["1", "2", "3", "5", "8", "10", "20"],
                "additives": [
                    ("氯化锶 SrCl2·6H2O", 88, 267, "538"),
                ],
            },
            {
                "name": "钾 K",
                "ideal": "380-420",
                "unit": "ppm",
                "detail": "海水中的主要离子之一；缺乏可靠测试依据时，不应把发色变化简单归因于钾。",
                "tip": "海水中常见约 400ppm；过量同样有风险，仅依据可靠检测和明确产品说明调整。",
                "direction": "up",
                "conc_presets": ["5", "10", "20", "30", "40", "50", "100"],
                "additives": [
                    ("氯化钾 KCl", 39, 74.4, "344"),
                ],
            },
        ],
    },

    # ═══════════ 微量组: 碘/溴/氟 ═══════════
    {
        "id": "trace",
        "title": "微量元素",
        "badge": "换水即可",
        "collapsed": True,
        "note": "多数情况下规律换水即可维持，单独补充需谨慎。",
        "elements": [
            {
                "name": "碘 I",
                "ideal": "0.06",
                "unit": "ppm",
                "detail": "参与蜕壳类生物和珊瑚新陈代谢，剂量极小。",
                "tip": "天然海水约 0.06ppm，补充请用低浓度溶液。",
                "direction": "up",
                "conc_presets": ["0.01", "0.02", "0.03", "0.05", "0.1", "0.2"],
                "additives": [
                    ("碘化钾 KI", 127, 166, ""),
                ],
            },
            {
                "name": "溴 Br",
                "ideal": "67",
                "unit": "ppm",
                "detail": "海水天然含量较高，一般不需要单独补充。",
                "tip": "天然海水约 67ppm，换水即可维持。",
                "direction": "up",
                "conc_presets": ["1", "5", "10", "20", "50"],
                "additives": [
                    ("溴化钾 KBr", 80, 119, ""),
                ],
            },
            {
                "name": "氟 F",
                "ideal": "1.3",
                "unit": "ppm",
                "detail": "微量元素，正常换水即可满足需求。",
                "tip": "天然海水约 1.3ppm，极少需要单独补充。",
                "direction": "up",
                "conc_presets": ["0.1", "0.2", "0.5", "1", "2"],
                "additives": [
                    ("氟化钠 NaF", 19, 42, ""),
                ],
            },
        ],
    },

    # ═══════════ 营养组: NO3/磷酸盐 ═══════════
    {
        "id": "nutrient",
        "title": "营养盐补充",
        "badge": "谨慎使用",
        "collapsed": True,
        "note": "仅提供可按化学计量验证的 NO3/PO4 补充；碳源降 NO3 不适用本计算器。",
        "elements": [
            {
                "name": "硝酸盐 NO3（提升）",
                "ideal": "2-10",
                "unit": "ppm",
                "detail": "NO3偏低或水体氮匮乏时使用：硝酸钙/硝酸钾补充氮源，让珊瑚恢复生长。",
                "tip": "仅在确认 NO3 偏低且明确需要补氮时使用；少量分次添加并复测，NO3 偏高时不要使用。",
                "direction": "up",
                "conc_presets": ["0.01", "0.02", "0.05", "0.1", "0.2", "0.5", "1"],
                "additives": [
                    ("硝酸钙 Ca(NO3)2·4H2O", 60, 236, "2660"),
                    ("硝酸钾 KNO3", 60, 101, "357"),
                ],
            },
            {
                "name": "磷酸盐 PO4",
                "ideal": "0.03-0.05",
                "unit": "ppm",
                "detail": "藻类养分，过高容易爆藻，需要控制。",
                "tip": "常见参考约 0.03-0.08ppm，但需结合系统类型与检测下限；长期不可检出可能增加营养限制风险，提升需谨慎。",
                "direction": "up",
                "conc_presets": ["0.01", "0.02", "0.05", "0.1", "0.2"],
                "additives": [
                    ("磷酸钾 K3PO4", 95, 212, "900"),
                ],
            },
        ],
    },

]

# 计算函数 ------------------------------------------------------------------

def calc_additive(water_liters: float, conc_delta: float, v1: float, v2: float) -> float:
    """
    计算添加剂用量(克)。
    formula: grams = round(s1 * (v2/v1) * t1) / 1000
    即 提升浓度 × (添加物分子量/元素当量) × 水量升 / 1000
    """
    import math
    if (water_liters is None or conc_delta is None or
            not isinstance(water_liters, (int, float)) or not isinstance(conc_delta, (int, float)) or
            not isinstance(v1, (int, float)) or not isinstance(v2, (int, float)) or
            not math.isfinite(water_liters) or not math.isfinite(conc_delta) or
            not math.isfinite(v1) or not math.isfinite(v2) or
            water_liters <= 0 or conc_delta <= 0 or v1 <= 0 or v2 <= 0):
        return 0.0
    return round(conc_delta * (v2 / v1) * water_liters) / 1000


def _fmt(v):
    """按量级自适应小数位：小数值保留更多位（PO4 0.008 显示 0.008，钙 376 显示 376）。"""
    av = abs(v)
    if av < 0.01:
        return f"{v:.3f}"
    if av < 1:
        return f"{v:.2f}"
    if av < 100:
        return f"{v:.1f}"
    return f"{v:.0f}"


def calc_dose_auto(water_liters: float, current_value: float, ideal_low: float,
                   ideal_high: float, v1: float, v2: float, unit: str = "ppm") -> dict:
    """
    【自动化】输入当前实测值，自动判断缺口并推荐添加量。
    如果当前值在理想范围内: 无需添加
    低于下限: 建议补到下限 (保守) 或中值 (推荐)
    高于上限: 提示偏高(不建议强行降低)
    """
    import math
    values = [water_liters, current_value, ideal_low, ideal_high, v1, v2]
    if (any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values) or
            water_liters <= 0 or current_value < 0 or ideal_low < 0 or ideal_high <= ideal_low or
            v1 <= 0 or v2 <= 0):
        return {
            "status": "invalid",
            "message": "参数无效：请检查实际水量、实测值、目标区间和添加物数据",
            "recommend_delta": 0,
            "grams": 0,
        }
    if current_value >= ideal_low and current_value <= ideal_high:
        return {
            "status": "ok",
            "message": f"当前 {_fmt(current_value)}{unit} 在理想范围 {_fmt(ideal_low)}-{_fmt(ideal_high)}{unit} 内，无需添加",
            "recommend_delta": 0,
            "grams": 0,
        }
    if current_value > ideal_high:
        return {
            "status": "high",
            "message": f"当前 {_fmt(current_value)}{unit} 高于理想上限 {_fmt(ideal_high)}{unit}，建议先观察/少量换水，暂不添加",
            "recommend_delta": 0,
            "grams": 0,
        }
    # 低于下限: 推荐补到理想中值
    mid = (ideal_low + ideal_high) / 2
    target = max(mid, ideal_low)
    delta = target - current_value
    grams = calc_additive(water_liters, delta, v1, v2)
    return {
        "status": "low",
        "message": f"当前 {_fmt(current_value)}{unit} 低于理想下限 {_fmt(ideal_low)}{unit}，建议补充 {_fmt(delta)}{unit} 到 {_fmt(target)}{unit}",
        "recommend_delta": round(delta, 2),
        "grams": grams,
    }


def calc_salt_add(water_liters: float, ppt_delta: float) -> str:
    """
    海水素添加量: 提升盐度需要加多少克海水素。
    经验系数 1.05~1.1 克/升/ppt
    """
    if not water_liters or not ppt_delta or ppt_delta <= 0:
        return ""
    lo = round(ppt_delta * water_liters * 1.05)
    hi = round(ppt_delta * water_liters * 1.1)
    return f"{lo}-{hi} 克"


def calc_water_adjust(current_ppt: float, target_ppt: float, water_liters: float) -> str:
    """
    盐度调节: 当前盐度 -> 目标盐度，需要加或减多少升海水。
    """
    if not current_ppt or not target_ppt or not water_liters or current_ppt <= 0:
        return ""
    delta = round(water_liters * (target_ppt - current_ppt) / current_ppt)
    if delta > 0:
        return f"添加海水 {delta} 升"
    elif delta < 0:
        return f"删除海水 {-delta} 升"
    return "无需调整"


def get_all_additives() -> list:
    """给前端返回全部数据。"""
    return ADDITIVE_GROUPS


if __name__ == "__main__":
    # 自测
    print("400L 水提升40ppm钙(氯化钙二水):", calc_additive(400, 40, 40, 147), "克")
    print("400L 水提升10ppm镁(氯化镁六水):", calc_additive(400, 10, 24, 204), "克")
    print("100L 水提升2dKH(碳酸氢钠):", calc_additive(100, 2, 2.8, 84), "克")
    # 自动化测试
    r = calc_dose_auto(400, 360, 400, 440, 40, 147)
    print("自动判断 Ca=360:", r["message"], "→", r["grams"], "克")
    r = calc_dose_auto(400, 420, 400, 440, 40, 147)
    print("自动判断 Ca=420:", r["message"])
    r = calc_dose_auto(400, 455, 400, 440, 40, 147)
    print("自动判断 Ca=455:", r["message"])
