# -*- coding: utf-8 -*-
"""
滴定用量计算/调节 - 核心引擎
算法复刻自 CMF海水论坛:
  https://www.cmfish.com/ca/didingy.html  (滴定用量自动计算表)
  https://www.cmfish.com/ca/didingt.html  (滴定用量调节表)

【滴定用量计算表 didingy】逻辑:
  对比浓度 = parseInt(RO水量 / 分析纯量)          # 配液稀释比
  所需量(ml/ppm/升) = 对比浓度 × 元素系数          # 钙0.004 镁0.009 KH0.03 钾0.002
  下降值 = 初次测试值 - 最后测试值
  每天消耗 = 下降值 / 测试间隔(天)
  每天滴定量(ml) = round(缸水量升 × 每天消耗 × 所需量)

【滴定用量调节表 didingt】逻辑(在计算表基础上):
  需升跌值 = 目标值 - 当前测试值
  日增减值 = 需升跌值 / 计划提升天数
  需增减值 = round(缸水量 × 日增减值 × 所需量)
  每日滴定量 = 需增减值 + 当前滴定量
"""

# 元素系数表（沿用原站经验公式）。
# `稀释比 × 系数`表示每升水提升1单位所需的配液毫升系数，
# 不是“每毫升配液能提升多少”。保留旧函数名仅为兼容现有API。
ELEMENT_FACTORS = {
    "钙": 0.004,
    "镁": 0.009,
    "KH": 0.03,
    "钾": 0.002,
}


def mix_concentration(ro_water_ml: float, powder_g: float) -> int:
    """
    配液对比浓度: 稀释比 = 水量/分析纯量 (原站 parseInt 取整)
    """
    import math
    if (not isinstance(ro_water_ml, (int, float)) or not isinstance(powder_g, (int, float)) or
            not math.isfinite(ro_water_ml) or not math.isfinite(powder_g) or
            ro_water_ml <= 0 or powder_g <= 0):
        return 0
    return int(ro_water_ml / powder_g)


def per_ml_effect(ro_water_ml: float, powder_g: float, element: str) -> float:
    """
    兼容旧名称：返回每升水提升1单位所需的配液毫升系数。

    该值越大，表示溶液越稀、达到同样提升所需的毫升数越多；
    它并不是“每毫升配液的提升量”。
    """
    c = mix_concentration(ro_water_ml, powder_g)
    factor = ELEMENT_FACTORS.get(element, 0)
    return c * factor


def daily_dose(ro_water_ml: float, powder_g: float, element: str,
               tank_liters: float, first_value: float, last_value: float,
               interval_days: float) -> float:
    """
    【滴定用量计算表】每天滴定量(毫升)
    每天滴定量 = round(缸水量升 × (初次-末次)/间隔天数 × 单位需求系数)
    """
    import math
    values = [tank_liters, first_value, last_value, interval_days, ro_water_ml, powder_g]
    if any(v is None or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return 0.0
    if tank_liters <= 0 or interval_days <= 0 or first_value < 0 or last_value < 0:
        return 0.0
    drop = first_value - last_value
    if drop <= 0:
        return 0.0  # 没有下降则无需补充
    daily_consume = drop / interval_days
    effect = per_ml_effect(ro_water_ml, powder_g, element)
    return round(tank_liters * daily_consume * effect)


def adjust_dose(ro_water_ml: float, powder_g: float, element: str,
                tank_liters: float, target_value: float, current_value: float,
                plan_days: float, current_dose_ml: float = 0) -> dict:
    """
    【滴定用量调节表】每日滴定量(毫升)调节计算
    返回: 需升跌值/日增减值/需增减值/每日滴定量
    """
    import math
    values = [tank_liters, target_value, current_value, plan_days,
              current_dose_ml, ro_water_ml, powder_g]
    if any(v is None or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return {"need_delta": 0, "daily_delta": 0, "need_dose": 0, "final_dose": 0}
    if (tank_liters <= 0 or plan_days <= 0 or target_value < 0 or current_value < 0 or
            current_dose_ml < 0):
        return {"need_delta": 0, "daily_delta": 0, "need_dose": 0, "final_dose": 0}
    need_delta = target_value - current_value
    daily_delta = need_delta / plan_days
    effect = per_ml_effect(ro_water_ml, powder_g, element)
    need_dose = round(tank_liters * daily_delta * effect)
    final_dose = int(need_dose) + int(current_dose_ml or 0)
    return {
        "need_delta": round(need_delta, 2),
        "daily_delta": round(daily_delta, 3),
        "need_dose": need_dose,
        "final_dose": final_dose,
    }


# 常用配液参考(原站默认值)
DEFAULT_MIX = {
    "钙": {"ro_water_ml": 2000, "powder_g": 500},
    "镁": {"ro_water_ml": 4000, "powder_g": 1000},
    "KH": {"ro_water_ml": 1000, "powder_g": 50},
    "钾": {"ro_water_ml": 1000, "powder_g": 500},
}


if __name__ == "__main__":
    # 自测 - 与原站默认输出对照
    print("钙配液: 2000ml水/500g 对比浓度=", mix_concentration(2000, 500), "单位需求系数=", per_ml_effect(2000, 500, "钙"))
    print("镁配液: 4000ml水/1000g 对比浓度=", mix_concentration(4000, 1000), "单位需求系数=", per_ml_effect(4000, 1000, "镁"))
    print("KH配液: 1000ml水/50g 对比浓度=", mix_concentration(1000, 50), "单位需求系数=", per_ml_effect(1000, 50, "KH"))
    print("钾配液: 1000ml水/500g 对比浓度=", mix_concentration(1000, 500), "单位需求系数=", per_ml_effect(1000, 500, "钾"))
    # 调节表默认值验证
    r = adjust_dose(2000, 500, "钙", 550, 420, 350, 10)
    print("钙调节(期望: 62):", r)
    r = adjust_dose(4000, 1000, "镁", 550, 1350, 1120, 5)
    print("镁调节(期望: 911):", r)
    r = adjust_dose(1000, 50, "KH", 550, 8.5, 7.5, 10)
    print("KH调节(期望: 33):", r)
