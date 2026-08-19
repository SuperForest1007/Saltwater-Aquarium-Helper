# -*- coding: utf-8 -*-
"""
水质智能分析引擎
=================
分层信号检测(L1-L5) + 规则组合引擎 + 动态建议生成

数据输入: 某元素的时序记录 [(日期str, 数值float), ...]
理想范围: 由元素定义传入 (ideal_low, ideal_high, unit)

L1 单点判断: 当前值 vs 理想范围
L2 趋势感知: 线性回归斜率(每天变化量/方向)
L3 异常检测: z-score 对比历史波动分布
L4 组合诊断: 多信号匹配规则模式 → 动态建议
L5 趋势预测: 线性外推预测"X天后跌破/突破范围"
"""
import copy
import math
from datetime import datetime, timedelta


# ============ 理想范围定义 ============
ELEMENT_IDEALS = {
    "KH":  {"low": 7.0, "high": 11.0, "unit": "dKH", "display": "KH 碱度",
            "hint": "通用参考约 7–11dKH；营养盐和珊瑚类型不同，合适的长期目标也会变，稳定比贴住某个数字更重要"},
    "钙":  {"low": 400, "high": 450, "unit": "ppm", "display": "钙 Ca",
            "hint": "通用参考约 400–450ppm；把盐度、测试误差和碱度趋势放在一起看，单次读数不用急着追"},
    "镁":  {"low": 1250, "high": 1400, "unit": "ppm", "display": "镁 Mg",
            "hint": "通用参考约 1250–1400ppm，并会随盐度变化；盐度和镁一起复测，心里更有底"},
    "NO3": {"low": 2.0, "high": 10.0, "unit": "ppm", "display": "硝酸盐 NO₃",
            "hint": "过低或过高都可能带来问题；应结合PO4、投喂、生物负载和缸体类型分别判断，不以固定比例作为追数值目标"},
    "PO4": {"low": 0.03, "high": 0.08, "unit": "ppm", "display": "磷酸盐 PO₄",
            "hint": "常见参考约 0.03–0.08ppm；长期测不到可能出现营养限制，也要留意试剂检测下限和系统类型"},
}

# 不同缸型的“起始参考范围”。它们用于个性化分析，不代替测试剂说明、
# 盐度校准和对具体生物状态的观察；用户自定义目标会覆盖这里的上下限。
TANK_TYPE_TARGETS = {
    "FOT": {
        "KH": (7.0, 11.0), "钙": (380, 450), "镁": (1200, 1400),
        "NO3": (2.0, 30.0), "PO4": (0.03, 0.30),
    },
    "软体": {
        "KH": (7.0, 11.0), "钙": (380, 450), "镁": (1250, 1400),
        "NO3": (2.0, 20.0), "PO4": (0.03, 0.15),
    },
    "LPS": {
        "KH": (7.5, 10.0), "钙": (400, 450), "镁": (1250, 1400),
        "NO3": (2.0, 15.0), "PO4": (0.03, 0.12),
    },
    "SPS": {
        "KH": (7.0, 9.0), "钙": (400, 450), "镁": (1250, 1400),
        "NO3": (1.0, 10.0), "PO4": (0.02, 0.08),
    },
    "NPS": {
        "KH": (7.0, 11.0), "钙": (380, 450), "镁": (1250, 1400),
        "NO3": (2.0, 25.0), "PO4": (0.03, 0.20),
    },
    "混养": {
        "KH": (7.0, 11.0), "钙": (400, 450), "镁": (1250, 1400),
        "NO3": (2.0, 10.0), "PO4": (0.03, 0.08),
    },
}

TANK_TYPE_DESCRIPTIONS = {
    "FOT": "只养鱼，或以鱼为主；重点看过滤负担和营养盐",
    "软体": "皮革、菇、纽扣这类软体，或以红奶嘴等海葵为主。海葵不是软体珊瑚，这里先共用一套基础水质参考",
    "LPS": "脑、糖果脑、火柴头这类大水螅体硬骨珊瑚为主",
    "SPS": "鹿角、鸟巢这类小水螅体硬骨珊瑚为主，更看重 KH 稳定",
    "NPS": "太阳花、海树这类非光合珊瑚为主，主要靠投喂",
    "混养": "鱼和几类珊瑚都有；暂时分不清也可以先选这个",
}

TANK_TYPE_FOCUS = {
    "FOT": ["先看过滤负担和 NO₃ / PO₄", "钙、镁通常不用频繁追"],
    "软体": ["先稳住温度、盐度和光照", "营养盐别长期测不到"],
    "LPS": ["留意 KH、钙的长期消耗", "保持适度营养和稳定水流"],
    "SPS": ["重点看 KH 的日常波动", "钙化消耗和营养盐都要连续记录"],
    "NPS": ["投喂量和过滤输出是主线", "NO₃ / PO₄ 范围只能作粗参考"],
    "混养": ["先照顾缸里最敏感的生物", "发现长期消耗后再收窄目标"],
}


def get_ideals_for_tank(tank_type="混养", custom_targets=None):
    """返回缸型参考范围，并安全应用用户自定义的 low/high。"""
    ideals = copy.deepcopy(ELEMENT_IDEALS)
    profile = TANK_TYPE_TARGETS.get(tank_type, TANK_TYPE_TARGETS["混养"])
    for element, (low, high) in profile.items():
        ideals[element]["low"] = low
        ideals[element]["high"] = high
        salt_note = "钙、镁读数还会跟着盐度变化，盐度和读数一起核对更稳妥；" if element in {"钙", "镁"} else ""
        ideals[element]["hint"] = (
            f"{tank_type}缸可以先把 {low}–{high}{ideals[element]['unit']} 当作参考。"
            f"{salt_note}如果缸里状态正常、走势也稳定，不用为了贴数字来回调整。"
        )
    for element, target in (custom_targets or {}).items():
        if element not in ideals or not isinstance(target, dict):
            continue
        try:
            low, high = float(target["low"]), float(target["high"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(low) and math.isfinite(high) and 0 <= low < high:
            ideals[element]["low"] = low
            ideals[element]["high"] = high
            ideals[element]["hint"] = "这里显示的是你自己设的目标，后面可以跟着缸里的变化再调。"
    return ideals


# ============ 基础统计 ============
def _mean(xs):
    return sum(xs) / len(xs) if xs else 0


def _std(xs):
    if len(xs) < 2:
        return 0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _linreg(xs, ys):
    """最小二乘线性回归, 返回 (斜率, 截距, R²)"""
    n = len(xs)
    if n < 2:
        return 0, 0, 0
    mx, my = _mean(xs), _mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0, my, 0
    slope = sxy / sxx
    inter = my - slope * mx
    # R²
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + inter)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    return slope, inter, r2


# ============ L1-L5 信号检测 ============
def analyze_element(records, element, ideal=None):
    """
    对单个元素做全链路分析, 返回结构化信号。
    records: [(date_str, value), ...] 按时间升序
    """
    if ideal is None:
        ideal = ELEMENT_IDEALS.get(element, {"low": 0, "high": 1, "unit": "ppm"})
    low, high, unit = ideal["low"], ideal["high"], ideal["unit"]

    if not records:
        return {"element": element, "status": "no_data", "signals": {}, "advice": "这个项目还没记录。多记几次，趋势才会慢慢显出来。"}

    # 展示保留完整记录；判断使用近期窗口，避免几个月前的数据冲淡刚发生的变化。
    all_dates = [datetime.fromisoformat(d) if isinstance(d, str) else d for d, _ in records]
    all_values = [float(v) for _, v in records]
    window_start = all_dates[-1] - timedelta(days=60)
    recent_pairs = [(d, v) for d, v in zip(all_dates, all_values) if d >= window_start][-20:]
    if len(recent_pairs) < 2:
        recent_pairs = list(zip(all_dates, all_values))[-2:]
    dates = [item[0] for item in recent_pairs]
    values = [item[1] for item in recent_pairs]

    # 转为"天"序号
    t0 = dates[0]
    xs = [(d - t0).total_seconds() / 86400.0 for d in dates]
    ys = values

    cur = ys[-1]
    slope, inter, r2 = _linreg(xs, ys)

    # ---- L1: 单点状态 ----
    if cur < low:
        l1 = "low"
        l1_msg = f"当前 {cur:.1f}{unit} 低于本缸参考下限 {low}{unit}"
    elif cur > high:
        l1 = "high"
        l1_msg = f"当前 {cur:.1f}{unit} 高于本缸参考上限 {high}{unit}"
    else:
        l1 = "ok"
        l1_msg = f"当前 {cur:.1f}{unit} 在本缸参考范围 {low}-{high}{unit} 内"

    # ---- L2: 趋势 ----
    # 斜率单位: 每天变化量
    rate = slope
    if abs(rate) < 0.02 * (high - low) / 10:  # 阈值: 相对范围微小变化
        direction = "stable"
        direction_cn = "平稳"
    elif rate > 0:
        direction = "rising"
        direction_cn = "上升"
    else:
        direction = "falling"
        direction_cn = "下降"

    # ---- 趋势加速度: 对比最近1/3段 vs 整体 ----
    accel = 0
    if len(xs) >= 6:
        cut = len(xs) // 3
        recent = xs[-cut:], ys[-cut:]
        overall = xs, ys
        s_recent, _, _ = _linreg(recent[0], recent[1])
        accel = s_recent - slope
    accelerating = abs(accel) > abs(slope) * 0.5 if slope != 0 else False

    # ---- L3: 异常检测 (z-score) ----
    anomaly = None
    if len(ys) >= 4:
        hist = ys[:-1]
        m, s = _mean(hist), _std(hist)
        if s > 0:
            z = (cur - m) / s
            if abs(z) >= 2.5:
                anomaly = "up" if z > 0 else "down"
    anomaly_cn = {"up": "异常跳升", "down": "异常骤降"}.get(anomaly, "")

    # ---- L3b: 波动幅度 ----
    vol = _std(ys)
    # 波动判定: 用"标准差/当前值"的相对比例，对小数值元素(PO4/NO3)更公平
    # 大数值元素(钙/镁几百ppm)波动几十ppm是正常的，小数值元素(0.05ppm)波动0.01也是正常的
    rel_vol = vol / cur if cur > 0 else 0
    if rel_vol > 0.15:        # 相对当前值波动>15%
        volatility = "high"
    elif rel_vol < 0.03:      # <3% 很平稳
        volatility = "low"
    else:
        volatility = "normal"
    # 波动值按量级自适应保留小数位（小数值元素显示更多位）
    vol_display = round(vol, 3) if cur < 1 else round(vol, 1)

    # ---- L5: 预测 ----
    prediction = None
    if slope != 0 and len(xs) >= 2:
        # 预测跌破/突破的天数
        if slope < 0 and cur > low:
            days_to_low = (low - cur) / slope
            if days_to_low > 0:
                eta = (dates[-1] + timedelta(days=days_to_low)).date()
                prediction = {"direction": "down", "days": days_to_low, "target": low, "date": str(eta),
                              "msg": f"按当前速率(每天{abs(slope):.2f}{unit})，预计约{max(1, round(days_to_low))}天后跌破{low}{unit}({eta})"}
        elif slope > 0 and cur < high:
            days_to_high = (high - cur) / slope
            if days_to_high > 0:
                eta = (dates[-1] + timedelta(days=days_to_high)).date()
                prediction = {"direction": "up", "days": days_to_high, "target": high, "date": str(eta),
                              "msg": f"按当前速率(每天{abs(slope):.2f}{unit})，预计约{max(1, round(days_to_high))}天后升破{high}{unit}({eta})"}

    # ---- L4: 规则组合 ----
    signals = {
        "level": l1, "level_msg": l1_msg,
        "direction": direction, "direction_cn": direction_cn,
        "rate": round(abs(rate), 3), "rate_signed": round(rate, 3),
        "accelerating": accelerating, "accel": round(accel, 3),
        "anomaly": anomaly, "anomaly_cn": anomaly_cn,
        "volatility": volatility, "vol": vol_display,
        "r2": round(r2, 3),
        "current": round(cur, 2),
        "count": len(records),
        "trend_count": len(values),
        "trend_days": max(0, (dates[-1] - dates[0]).days),
    }
    advice = _compose_advice(element, signals, low, high, unit, prediction)

    return {
        "element": element,
        "display": ideal.get("display", element),
        "ideal": {"low": low, "high": high, "unit": unit},
        "status": l1,
        "current": round(cur, 2),
        "signals": signals,
        "prediction": prediction,
        "advice": advice,
        "records": [{"date": d.strftime("%Y-%m-%d"), "value": v, "ts": int(d.timestamp() * 1000)} for d, v in zip(all_dates, all_values)],
    }


# ============ L4: 规则引擎 + 动态建议 ============
def _compose_advice(element, s, low, high, unit, prediction=None):
    """
    信号组合 → 建议。不是固定模板: 结论由数值动态生成,
    动作从动作库挑选并代入实际参数。
    """
    parts = []
    prio = 0
    supplement = None  # 偏低时记录"需要补多少"，供前端换算克数/滴定量
    low_cn = {"KH": "碱度", "钙": "钙", "镁": "镁", "NO3": "硝酸盐", "PO4": "磷酸盐"}.get(element, element)

    def _supplement_info():
        """偏低 → 计算补到参考中值的用量。返回 {delta, target, unit}"""
        mid = (low + high) / 2
        delta = max(mid - s["current"], 0)
        return {"delta": round(delta, 2), "target": round(mid, 1), "unit": unit}

    # --- 异常检测(最高优先) ---
    if s["anomaly"] == "down":
        parts.append(f"⚠️ {low_cn}这次掉得不寻常，单次变化超过以往波动 {max(2, round(s['vol']*2))}{unit}。先别急着补：看看蛋分和滴定泵是否正常、最近有没有大换水，再用同一套方法复测一次")
        prio = max(prio, 90)
    elif s["anomaly"] == "up":
        parts.append(f"⚠️ {low_cn}这次突然跳高。回看一下最近的补充记录和钙反状态，再用同一套方法复测，先排除操作差异")
        prio = max(prio, 85)

    # --- 预测预警 ---
    if prediction and prediction["days"] <= 7:
        parts.append(f"📅 {prediction['msg']}。可以提前核对实际消耗和当前补充方案，别等越线后再追")
        prio = max(prio, 80)

    # --- 营养盐专属建议 (NO3/PO4) ---
    if element in ("NO3", "PO4"):
        other = "PO4" if element == "NO3" else "NO3"
        if s["level"] == "low" and s["current"] <= low * 0.5:
            if element == "NO3":
                parts.append(f"🪸 {low_cn}读数很低（{s['current']:.2f}{unit}）。先用同一套方法复测，再把 PO₄、投喂量、生物负载和蛋分状态放在一起看。确认持续缺氮后，再考虑增加投喂或采用经过验证的氮源方案，每次只动一点")
                prio = max(prio, 70)
            else:
                parts.append(f"🪸 {low_cn}读数很低（{s['current']:.2f}{unit}）。先确认试剂状态和检测下限，再结合 NO₃、投喂和珊瑚表现判断；固定比例不值得拿来直接套加药")
                prio = max(prio, 70)
        elif s["level"] == "ok" and element == "NO3":
            parts.append(f"🪸 {low_cn}落在本缸参考范围 {low}–{high}{unit}，不需要为了更低继续往下压")
            prio = max(prio, 20)

    # --- 趋势+水平组合 ---
    if s["level"] == "low":
        # 仅核心钙化元素生成可直接进入计算器的补充动作。
        # 营养盐需要结合投喂、菌群、蛋分和生物负载判断，不自动生成加药剂量。
        if element in ("KH", "钙", "镁"):
            supplement = _supplement_info()
        if s["direction"] == "falling":
            if s["accelerating"]:
                parts.append(f"📉 {low_cn}还在下降，而且速度变快了（每天 {s['rate']:.2f}{unit}）。先复测确认趋势；读数没问题的话，分次补回 {low}–{high}{unit}，也回看近期珊瑚生长、换水和补充记录")
                prio = max(prio, 75)
            else:
                parts.append(f"📉 {low_cn}缓慢下降（每天 {s['rate']:.2f}{unit}），已经低于参考下限。确认读数后，可以分次补回参考范围，再看下一次测试")
                prio = max(prio, 65)
        elif s["direction"] == "rising":
            parts.append(f"↗️ {low_cn}虽然还低，但正在回升（每天 {s['rate']:.2f}{unit}）。先看下一次读数；还需要补时，少量分次就好")
            prio = max(prio, 55)
        else:
            parts.append(f"➡️ {low_cn}低于参考下限，近期变化不大。确认读数后，可以分次补回 {low}–{high}{unit}")
            prio = max(prio, 60)
    elif s["level"] == "high":
        if s["direction"] == "rising":
            parts.append(f"📈 {low_cn}高于参考上限，还在继续上升（每天 {s['rate']:.2f}{unit}）。先停下这一项补充，复测并回看最近的添加记录")
            prio = max(prio, 70)
        elif s["direction"] == "falling":
            parts.append(f"↘️ {low_cn}虽然偏高，但正在回落。先观察趋势，不用为了追数字急着动")
            prio = max(prio, 50)
        else:
            parts.append(f"➡️ {low_cn}高于参考上限，近期变化不大。先暂停这一项补充，复测并回看最近的换水和添加记录")
            prio = max(prio, 55)
    else:  # ok
        if s["direction"] == "falling" and prediction and prediction["days"] <= 14:
            parts.append(f"✅ {low_cn}目前还在参考范围内；照每天 {s['rate']:.2f}{unit} 的消耗速度，约 {prediction['days']:.0f} 天后可能低于 {low}{unit}。下一轮补充可以提前准备起来")
            prio = max(prio, 40)
        elif s["volatility"] == "high":
            parts.append(f"📊 {low_cn}平均值在参考范围内，不过波动有点大（±{s['vol']}{unit}）。接下来几次尽量在接近的时间测试，也看看设备和补充设置最近有没有变化")
            prio = max(prio, 35)
        else:
            parts.append(f"✅ {low_cn}落在本缸参考范围，趋势也稳。照现在的节奏养着就好")
            prio = max(prio, 10)

    # --- 波动补充 ---
    if s["volatility"] == "high" and "波动" not in "".join(parts):
        parts.append("📊 这段时间波动有点大。接下来几次可以稍微缩短复测间隔，更容易看清变化从哪里来")

    return {
        "priority": prio,
        "parts": parts,
        "summary": parts[0] if parts else "记录还不够，暂时不下结论",
        "supplement": supplement,
    }


# ============ 汇总分析 ============
def analyze_all(records_by_element, ideals=None):
    """records_by_element: {元素: [(date, value), ...]}"""
    result = {}
    for el, recs in records_by_element.items():
        result[el] = analyze_element(recs, el, (ideals or ELEMENT_IDEALS).get(el))
    return result


# ============ 元素联动诊断 ============
def linkage_diagnosis(analysis, ideals=None):
    """
    跨元素联动诊断：组合多个元素的信号，寻找关联线索与待复核的可能原因。
    analysis: analyze_all 的输出 {元素: 分析结果}
    返回: [{title, detail, priority, related}]
    """
    def sig(el, key):
        """安全取元素信号。"""
        a = analysis.get(el)
        if not a or "signals" not in a:
            return None
        return a["signals"].get(key)

    def cur(el):
        a = analysis.get(el)
        return a.get("current") if a else None

    findings = []
    ideals = ideals or ELEMENT_IDEALS

    # --- R1: 镁偏低与钙下降同时出现 ---
    mg = cur("镁")
    ca = cur("钙")
    mg_trend = sig("镁", "direction")
    ca_trend = sig("钙", "direction")
    if mg is not None and ca is not None:
        mg_low_limit = ideals["镁"]["low"]
        if mg < mg_low_limit and ca_trend == "falling":
            findings.append({
                "title": "镁偏低与钙下降同时出现",
                "detail": f"镁当前 {mg:.0f}ppm，低于本缸参考下限 {mg_low_limit:.0f}，钙也在下降。低镁可能增加碳酸钙非生物沉淀，也可能只是测试误差、盐度变化或生物消耗。把镁、钙和盐度一起复测，再决定从哪一项动手。",
                "priority": 85,
                "related": ["镁", "钙"],
            })

    # --- R2: KH与钙同步下降 ---
    kh = cur("KH")
    kh_trend = sig("KH", "direction")
    ca_trend2 = sig("钙", "direction")
    if kh is not None and ca is not None:
        kh_rate = abs(sig("KH", "rate") or 0)
        ca_rate = abs(sig("钙", "rate") or 0)
        if kh_trend == "falling" and ca_trend2 == "falling" and kh_rate > 0.02 and ca_rate > 0.3:
            findings.append({
                "title": "KH与钙同步下降",
                "detail": f"KH 每天降 {kh_rate:.2f}dKH，钙每天降 {ca_rate:.1f}ppm，两条趋势走得比较同步。珊瑚钙化、非生物沉淀和测量条件都可能带来这种变化；确认趋势后，按各自实测消耗校准，别拿固定比例硬套。",
                "priority": 70,
                "related": ["KH", "钙"],
            })

    # --- R3: 钙高 + KH低 → 碳酸钙沉淀 ---
    if kh is not None and ca is not None:
        ca_high_limit = ideals["钙"]["high"]
        kh_low_limit = ideals["KH"]["low"]
        if ca > ca_high_limit and kh < kh_low_limit:
            findings.append({
                "title": "钙偏高且碱度偏低，需要复核",
                "detail": f"钙 {ca:.0f}ppm 偏高（>{ca_high_limit:.0f}），KH 却只有 {kh:.1f}dKH（<{kh_low_limit:.0f}）。补充比例、盐度、测试误差或碳酸钙沉淀都可能有关。复测后再看钙反和补充设置，别只凭这一组数就调整。",
                "priority": 80,
                "related": ["钙", "KH"],
            })

    # --- R4: 碳氮磷失衡（NO3低 + PO4高） ---
    no3 = cur("NO3")
    po4 = cur("PO4")
    if no3 is not None and po4 is not None:
        if no3 < 1 and po4 > 0.1:
            findings.append({
                "title": "NO₃偏低且PO₄偏高",
                "detail": f"NO₃ 为 {no3:.2f}ppm，PO₄ 为 {po4:.2f}ppm。固定的 NO₃:PO₄ 比值不适合直接拿来算加药；复测后，把投喂、蛋分、吸附材料和生物负载逐项过一遍，再小幅调整。",
                "priority": 75,
                "related": ["NO3", "PO4"],
            })

    # --- R5: 镁过高提示 ---
    mg_high_limit = ideals["镁"]["high"]
    if mg is not None and mg > mg_high_limit:
        findings.append({
            "title": "镁偏高",
            "detail": f"镁 {mg:.0f}ppm，高于本缸参考上限 {mg_high_limit:.0f}。先把盐度和测试结果核对清楚，主动补镁可以停一停；多数情况下不用急着往下压。",
            "priority": 30,
            "related": ["镁"],
        })

    # 按优先级排序
    findings.sort(key=lambda x: x["priority"], reverse=True)
    return findings


# ============ A1: 滴定效果评估 ============
def evaluate_dosing_effect(records_by_element, dosing_logs):
    """
    对比"滴定区间内" vs "滴定区间外"的消耗速率。
    dosing_logs: [{element, dose_ml, action, recorded_at}, ...]
    返回每个元素滴定前后的速率变化。
    """
    from datetime import datetime

    def rate_in_range(recs, start, end):
        """计算某时间范围内的线性回归斜率(每天变化)。"""
        filtered = [(d, v) for d, v in recs if start <= d.isoformat()[:10] <= end]
        if len(filtered) < 2:
            return None
        t0 = filtered[0][0]
        xs = [(d - t0).total_seconds() / 86400.0 for d, _ in filtered]
        ys = [v for _, v in filtered]
        slope, _, _ = _linreg(xs, ys)
        return slope

    result = {}
    # 按元素分组滴定日志
    for el, recs in records_by_element.items():
        el_logs = [l for l in dosing_logs if l.get("element") == el]
        if len(el_logs) < 2:
            continue  # 至少要有开始+结束才能评估
        # 找完整区间（start→end 配对）
        dates = sorted([(l["recorded_at"][:10], l["action"]) for l in el_logs])
        intervals = []
        open_start = None
        for d, action in dates:
            if action == "start" and open_start is None:
                open_start = d
            elif action == "end" and open_start is not None:
                intervals.append((open_start, d))
                open_start = None
        if not intervals:
            continue
        # 速率显示按量级自适应小数位（小数值元素显示更多位，避免"看起来没变"）
        def fmt_rate(v):
            av = abs(v)
            if av < 0.01:
                return round(v, 5)
            elif av < 0.1:
                return round(v, 4)
            return round(v, 3)
        # 评估每个完整区间（可能多次滴定）
        el_intervals = []
        for idx, (start, end) in enumerate(intervals):
            in_rate = rate_in_range(recs, start, end)
            # 区间外速率：该区间开始前的数据
            pre_recs = [(d, v) for d, v in recs if d.isoformat()[:10] < start]
            pre_rate = None
            if len(pre_recs) >= 2:
                t0 = pre_recs[0][0]
                xs = [(d - t0).total_seconds() / 86400.0 for d, _ in pre_recs]
                ys = [v for _, v in pre_recs]
                pre_rate, _, _ = _linreg(xs, ys)
            if in_rate is None or pre_rate is None:
                continue
            # 效果：消耗率变化（斜率绝对值变小=消耗变慢=有效）
            change = (abs(pre_rate) - abs(in_rate)) / abs(pre_rate) * 100 if pre_rate != 0 else 0
            el_intervals.append({
                "interval": f"{start} ~ {end}",
                "pre_rate": fmt_rate(pre_rate),
                "in_rate": fmt_rate(in_rate),
                "improvement_pct": round(change, 1),
                "effective": change > 10,
            })
        if el_intervals:
            result[el] = el_intervals if len(el_intervals) > 1 else el_intervals[0]
    return result


# ============ A2: 消耗/补充平衡 ============
def current_dosing_states(dosing_logs):
    """把开始、调整、停用日志归并为每个元素的当前方案状态。"""
    states = {}
    ordered = sorted(
        dosing_logs or [],
        key=lambda item: (str(item.get("recorded_at") or ""), int(item.get("id") or 0)),
    )
    for log in ordered:
        element = log.get("element")
        action = log.get("action") or "start"
        if not element:
            continue
        state = states.setdefault(element, {"active": False, "dose_ml": 0})
        if action == "start":
            state.update(active=True, dose_ml=log.get("dose_ml", 0))
        elif action == "adjust" and state["active"]:
            state["dose_ml"] = log.get("dose_ml", state["dose_ml"])
        elif action == "end":
            state.update(active=False, dose_ml=0)
    return states


def balance_audit(records_by_element, dosing_logs, mix_ratio=None, tank_liters=None):
    """
    估算"缸体消耗量" vs "滴定补充量"是否平衡。
    mix_ratio: {元素: {"pw": 分析纯克, "ro": RO水毫升}} 配液比例
    tank_liters: 缸体实际水体(升)
    消耗量 = 由水质下降速率推得(ppm/天 → 需要补的克)
    补充量 = 滴定量(ml/天) × 配液浓度(克/ml)
    """
    if (not isinstance(tank_liters, (int, float)) or not math.isfinite(tank_liters) or
            tank_liters <= 0):
        return {}
    result = {}
    dosing_states = current_dosing_states(dosing_logs)
    # (添加物分子量, 元素当量) — 用于 ppm→克 换算
    EL_COEF = {"KH": (84, 2.8), "钙": (147, 40), "镁": (204, 24)}

    for el, recs in records_by_element.items():
        if el not in EL_COEF:
            continue
        mol, eq = EL_COEF[el]
        # 消耗：最近趋势的下降速率(ppm/天)
        vals = [v for _, v in recs]
        if len(vals) < 3:
            continue
        t0 = recs[0][0]
        xs = [(d - t0).total_seconds() / 86400.0 for d, _ in recs[-5:]]
        ys = vals[-5:]
        slope, _, _ = _linreg(xs, ys)
        consume_rate = -slope if slope < 0 else 0  # ppm/天下降

        # 补充：只使用当前仍启用的方案，调整剂量会更新当前值，停用后归零。
        state = dosing_states.get(el, {})
        dose_ml = state.get("dose_ml", 0) if state.get("active") else 0
        # 配液浓度必须来自用户真实配比；不同元素/配方不能共用假定默认浓度。
        mix = mix_ratio.get(el) if isinstance(mix_ratio, dict) else None
        if not isinstance(mix, dict):
            result[el] = {
                "consume_g_per_day": round(consume_rate * tank_liters * (mol / eq) / 1000, 3),
                "supply_g_per_day": None,
                "balance_pct": None,
                "status": "needs_mix",
            }
            continue
        pw, ro = mix.get("pw"), mix.get("ro")
        if (not isinstance(pw, (int, float)) or not isinstance(ro, (int, float)) or
                not math.isfinite(pw) or not math.isfinite(ro) or pw <= 0 or ro <= 0):
            result[el] = {
                "consume_g_per_day": round(consume_rate * tank_liters * (mol / eq) / 1000, 3),
                "supply_g_per_day": None,
                "balance_pct": None,
                "status": "needs_mix",
            }
            continue
        conc_g_per_ml = pw / ro

        # 补充量换算: ml/天 × 克/ml = 克/天
        supply_g_per_day = dose_ml * conc_g_per_ml
        # 消耗量换算: ppm/天 × 水体体积(L) × (分子量/当量) / 1000 = 克/天
        consume_g_per_day = consume_rate * tank_liters * (mol / eq) / 1000

        balance_pct = 0
        if consume_g_per_day > 0:
            balance_pct = supply_g_per_day / consume_g_per_day * 100

        # 状态判定：消耗为0 → 水质未下降，无需补充（平衡）
        # 消耗>0 且 补充=0 → 补充不足；消耗>0 且 补充>0 → 比较比例
        if consume_g_per_day <= 0:
            status = "stable"   # 水质稳定，无需补充
        elif supply_g_per_day <= 0:
            status = "under"    # 有消耗但没在补充
        elif 80 <= balance_pct <= 120:
            status = "balanced"
        elif balance_pct > 120:
            status = "over"     # 补多了
        else:
            status = "under"    # 补不够

        result[el] = {
            "consume_g_per_day": round(consume_g_per_day, 3),
            "supply_g_per_day": round(supply_g_per_day, 3),
            "balance_pct": round(balance_pct, 0),  # >100=补多了, <100=不够
            "status": status,
        }
    return result


# ============ B1: 测试频率健康度 ============
def test_frequency_health(records_by_element, weeks=4, intervals=None):
    """
    评估测试频率：看"最近一条记录往前 N 周"内各元素测试了多少次，
    并以用户当前维护周期判断完成度和数据是否过期。
    """
    from datetime import datetime, timedelta

    today = datetime.now()
    result = {}
    for el, recs in records_by_element.items():
        if not recs:
            continue
        dates = [d for d, _ in recs]
        last_date = max(dates)
        days_since_last = (today - last_date).total_seconds() / 86400.0
        # 以最后一条记录为基准往回统计（避免演示数据陈旧导致误报）
        window_end = last_date
        window_start = window_end - timedelta(days=weeks * 7)
        recent = [d for d in dates if window_start <= d <= window_end]
        count = len(recent)
        per_week = count / weeks if weeks > 0 else 0

        interval = max(1, int((intervals or {}).get(el, 7)))
        expected_count = weeks * 7 / interval
        completion = count / expected_count if expected_count else 0
        stale = days_since_last > interval
        if stale:
            status = "stale"
            msg = (f"最后一次是 {last_date.strftime('%Y-%m-%d')}（距今 {days_since_last:.0f} 天），"
                   f"已经超过当前 {interval} 天周期，可以找时间复测了")
        elif completion >= 1:
            status = "good"
            msg = f"近{weeks}周测试 {count} 次，符合当前 {interval} 天周期"
        elif completion >= 0.6:
            status = "fair"
            msg = f"近{weeks}周测试 {count} 次，略少于当前 {interval} 天周期"
        else:
            status = "low"
            msg = f"近{weeks}周仅测试 {count} 次，低于当前 {interval} 天周期，趋势判断可能不准"
        result[el] = {"count": count, "per_week": round(per_week, 1), "interval_days": interval,
                      "status": status, "msg": msg, "stale": stale}
    return result


if __name__ == "__main__":
    # 自测: 模拟KH 3周缓慢下降
    from datetime import date
    recs = []
    for i in range(21):
        recs.append((date(2025, 1, 1 + i).isoformat(), 8.2 - i * 0.08))
    r = analyze_element(recs, "KH")
    print("状态:", r["status"], "| 当前:", r["current"])
    import json
    print("信号:", json.dumps(r["signals"], ensure_ascii=False))
    print("预测:", r["prediction"] and r["prediction"]["msg"])
    print("建议:", r["advice"]["summary"])
    print("优先级:", r["advice"]["priority"])
