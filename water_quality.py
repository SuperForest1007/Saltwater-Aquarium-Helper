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
import math
from datetime import datetime, timedelta


# ============ 理想范围定义 ============
ELEMENT_IDEALS = {
    "KH":  {"low": 7.0, "high": 8.0, "unit": "dKH", "display": "KH 碱度"},
    "钙":  {"low": 400, "high": 440, "unit": "ppm", "display": "钙 Ca"},
    "镁":  {"low": 1200, "high": 1300, "unit": "ppm", "display": "镁 Mg"},
    "NO3": {"low": 2.0, "high": 10.0, "unit": "ppm", "display": "硝酸盐 NO₃",
            "hint": "完全归零会让珊瑚饿瘦；SPS建议3-10ppm，LPS 2-5ppm，与PO4保持约100:1"},
    "PO4": {"low": 0.03, "high": 0.08, "unit": "ppm", "display": "磷酸盐 PO₄",
            "hint": "完全归零会让珊瑚失去颜色；SPS建议0.03-0.05ppm，LPS可到0.08ppm"},
}


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
        return {"element": element, "status": "no_data", "signals": {}, "advice": "暂无该元素记录，请添加几次测试值后开始分析。"}

    # 时间序列
    dates = [datetime.fromisoformat(d) if isinstance(d, str) else d for d, _ in records]
    values = [float(v) for _, v in records]
    # 转为"天"序号
    t0 = dates[0]
    xs = [(d - t0).total_seconds() / 86400.0 for d in dates]
    ys = values

    cur = ys[-1]
    slope, inter, r2 = _linreg(xs, ys)

    # ---- L1: 单点状态 ----
    if cur < low:
        l1 = "low"
        l1_msg = f"当前 {cur:.1f}{unit} 低于理想下限 {low}{unit}"
    elif cur > high:
        l1 = "high"
        l1_msg = f"当前 {cur:.1f}{unit} 高于理想上限 {high}{unit}"
    else:
        l1 = "ok"
        l1_msg = f"当前 {cur:.1f}{unit} 在理想范围 {low}-{high}{unit} 内"

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
    range_span = high - low
    vol_ratio = vol / range_span if range_span > 0 else 0
    volatility = "high" if vol_ratio > 0.25 else ("low" if vol_ratio < 0.08 else "normal")

    # ---- L5: 预测 ----
    prediction = None
    if slope != 0 and len(xs) >= 2:
        # 预测跌破/突破的天数
        if slope < 0 and cur > low:
            days_to_low = (low - cur) / slope
            if days_to_low > 0:
                eta = (t0 + timedelta(days=days_to_low)).date()
                prediction = {"direction": "down", "days": days_to_low, "target": low, "date": str(eta),
                              "msg": f"按当前速率(每天{abs(slope):.2f}{unit})，预计约{max(1, round(days_to_low))}天后跌破{low}{unit}({eta})"}
        elif slope > 0 and cur < high:
            days_to_high = (high - cur) / slope
            if days_to_high > 0:
                eta = (t0 + timedelta(days=days_to_high)).date()
                prediction = {"direction": "up", "days": days_to_high, "target": high, "date": str(eta),
                              "msg": f"按当前速率(每天{abs(slope):.2f}{unit})，预计约{max(1, round(days_to_high))}天后升破{high}{unit}({eta})"}

    # ---- L4: 规则组合 ----
    signals = {
        "level": l1, "level_msg": l1_msg,
        "direction": direction, "direction_cn": direction_cn,
        "rate": round(abs(rate), 3), "rate_signed": round(rate, 3),
        "accelerating": accelerating, "accel": round(accel, 3),
        "anomaly": anomaly, "anomaly_cn": anomaly_cn,
        "volatility": volatility, "vol": round(vol, 2),
        "r2": round(r2, 3),
        "current": round(cur, 2),
        "count": len(records),
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
        "records": [{"date": d.strftime("%Y-%m-%d"), "value": v, "ts": int(d.timestamp() * 1000)} for d, v in zip(dates, values)],
    }


# ============ L4: 规则引擎 + 动态建议 ============
def _compose_advice(element, s, low, high, unit, prediction=None):
    """
    信号组合 → 建议。不是固定模板: 结论由数值动态生成,
    动作从动作库挑选并代入实际参数。
    """
    parts = []
    prio = 0
    low_cn = {"KH": "碱度", "钙": "钙", "镁": "镁", "NO3": "硝酸盐", "PO4": "磷酸盐"}.get(element, element)

    # --- 异常检测(最高优先) ---
    if s["anomaly"] == "down":
        parts.append(f"⚠️ {low_cn}出现异常骤降(单次变化超出历史波动{max(2, round(s['vol']*2))}{unit})，优先检查：蛋分/滴定泵是否故障、是否大换水、测试剂是否新鲜")
        prio = max(prio, 90)
    elif s["anomaly"] == "up":
        parts.append(f"⚠️ {low_cn}出现异常跳升，优先检查：是否刚添加了补充剂、钙反是否异常、测试操作是否一致")
        prio = max(prio, 85)

    # --- 预测预警 ---
    if prediction and prediction["days"] <= 7:
        parts.append(f"📅 {prediction['msg']}，建议提前补充或检查消耗源")
        prio = max(prio, 80)

    # --- 营养盐专属建议 (NO3/PO4) ---
    if element in ("NO3", "PO4"):
        other = "PO4" if element == "NO3" else "NO3"
        if s["level"] == "low" and s["current"] <= low * 0.5:
            if element == "NO3":
                parts.append(f"🪸 {low_cn}过低({s['current']:.2f}{unit})，珊瑚可能因缺乏营养而褪色瘦弱。刚开缸时可接受归零，但养珊瑚建议维持 {low}-{high}{unit}，可用硝酸钾/珊瑚粮缓慢提升，保持与PO4约100:1")
                prio = max(prio, 70)
            else:
                parts.append(f"🪸 {low_cn}过低({s['current']:.2f}{unit})，磷是珊瑚营养必需。完全归零会让珊瑚发白、生长停滞，建议维持 {low}-{high}{unit}")
                prio = max(prio, 70)
        elif s["level"] == "ok" and element == "NO3":
            parts.append(f"🪸 {low_cn}在 {low}-{high}{unit} 之间，是珊瑚生长所需营养区间(只有刚开缸阶段才追求归零)，保持即可")
            prio = max(prio, 20)

    # --- 趋势+水平组合 ---
    if s["level"] == "low":
        if s["direction"] == "falling":
            if s["accelerating"]:
                parts.append(f"📉 {low_cn}持续下降且速率在加快(每天{s['rate']:.2f}{unit})，正在远离理想范围，建议尽快补充至{low}-{high}{unit}，并排查消耗增加原因(珊瑚生长加速/换水)")
                prio = max(prio, 75)
            else:
                parts.append(f"📉 {low_cn}缓慢下降(每天{s['rate']:.2f}{unit})，已低于下限，建议补充并观察是否稳定")
                prio = max(prio, 65)
        elif s["direction"] == "rising":
            parts.append(f"↗️ {low_cn}虽低于下限但正在回升(每天{s['rate']:.2f}{unit})，若在恢复中可少量补充加速到位")
            prio = max(prio, 55)
        else:
            parts.append(f"➡️ {low_cn}低于下限且近期平稳，建议补充至{low}-{high}{unit}")
            prio = max(prio, 60)
    elif s["level"] == "high":
        if s["direction"] == "rising":
            parts.append(f"📈 {low_cn}高于上限且仍在上升(每天{s['rate']:.2f}{unit})，注意过量风险，建议暂停补充并观察")
            prio = max(prio, 70)
        elif s["direction"] == "falling":
            parts.append(f"↘️ {low_cn}虽高于上限但正回落，可暂不处理，回到{high}{unit}以下即可")
            prio = max(prio, 50)
        else:
            parts.append(f"➡️ {low_cn}高于上限且平稳，建议少量换水或暂停添加让其自然回落")
            prio = max(prio, 55)
    else:  # ok
        if s["direction"] == "falling" and prediction and prediction["days"] <= 14:
            parts.append(f"✅ {low_cn}当前正常，但按每天{s['rate']:.2f}{unit}的速度消耗，{prediction['days']:.0f}天后可能低于{low}{unit}，可提前规划补充")
            prio = max(prio, 40)
        elif s["volatility"] == "high":
            parts.append(f"📊 {low_cn}均值正常但波动偏大(±{s['vol']:.1f}{unit})，建议固定每天同一时间测试，排查波动源")
            prio = max(prio, 35)
        else:
            parts.append(f"✅ {low_cn}在理想范围内且趋势平稳，状态良好，按当前节奏维护即可")
            prio = max(prio, 10)

    # --- 波动补充 ---
    if s["volatility"] == "high" and "波动" not in "".join(parts):
        parts.append(f"📊 整体波动偏大，建议增加测试频率(每周2-3次)以掌握真实变化")

    return {
        "priority": prio,
        "parts": parts,
        "summary": parts[0] if parts else "暂无建议",
    }


# ============ 汇总分析 ============
def analyze_all(records_by_element):
    """records_by_element: {元素: [(date, value), ...]}"""
    result = {}
    for el, recs in records_by_element.items():
        result[el] = analyze_element(recs, el)
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
