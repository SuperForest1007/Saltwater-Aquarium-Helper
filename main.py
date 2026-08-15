# -*- coding: utf-8 -*-
"""
海水缸管理App - FastAPI 后端入口
"""
import os
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from additive_calculator import (
    calc_additive, get_all_additives, calc_dose_auto,
)
from dosing_calculator import (
    ELEMENT_FACTORS, DEFAULT_MIX, mix_concentration, per_ml_effect,
    daily_dose, adjust_dose,
)
from water_quality import (
    analyze_element, analyze_all, ELEMENT_IDEALS,
    evaluate_dosing_effect, balance_audit, test_frequency_health,
)
from water_store import (
    init_db, add_record, get_records, get_records_grouped, delete_record, get_elements,
    init_dosing_log, add_dosing_log, get_dosing_logs, get_last_dose, delete_dosing_log,
    init_water_change, add_water_change, get_water_changes, delete_water_change,
)

app = FastAPI(title="海水缸管理App", version="0.4.0")

# 初始化数据库
init_db()
init_dosing_log()
init_water_change()

# 项目根目录（基于文件位置，避免工作目录不同导致找不到文件）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 静态文件（echarts.min.js 等）
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ---------- API ----------

class AdditiveRequest(BaseModel):
    water_liters: float       # 水量(升)
    conc_delta: float         # 提升/降低浓度
    v1: float                 # 元素当量
    v2: float                 # 添加物分子量

class AutoDoseRequest(BaseModel):
    water_liters: float       # 水量(升)
    current_value: float      # 当前实测值
    ideal_low: float          # 理想下限
    ideal_high: float         # 理想上限
    v1: float                 # 元素当量
    v2: float                 # 添加物分子量
    unit: str = "ppm"         # 单位(ppm/dKH)

class MixRequest(BaseModel):
    ro_water_ml: float        # RO水量(毫升)
    powder_g: float           # 分析纯量(克)

class DoseRequest(BaseModel):
    ro_water_ml: float
    powder_g: float
    element: str              # 钙/镁/KH/钾
    tank_liters: float        # 缸总水量(升)
    first_value: float        # 初次测试值
    last_value: float         # 最后测试值
    interval_days: float      # 测试间隔(天)

class AdjustRequest(BaseModel):
    ro_water_ml: float
    powder_g: float
    element: str
    tank_liters: float
    target_value: float       # 目标值
    current_value: float      # 当前测试值
    plan_days: float          # 计划提升天数
    current_dose_ml: float = 0  # 当前滴定量(毫升)

@app.get("/api/additives")
def api_additives():
    """返回试算表全部数据(分组+说明)。"""
    return {"groups": get_all_additives()}

@app.post("/api/calc/additive")
def api_calc_additive(req: AdditiveRequest):
    grams = calc_additive(req.water_liters, req.conc_delta, req.v1, req.v2)
    return {"grams": grams, "note": "使用量(克)"}

@app.post("/api/calc/auto")
def api_calc_auto(req: AutoDoseRequest):
    """【自动化】输入实测值 → 自动判断缺口 → 推荐添加量。"""
    return calc_dose_auto(req.water_liters, req.current_value,
                          req.ideal_low, req.ideal_high, req.v1, req.v2, req.unit)

# ---------- 滴定相关 API ----------

@app.get("/api/dosing/meta")
def api_dosing_meta():
    """滴定元素系数与默认配液。"""
    return {"factors": ELEMENT_FACTORS, "defaults": DEFAULT_MIX}

@app.post("/api/dosing/mix")
def api_dosing_mix(req: MixRequest):
    """配液浓度计算。"""
    return {"concentration": mix_concentration(req.ro_water_ml, req.powder_g)}

@app.post("/api/dosing/daily")
def api_dosing_daily(req: DoseRequest):
    """滴定用量计算表: 每天滴定量。"""
    return {
        "concentration": mix_concentration(req.ro_water_ml, req.powder_g),
        "per_ml_effect": per_ml_effect(req.ro_water_ml, req.powder_g, req.element),
        "daily_dose_ml": daily_dose(req.ro_water_ml, req.powder_g, req.element,
                                     req.tank_liters, req.first_value, req.last_value,
                                     req.interval_days),
    }

@app.post("/api/dosing/adjust")
def api_dosing_adjust(req: AdjustRequest):
    """滴定用量调节表: 每日滴定量调节。"""
    return adjust_dose(req.ro_water_ml, req.powder_g, req.element,
                       req.tank_liters, req.target_value, req.current_value,
                       req.plan_days, req.current_dose_ml)

class DosingLogRequest(BaseModel):
    element: str
    dose_ml: float
    note: str = ""
    action: str = "start"   # start=开始滴定 / end=结束滴定
    recorded_at: str = ""

@app.post("/api/dosing/log")
def api_dosing_log_add(req: DosingLogRequest):
    """记录一次滴定设置变化（前端自动调用）。"""
    rid = add_dosing_log(req.element, req.dose_ml, req.note, req.recorded_at or None, req.action)
    return {"id": rid, "ok": True}

@app.get("/api/dosing/logs")
def api_dosing_logs(element: str = None):
    """获取滴定记录（供趋势图标记）。"""
    return {"logs": get_dosing_logs(element)}

@app.delete("/api/dosing/log/{rid}")
def api_dosing_log_delete(rid: int):
    """删除一条滴定记录。"""
    return {"ok": delete_dosing_log(rid)}

# ---------- 换水记录 API ----------

class WaterChangeRequest(BaseModel):
    water_liters: float
    salt_brand: str = ""
    note: str = ""
    recorded_at: str = ""

@app.post("/api/water-change")
def api_water_change_add(req: WaterChangeRequest):
    rid = add_water_change(req.water_liters, req.salt_brand, req.note, req.recorded_at or None)
    return {"id": rid, "ok": True}

@app.get("/api/water-change")
def api_water_change_list():
    return {"changes": get_water_changes()}

@app.delete("/api/water-change/{rid}")
def api_water_change_delete(rid: int):
    return {"ok": delete_water_change(rid)}

# ---------- 水质记录与分析 API ----------

class RecordRequest(BaseModel):
    element: str
    value: float
    note: str = ""
    recorded_at: str = ""   # 可选，默认当前时间

@app.get("/api/water/ideals")
def api_water_ideals():
    """各元素理想范围。"""
    return {"ideals": ELEMENT_IDEALS}

@app.get("/api/water/records")
def api_water_records(element: str = None):
    """获取记录（可按元素过滤）。"""
    return {"records": get_records(element)}

@app.get("/api/water/elements")
def api_water_elements():
    """已有记录的元素列表。"""
    return {"elements": get_elements()}

@app.post("/api/water/record")
def api_water_add(req: RecordRequest):
    rid = add_record(req.element, req.value, ELEMENT_IDEALS.get(req.element, {}).get("unit", "ppm"), req.note, req.recorded_at or None)
    return {"id": rid, "ok": True}

@app.delete("/api/water/record/{rid}")
def api_water_delete(rid: int):
    return {"ok": delete_record(rid)}

@app.get("/api/water/analysis")
def api_water_analysis():
    """全元素智能分析（L1-L5）。"""
    grouped = get_records_grouped()
    return {"analysis": analyze_all(grouped)}

@app.get("/api/water/element-analysis")
def api_water_element_analysis(element: str):
    """单元素分析。"""
    recs = get_records(element)
    data = [(r["recorded_at"], r["value"]) for r in recs]
    return {"analysis": analyze_element(data, element)}

@app.get("/api/analysis/dosing-effect")
def api_dosing_effect():
    """A1: 滴定效果评估。"""
    grouped = get_records_grouped()
    logs = get_dosing_logs()
    data = {}
    for el, recs in grouped.items():
        # 转为datetime
        from datetime import datetime
        data[el] = [(datetime.fromisoformat(d), v) for d, v in recs]
    return {"result": evaluate_dosing_effect(data, logs)}

@app.get("/api/analysis/balance")
def api_balance(tank_liters: float = 156):
    """A2: 消耗/补充平衡审计。"""
    grouped = get_records_grouped()
    logs = get_dosing_logs()
    from datetime import datetime
    data = {}
    for el, recs in grouped.items():
        data[el] = [(datetime.fromisoformat(d), v) for d, v in recs]
    return {"result": balance_audit(data, logs, tank_liters=tank_liters)}

@app.get("/api/analysis/frequency")
def api_frequency():
    """B1: 测试频率健康度。"""
    grouped = get_records_grouped()
    from datetime import datetime
    data = {}
    for el, recs in grouped.items():
        data[el] = [(datetime.fromisoformat(d), v) for d, v in recs]
    return {"result": test_frequency_health(data)}

# ---------- 前端页面 ----------

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
