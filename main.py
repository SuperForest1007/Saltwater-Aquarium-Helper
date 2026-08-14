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
from water_quality import analyze_element, analyze_all, ELEMENT_IDEALS
from water_store import (
    init_db, add_record, get_records, get_records_grouped, delete_record, get_elements,
)

app = FastAPI(title="海水缸管理App", version="0.4.0")

# 初始化数据库
init_db()

# 静态文件（echarts.min.js 等）
app.mount("/static", StaticFiles(directory="static"), name="static")

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

# ---------- 前端页面 ----------

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
