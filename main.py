# -*- coding: utf-8 -*-
"""
海水缸管理App - FastAPI 后端入口
"""
import os
from datetime import date, timedelta
from typing import Literal, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, confloat

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
    linkage_diagnosis, get_ideals_for_tank, TANK_TYPE_DESCRIPTIONS,
    TANK_TYPE_TARGETS, TANK_TYPE_FOCUS,
)
from today_status import maintenance_defaults, build_today_dashboard
from water_store import (
    init_db, add_record, get_records, get_records_grouped, delete_record, get_elements,
    init_dosing_log, add_dosing_log, get_dosing_logs, get_last_dose, delete_dosing_log,
    init_water_change, add_water_change, get_water_changes, delete_water_change,
    update_record, update_dosing_log, update_water_change,
    export_all, import_all, get_active_tank, update_active_tank,
    init_maintenance, ensure_maintenance_rules, get_maintenance_rules,
    update_maintenance_rule, add_maintenance_event, get_maintenance_events,
    TANK_TYPES, TANK_STAGES,
)

app = FastAPI(title="海水缸管理App", version="0.5.0")

# 初始化数据库
init_db()
init_dosing_log()
init_water_change()
init_maintenance()

# 项目根目录（基于文件位置，避免工作目录不同导致找不到文件）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 静态文件（echarts.min.js 等）
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ---------- API ----------

PositiveFiniteFloat = confloat(gt=0, allow_inf_nan=False)
NonNegativeFiniteFloat = confloat(ge=0, allow_inf_nan=False)
WaterElement = Literal["KH", "钙", "镁", "NO3", "PO4"]
DosingElement = Literal["KH", "钙", "镁"]
DosingAction = Literal["start", "end", "adjust"]


def _validate_recorded_at(value: str):
    """记录日期只接收本地日历日期，避免坏数据让后续趋势解析失败。"""
    if not value:
        return
    try:
        recorded = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="记录日期必须使用 YYYY-MM-DD") from exc
    if recorded > date.today():
        raise HTTPException(status_code=422, detail="记录日期不能晚于今天")


def _not_found(ok: bool, label: str):
    if not ok:
        raise HTTPException(status_code=404, detail=f"没有找到这条{label}")
    return {"ok": True}


def _active_context():
    tank = get_active_tank()
    ideals = get_ideals_for_tank(tank["tank_type"], tank.get("custom_targets"))
    return tank, ideals


class TankProfileRequest(BaseModel):
    name: str = Field(default="我的鱼缸", max_length=40)
    water_liters: PositiveFiniteFloat
    tank_type: Literal["FOT", "软体", "LPS", "SPS", "NPS", "混养"]
    stage: Literal["筹备中", "开缸期", "稳定期", "调整期"]
    started_at: str = ""
    custom_targets: dict = Field(default_factory=dict)
    salt_brand: str = Field(default="", max_length=80)


def _validate_tank_request(req: TankProfileRequest):
    if req.started_at:
        try:
            started = date.fromisoformat(req.started_at)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="开缸日期必须使用 YYYY-MM-DD") from exc
        if started > date.today():
            raise HTTPException(status_code=422, detail="开缸日期不能晚于今天")
    for element, target in req.custom_targets.items():
        if element not in ELEMENT_IDEALS or not isinstance(target, dict):
            raise HTTPException(status_code=422, detail=f"无法识别的自定义目标：{element}")
        try:
            low, high = float(target["low"]), float(target["high"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"{element} 自定义目标需要 low/high") from exc
        if low < 0 or low >= high:
            raise HTTPException(status_code=422, detail=f"{element} 自定义目标必须满足 0 ≤ low < high")


@app.get("/api/tank")
def api_tank_get():
    tank, ideals = _active_context()
    return {
        "tank": tank,
        "effective_targets": ideals,
        "profile_note": "这些数值先拿来作参考，后面再跟着测试走势和缸里的状态慢慢调。",
    }


@app.get("/api/tank/options")
def api_tank_options():
    return {
        "types": [
            {
                "value": item,
                "description": TANK_TYPE_DESCRIPTIONS[item],
                "focus": TANK_TYPE_FOCUS[item],
                "targets": {
                    element: {"low": low, "high": high, "unit": ELEMENT_IDEALS[element]["unit"]}
                    for element, (low, high) in TANK_TYPE_TARGETS[item].items()
                },
            }
            for item in TANK_TYPES
        ],
        "stages": list(TANK_STAGES),
    }


@app.put("/api/tank")
def api_tank_update(req: TankProfileRequest):
    _validate_tank_request(req)
    tank = update_active_tank(
        req.name, req.water_liters, req.tank_type, req.stage, req.started_at,
        req.custom_targets, req.salt_brand,
    )
    return {
        "ok": True,
        "tank": tank,
        "effective_targets": get_ideals_for_tank(tank["tank_type"], tank.get("custom_targets")),
    }


class MaintenanceRuleRequest(BaseModel):
    interval_days: int = Field(ge=1, le=365)
    enabled: bool = True


class MaintenanceEventRequest(BaseModel):
    task_key: str = Field(min_length=1, max_length=60)
    action: Literal["complete", "postpone"]
    snooze_days: int = Field(default=1, ge=1, le=30)
    note: str = Field(default="", max_length=200)


def _maintenance_context():
    tank = get_active_tank()
    rules = ensure_maintenance_rules(maintenance_defaults(tank))
    return tank, rules


@app.get("/api/today")
def api_today():
    """今日海况、判断依据与轻量维护节奏。"""
    tank, rules = _maintenance_context()
    ideals = get_ideals_for_tank(tank["tank_type"], tank.get("custom_targets"))
    return build_today_dashboard(
        tank=tank,
        ideals=ideals,
        records_by_element=get_records_grouped(),
        water_changes=get_water_changes(),
        dosing_logs=get_dosing_logs(),
        rules=rules,
        events=get_maintenance_events(),
    )


@app.get("/api/maintenance")
def api_maintenance():
    tank, rules = _maintenance_context()
    return {
        "rules": rules,
        "events": get_maintenance_events(limit=100),
        "note": f"这是按{tank['tank_type']} · {tank['stage']}生成的起始节奏，可以按自己的设备和习惯调整。",
    }


@app.put("/api/maintenance/rule/{task_key}")
def api_maintenance_rule_update(task_key: str, req: MaintenanceRuleRequest):
    _, rules = _maintenance_context()
    if task_key not in {rule["task_key"] for rule in rules}:
        raise HTTPException(status_code=404, detail="没有找到这个维护项目")
    update_maintenance_rule(task_key, req.interval_days, req.enabled)
    return {"ok": True, "rules": get_maintenance_rules()}


@app.post("/api/maintenance/event")
def api_maintenance_event_add(req: MaintenanceEventRequest):
    _, rules = _maintenance_context()
    if req.task_key not in {rule["task_key"] for rule in rules}:
        raise HTTPException(status_code=404, detail="没有找到这个维护项目")
    snooze_until = None
    if req.action == "postpone":
        snooze_until = (date.today() + timedelta(days=req.snooze_days)).isoformat()
    rid = add_maintenance_event(req.task_key, req.action, req.note, snooze_until=snooze_until)
    return {"ok": True, "id": rid, "snooze_until": snooze_until}

class AdditiveRequest(BaseModel):
    water_liters: PositiveFiniteFloat       # 水量(升)
    conc_delta: PositiveFiniteFloat         # 提升浓度
    v1: PositiveFiniteFloat                 # 元素当量
    v2: PositiveFiniteFloat                 # 添加物分子量

class AutoDoseRequest(BaseModel):
    water_liters: PositiveFiniteFloat       # 水量(升)
    current_value: NonNegativeFiniteFloat   # 当前实测值
    ideal_low: NonNegativeFiniteFloat       # 参考下限
    ideal_high: PositiveFiniteFloat          # 参考上限
    v1: PositiveFiniteFloat                 # 元素当量
    v2: PositiveFiniteFloat                 # 添加物分子量
    unit: str = "ppm"         # 单位(ppm/dKH)

class MixRequest(BaseModel):
    ro_water_ml: PositiveFiniteFloat        # RO水量(毫升)
    powder_g: PositiveFiniteFloat           # 分析纯量(克)

class DoseRequest(BaseModel):
    ro_water_ml: PositiveFiniteFloat
    powder_g: PositiveFiniteFloat
    element: str              # 钙/镁/KH/钾
    tank_liters: PositiveFiniteFloat        # 缸实际水量(升)
    first_value: NonNegativeFiniteFloat     # 初次测试值
    last_value: NonNegativeFiniteFloat      # 最后测试值
    interval_days: PositiveFiniteFloat      # 测试间隔(天)

class AdjustRequest(BaseModel):
    ro_water_ml: PositiveFiniteFloat
    powder_g: PositiveFiniteFloat
    element: str
    tank_liters: PositiveFiniteFloat
    target_value: NonNegativeFiniteFloat    # 目标值
    current_value: NonNegativeFiniteFloat   # 当前测试值
    plan_days: PositiveFiniteFloat           # 计划提升天数
    current_dose_ml: NonNegativeFiniteFloat = 0  # 当前滴定量(毫升)

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
    element: DosingElement
    dose_ml: PositiveFiniteFloat = Field(description="滴定量必须为正数")
    note: str = Field(default="", max_length=200)
    action: DosingAction = "start"   # start=开始滴定 / end=结束滴定
    recorded_at: str = Field(default="", max_length=10)

@app.post("/api/dosing/log")
def api_dosing_log_add(req: DosingLogRequest):
    """记录一次滴定设置变化（前端自动调用）。"""
    _validate_recorded_at(req.recorded_at)
    rid = add_dosing_log(req.element, req.dose_ml, req.note, req.recorded_at or None, req.action)
    return {"id": rid, "ok": True}

@app.get("/api/dosing/logs")
def api_dosing_logs(element: Optional[DosingElement] = None):
    """获取滴定记录（供趋势图标记）。"""
    return {"logs": get_dosing_logs(element)}

@app.delete("/api/dosing/log/{rid}")
def api_dosing_log_delete(rid: int):
    """删除一条滴定记录。"""
    return _not_found(delete_dosing_log(rid), "滴定记录")

class DosingLogUpdateRequest(BaseModel):
    element: DosingElement
    dose_ml: PositiveFiniteFloat
    note: str = Field(default="", max_length=200)
    action: DosingAction = "start"
    recorded_at: str = Field(default="", max_length=10)

@app.put("/api/dosing/log/{rid}")
def api_dosing_log_update(rid: int, req: DosingLogUpdateRequest):
    """更新一条滴定记录。"""
    _validate_recorded_at(req.recorded_at)
    return _not_found(
        update_dosing_log(rid, req.element, req.dose_ml, req.note, req.recorded_at or None, req.action),
        "滴定记录",
    )

# ---------- 换水记录 API ----------

class WaterChangeRequest(BaseModel):
    water_liters: PositiveFiniteFloat = Field(description="换水量必须为正数")
    salt_grams: Optional[PositiveFiniteFloat] = Field(default=None, description="实际配盐克数可留空")
    salt_brand: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=200)
    recorded_at: str = Field(default="", max_length=10)

@app.post("/api/water-change")
def api_water_change_add(req: WaterChangeRequest):
    _validate_recorded_at(req.recorded_at)
    rid = add_water_change(
        req.water_liters, req.salt_brand, req.note, req.recorded_at or None,
        salt_grams=req.salt_grams,
    )
    return {"id": rid, "ok": True}

@app.get("/api/water-change")
def api_water_change_list():
    return {"changes": get_water_changes()}

@app.delete("/api/water-change/{rid}")
def api_water_change_delete(rid: int):
    return _not_found(delete_water_change(rid), "换水记录")

class WaterChangeUpdateRequest(BaseModel):
    water_liters: PositiveFiniteFloat = Field(description="换水量必须为正数")
    salt_grams: Optional[PositiveFiniteFloat] = Field(default=None, description="实际配盐克数可留空")
    salt_brand: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=200)
    recorded_at: str = Field(default="", max_length=10)

@app.put("/api/water-change/{rid}")
def api_water_change_update(rid: int, req: WaterChangeUpdateRequest):
    _validate_recorded_at(req.recorded_at)
    return _not_found(
        update_water_change(
            rid, req.water_liters, req.salt_brand, req.note, req.recorded_at or None,
            salt_grams=req.salt_grams,
        ),
        "换水记录",
    )

# ---------- 水质记录与分析 API ----------

class RecordRequest(BaseModel):
    element: WaterElement
    value: NonNegativeFiniteFloat = Field(description="测试值不能为负数；NO3、PO4等允许记录0")
    note: str = Field(default="", max_length=200)
    recorded_at: str = Field(default="", max_length=10)   # 可选，默认当前时间


def _validate_zero_value(element: str, value: float):
    """营养盐可记录检测结果0；KH/Ca/Mg等核心参数的0值视为误输入。"""
    if value == 0 and element not in {"NO3", "PO4"}:
        raise HTTPException(status_code=422, detail="只有NO3、PO4允许记录0；请复核该参数读数")

@app.get("/api/water/ideals")
def api_water_ideals():
    """当前鱼缸类型对应的起始参考范围。"""
    tank, ideals = _active_context()
    return {
        "ideals": ideals,
        "tank_type": tank["tank_type"],
        "source": "tank_profile",
        "note": "这是当前缸型的起步参考。看数据时，也一起看看连续走势和缸里的实际状态。",
    }

@app.get("/api/water/records")
def api_water_records(element: Optional[WaterElement] = None):
    """获取记录（可按元素过滤）。"""
    return {"records": get_records(element)}

@app.get("/api/water/elements")
def api_water_elements():
    """已有记录的元素列表。"""
    return {"elements": get_elements()}

@app.post("/api/water/record")
def api_water_add(req: RecordRequest):
    _validate_zero_value(req.element, req.value)
    _validate_recorded_at(req.recorded_at)
    _, ideals = _active_context()
    rid = add_record(req.element, req.value, ideals.get(req.element, {}).get("unit", "ppm"), req.note, req.recorded_at or None)
    return {"id": rid, "ok": True}

@app.delete("/api/water/record/{rid}")
def api_water_delete(rid: int):
    return _not_found(delete_record(rid), "水质记录")

class RecordUpdateRequest(BaseModel):
    element: WaterElement
    value: NonNegativeFiniteFloat = Field(description="测试值不能为负数；NO3、PO4等允许记录0")
    note: str = Field(default="", max_length=200)
    recorded_at: str = Field(default="", max_length=10)

@app.put("/api/water/record/{rid}")
def api_water_update(rid: int, req: RecordUpdateRequest):
    _validate_zero_value(req.element, req.value)
    _validate_recorded_at(req.recorded_at)
    _, ideals = _active_context()
    rid_ok = update_record(rid, req.element, req.value,
                           ideals.get(req.element, {}).get("unit", "ppm"),
                           req.note, req.recorded_at or None)
    return _not_found(rid_ok, "水质记录")

@app.get("/api/water/analysis")
def api_water_analysis():
    """全元素智能分析（L1-L5）。"""
    grouped = get_records_grouped()
    _, ideals = _active_context()
    return {"analysis": analyze_all(grouped, ideals)}

@app.get("/api/water/element-analysis")
def api_water_element_analysis(element: str):
    """单元素分析。"""
    recs = get_records(element)
    data = [(r["recorded_at"], r["value"]) for r in recs]
    _, ideals = _active_context()
    return {"analysis": analyze_element(data, element, ideals.get(element))}

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

def _balance_result(tank_liters, mix_ratio=None):
    """构建收支审计结果；水量与配液数据均不使用静默默认值。"""
    grouped = get_records_grouped()
    logs = get_dosing_logs()
    from datetime import datetime
    data = {}
    for el, recs in grouped.items():
        data[el] = [(datetime.fromisoformat(d), v) for d, v in recs]
    return {"result": balance_audit(data, logs, mix_ratio=mix_ratio, tank_liters=tank_liters)}


@app.get("/api/analysis/balance")
def api_balance(tank_liters: float = None):
    """未显式提供时使用鱼缸档案的实际水量；未设置档案则保持空结果。"""
    if tank_liters is None:
        tank_liters = get_active_tank().get("water_liters")
    return _balance_result(tank_liters)


class BalanceRequest(BaseModel):
    tank_liters: PositiveFiniteFloat
    mix_ratio: dict = Field(default_factory=dict)


@app.post("/api/analysis/balance")
def api_balance_with_mix(req: BalanceRequest):
    """按用户实际水量与各元素真实配液比例做收支估算。"""
    return _balance_result(req.tank_liters, req.mix_ratio)

@app.get("/api/analysis/frequency")
def api_frequency():
    """B1: 测试频率健康度。"""
    grouped = get_records_grouped()
    from datetime import datetime
    data = {}
    for el, recs in grouped.items():
        data[el] = [(datetime.fromisoformat(d), v) for d, v in recs]
    return {"result": test_frequency_health(data)}

@app.get("/api/analysis/linkage")
def api_linkage():
    """元素联动诊断：提供跨元素关联线索与待复核的可能原因。"""
    grouped = get_records_grouped()
    _, ideals = _active_context()
    analysis = analyze_all(grouped, ideals)
    return {"findings": linkage_diagnosis(analysis, ideals)}

# ---------- 前端页面 ----------

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


# ---------- 数据导出 / 导入 ----------
import csv as _csv, io

@app.get("/api/export/json")
def api_export_json():
    """导出全部数据为 JSON 备份（可导入恢复）。"""
    return export_all()

@app.post("/api/import")
def api_import(payload: dict):
    """导入 JSON 备份（按内容去重，重复跳过）。"""
    inserted, skipped = import_all(payload)
    return {"inserted": inserted, "skipped": skipped, "ok": True}

@app.get("/api/export/csv")
def api_export_csv(kind: str = "water"):
    """导出单表为 CSV：kind = water | dosing | change。"""
    buf = io.StringIO()
    if kind == "water":
        rows = get_records(limit=100000)
        if rows:
            w = _csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    elif kind == "dosing":
        rows = get_dosing_logs()
        if rows:
            w = _csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    elif kind == "change":
        rows = get_water_changes(limit=100000)
        if rows:
            w = _csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    else:
        return {"error": "kind 必须是 water/dosing/change"}
    # CSV 需 UTF-8 BOM，Excel 打开中文不乱码
    data = "\ufeff" + buf.getvalue()
    from fastapi.responses import Response
    return Response(content=data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=reefpal_{kind}.csv"})


@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
