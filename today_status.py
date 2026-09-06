# -*- coding: utf-8 -*-
"""“本缸今日状态”聚合逻辑：把水质判断和维护节奏整理成可解释的工作台。"""
from datetime import date, datetime, timedelta

from water_quality import analyze_all


ELEMENT_ORDER = ("KH", "钙", "镁", "NO3", "PO4")
ELEMENT_LABELS = {"KH": "KH", "钙": "钙", "镁": "镁", "NO3": "NO₃", "PO4": "PO₄"}
OBSERVATION_LABELS = {"good": "状态不错", "changed": "有点变化", "watch": "需要留意"}
OBSERVATION_TAG_LABELS = {
    "coral": "珊瑚状态", "fish": "鱼只 / 摄食", "algae": "藻相",
    "equipment": "水流 / 设备", "other": "其他",
}


def maintenance_defaults(tank):
    """按缸型和阶段给出保守的起始节奏；用户修改后由存储层保留。"""
    tank_type = tank.get("tank_type") or "混养"
    stage = tank.get("stage") or "稳定期"
    active_stage = stage in ("开缸期", "调整期")

    if tank_type == "FOT":
        core_title, core_elements, core_days = "测 KH", ["KH"], 14 if not active_stage else 7
    else:
        core_title, core_elements, core_days = "测 KH / 钙 / 镁", ["KH", "钙", "镁"], 7 if not active_stage else 3

    nutrient_days = 4 if active_stage or tank_type == "NPS" else 7
    change_days = 10 if tank_type in ("FOT", "NPS") else 14
    if stage == "筹备中":
        change_days = 14

    return [
        {"task_key": "water_core", "title": core_title, "category": "水质检测", "interval_days": core_days,
         "icon": "⌁", "elements": core_elements, "record_source": "water"},
        {"task_key": "nutrients", "title": "测 NO₃ / PO₄", "category": "水质检测", "interval_days": nutrient_days,
         "icon": "◌", "elements": ["NO3", "PO4"], "record_source": "water"},
        {"task_key": "water_change", "title": "换水", "category": "基础维护", "interval_days": change_days,
         "icon": "↻", "record_source": "water_change"},
        {"task_key": "mechanical_filter", "title": "清洁机械过滤", "category": "设备维护", "interval_days": 3,
         "icon": "▦", "record_source": "maintenance"},
        {"task_key": "skimmer_cup", "title": "清理蛋分杯", "category": "设备维护", "interval_days": 7,
         "icon": "◒", "record_source": "maintenance"},
    ]


def _as_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _days_text(days):
    if days == 0:
        return "今天"
    if days == 1:
        return "明天"
    if days > 1:
        return f"{days} 天后"
    if days == -1:
        return "昨天到期"
    return f"已过 {abs(days)} 天"


def _plain_advice(text):
    """首页用更像养缸记录的语气，去掉分析模块用于列表识别的前缀图标。"""
    return (text or "").lstrip("⚠️📅🪸📉↗➡📈↘✅📊 ")


def _latest_by_element(records_by_element):
    latest = {}
    for element, records in records_by_element.items():
        parsed = [(_as_datetime(d), float(v)) for d, v in records]
        parsed = [(d, v) for d, v in parsed if d is not None]
        if parsed:
            latest[element] = max(parsed, key=lambda item: item[0])
    return latest


def _observation_context(observations, now):
    valid = [(item, _as_datetime(item.get("recorded_at"))) for item in observations or []]
    valid = [(item, recorded_at) for item, recorded_at in valid if recorded_at]
    if not valid:
        return None
    item, recorded_at = max(valid, key=lambda entry: (entry[1], int(entry[0].get("id") or 0)))
    status = item.get("status") if item.get("status") in OBSERVATION_LABELS else "changed"
    tags = [tag for tag in item.get("tags") or [] if tag in OBSERVATION_TAG_LABELS]
    note = str(item.get("note") or "").strip()
    if note:
        summary = note
    elif tags:
        summary = "、".join(OBSERVATION_TAG_LABELS[tag] for tag in tags)
    else:
        summary = {
            "good": "整体看着和平时差不多",
            "changed": "有些地方和平时不太一样",
            "watch": "有一处想接着观察",
        }[status]
    age_days = max(0, (now.date() - recorded_at.date()).days)
    return {
        "id": item.get("id"), "status": status, "label": OBSERVATION_LABELS[status],
        "tags": tags, "note": note, "summary": summary,
        "recorded_at": recorded_at.isoformat(), "age_days": age_days,
        "is_today": recorded_at.date() == now.date(),
    }


def _build_recent_events(records_by_element, water_changes, dosing_logs, observations=None,
                         supplement_events=None, now=None):
    """把现有记录投影成今日页的轻量时间线，不另存一份事件数据。"""
    recent = []
    measurements = []
    for element, records in records_by_element.items():
        for recorded_at, value in records:
            measured_at = _as_datetime(recorded_at)
            if measured_at:
                measurements.append((measured_at, element, float(value)))
    if measurements:
        newest_at = max(item[0] for item in measurements)
        same_day = [item for item in measurements if item[0].date() == newest_at.date()]
        latest_per_element = {}
        for measured_at, element, value in same_day:
            previous = latest_per_element.get(element)
            if previous is None or measured_at >= previous[0]:
                latest_per_element[element] = (measured_at, value)
        labels = [ELEMENT_LABELS.get(element, element) for element in ELEMENT_ORDER if element in latest_per_element]
        recent.append({
            "kind": "water", "icon": "⌁", "title": "记录水质",
            "detail": " / ".join(labels) if labels else "新读数已记下",
            "recorded_at": newest_at.isoformat(),
        })

    valid_changes = [(item, _as_datetime(item.get("recorded_at"))) for item in water_changes]
    valid_changes = [(item, recorded_at) for item, recorded_at in valid_changes if recorded_at]
    if valid_changes:
        change, changed_at = max(valid_changes, key=lambda item: item[1])
        liters = float(change.get("water_liters") or 0)
        liters_text = f"{liters:g} L" if liters else "已记录"
        brand = str(change.get("salt_brand") or "").strip()
        recent.append({
            "kind": "water_change", "icon": "↻", "title": "完成换水",
            "detail": liters_text + (f" · {brand}" if brand else ""),
            "recorded_at": changed_at.isoformat(),
        })

    valid_logs = [(item, _as_datetime(item.get("recorded_at"))) for item in dosing_logs]
    valid_logs = [(item, recorded_at) for item, recorded_at in valid_logs if recorded_at]
    if valid_logs:
        log, logged_at = max(valid_logs, key=lambda item: (item[1], int(item[0].get("id") or 0)))
        action = {"start": "启用", "end": "停用", "adjust": "调整"}.get(log.get("action"), "更新")
        dose = float(log.get("dose_ml") or 0)
        recent.append({
            "kind": "dosing", "icon": "∿", "title": f"{action} {log.get('element') or ''} 滴定".replace("  ", " ").strip(),
            "detail": f"{dose:g} ml/天" if dose else "方案已更新",
            "recorded_at": logged_at.isoformat(),
        })

    observation = _observation_context(observations, now or datetime.now())
    if observation:
        recent.append({
            "kind": "observation", "icon": "◉", "title": "看过一圈",
            "detail": observation["label"] + " · " + observation["summary"],
            "recorded_at": observation["recorded_at"],
        })

    valid_supplements = [(item, _as_datetime(item.get("recorded_at"))) for item in supplement_events or []]
    valid_supplements = [(item, recorded_at) for item, recorded_at in valid_supplements if recorded_at]
    if valid_supplements:
        item, recorded_at = max(valid_supplements, key=lambda entry: (entry[1], int(entry[0].get("id") or 0)))
        amount = float(item.get("actual_amount") or 0)
        unit = item.get("amount_unit") or ""
        recent.append({
            "kind": "supplement", "icon": "+", "title": f"补了 {item.get('element') or ''}".strip(),
            "detail": f"{amount:g} {unit} · 等复测",
            "recorded_at": recorded_at.isoformat(),
        })

    recent.sort(key=lambda item: _as_datetime(item["recorded_at"]) or datetime.min, reverse=True)
    return recent[:3]


def _latest_event(events, task_key, action=None):
    matches = [e for e in events if e.get("task_key") == task_key and (action is None or e.get("action") == action)]
    if not matches:
        return None
    return max(matches, key=lambda e: _as_datetime(e.get("recorded_at")) or datetime.min)


def _task_baseline(rule, latest_elements, water_changes, events):
    source = rule.get("record_source")
    if source == "water":
        dates = [latest_elements.get(el, (None, None))[0] for el in rule.get("elements", [])]
        if not dates or any(d is None for d in dates):
            return None
        return min(dates)
    if source == "water_change":
        dates = [_as_datetime(item.get("recorded_at")) for item in water_changes]
        dates = [d for d in dates if d]
        return max(dates) if dates else None
    event = _latest_event(events, rule["task_key"], "complete")
    return _as_datetime(event.get("recorded_at")) if event else None


def build_maintenance_rhythm(rules, events, latest_elements, water_changes, now=None):
    now = now or datetime.now()
    today = now.date()
    rhythm = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        interval = max(1, int(rule.get("interval_days") or 1))
        baseline = _task_baseline(rule, latest_elements, water_changes, events)
        postpone = _latest_event(events, rule["task_key"], "postpone")
        postpone_until = _as_datetime(postpone.get("snooze_until")) if postpone else None
        if baseline is None:
            if rule.get("record_source") == "water":
                due_date = today
                state = "due"
                timing = "记录还不完整"
                reason = "再补一组记录，就能按这口缸的实际间隔往后排了"
            else:
                due_date = None
                state = "untracked"
                timing = "尚未建立节奏"
                reason = "做完一次点“完成”，之后会按实际周期提醒"
        else:
            due_date = baseline.date() + timedelta(days=interval)
            if postpone_until and postpone_until.date() > due_date:
                due_date = postpone_until.date()
            delta = (due_date - today).days
            state = "overdue" if delta < 0 else ("due" if delta == 0 else ("soon" if delta <= 3 else "later"))
            timing = _days_text(delta)
            reason = f"上次 {baseline.strftime('%m月%d日')} · 当前周期 {interval} 天"

        rhythm.append({
            "task_key": rule["task_key"], "title": rule["title"], "category": rule.get("category", "维护"),
            "icon": rule.get("icon", "·"), "interval_days": interval, "state": state,
            "due_date": due_date.isoformat() if due_date else None, "timing": timing, "reason": reason,
            "action_type": "record" if rule.get("record_source") in ("water", "water_change") else "complete",
            "target_tab": "water" if rule.get("record_source") == "water" else ("salt" if rule.get("record_source") == "water_change" else None),
        })
    order = {"overdue": 0, "due": 1, "soon": 2, "untracked": 3, "later": 4}
    rhythm.sort(key=lambda item: (order.get(item["state"], 9), item.get("due_date") or "9999"))
    return rhythm


def build_today_dashboard(tank, ideals, records_by_element, water_changes, dosing_logs, rules, events,
                          observations=None, supplement_events=None, now=None):
    now = now or datetime.now()
    if not tank.get("setup_complete"):
        return {
            "status": {"code": "setup", "label": "鱼缸档案还差几项", "tone": "neutral",
                       "summary": "实际水量、主要类型和当前阶段填好后，这口缸的维护节奏就能排起来了。"},
            "coverage": {"count": 0, "total": len(ELEMENT_ORDER), "latest_date": None, "label": "尚未开始"},
            "evidence": [], "actions": [], "rhythm": [], "insights": [], "recent_events": [],
            "observation": None,
            "basis_note": "现在的记录还不够，先不急着下结论。",
        }

    latest = _latest_by_element(records_by_element)
    analysis = analyze_all(records_by_element, ideals)
    freshness_by_element = {}
    for rule in rules:
        if rule.get("record_source") != "water" or not rule.get("enabled", True):
            continue
        interval = max(1, int(rule.get("interval_days") or 1))
        for element in rule.get("elements", []):
            freshness_by_element[element] = interval
    evidence = []
    fresh_count = 0
    newest = None
    priority_findings = []
    for element in ELEMENT_ORDER:
        current = latest.get(element)
        item = analysis.get(element)
        if not current or not item:
            evidence.append({"element": element, "label": ELEMENT_LABELS[element], "state": "missing", "state_label": "未记录"})
            continue
        measured_at, value = current
        age = max(0, (now.date() - measured_at.date()).days)
        newest = max(newest, measured_at) if newest else measured_at
        freshness_days = freshness_by_element.get(element, 14)
        fresh = age <= freshness_days
        if fresh:
            fresh_count += 1
        level = item.get("status", "no_data")
        direction = item.get("signals", {}).get("direction", "stable")
        level_label = {"ok": "范围内", "low": "偏低", "high": "偏高"}.get(level, "待判断")
        direction_label = {"stable": "平稳", "rising": "上升", "falling": "下降"}.get(direction, "")
        evidence.append({
            "element": element, "label": ELEMENT_LABELS[element], "value": value,
            "unit": ideals.get(element, {}).get("unit", ""), "state": "stale" if not fresh else level,
            "state_label": f"{age}天前 · 该复测了" if not fresh else f"{level_label} · {direction_label}",
            "measured_at": measured_at.strftime("%Y-%m-%d"), "age_days": age,
            "freshness_days": freshness_days,
        })
        advice = item.get("advice") or {}
        priority = int(advice.get("priority") or 0)
        if fresh and priority >= 35:
            priority_findings.append({
                "element": element, "priority": priority, "summary": _plain_advice(advice.get("summary") or ""),
                "level": level, "anomaly": item.get("signals", {}).get("anomaly"),
                "direction": direction, "count": item.get("signals", {}).get("count", 0),
            })

    priority_findings.sort(key=lambda item: item["priority"], reverse=True)
    severe = [item for item in priority_findings if item.get("anomaly") or (
        item["priority"] >= 70 and item.get("count", 0) >= 2 and item.get("direction") in ("rising", "falling")
    )]
    warnings = [item for item in priority_findings if item["priority"] >= 35]

    if severe:
        top = severe[0]
        status = {"code": "priority", "label": "有一项先留意", "tone": "danger",
                  "summary": top["summary"]}
    elif warnings:
        top = warnings[0]
        status = {"code": "attention", "label": "有一项值得留意", "tone": "warn",
                  "summary": top["summary"]}
    elif fresh_count >= 3:
        status = {"code": "stable", "label": "目前整体平稳", "tone": "ok",
                  "summary": "这几组记录没看到明显越界或异常趋势，照现在的节奏养着就好。"}
    elif latest:
        status = {"code": "insufficient", "label": "再记几项会更清楚", "tone": "neutral",
                  "summary": "手头已经有些数据了，不过还看不全整缸趋势。把关键水质补齐，再判断更踏实。"}
    else:
        status = {"code": "insufficient", "label": "从第一组数据开始", "tone": "neutral",
                  "summary": "记下第一组关键水质，后面的每次测试都会让这口缸更好读懂。"}

    rhythm = build_maintenance_rhythm(rules, events, latest, water_changes, now)
    observation = _observation_context(observations, now)
    due_tasks = [item for item in rhythm if item["state"] in ("overdue", "due")]
    actions = due_tasks[:3]
    pending_retests = []
    for item in supplement_events or []:
        if item.get("status") != "awaiting_test":
            continue
        retest_at = _as_datetime(item.get("recommended_retest_at"))
        recorded_at = _as_datetime(item.get("recorded_at"))
        if not retest_at or retest_at.date() > now.date() + timedelta(days=1):
            continue
        delta = (retest_at.date() - now.date()).days
        amount = float(item.get("actual_amount") or 0)
        unit = item.get("amount_unit") or ""
        pending_retests.append({
            "task_key": f"supplement_retest_{item.get('id')}",
            "title": "复测 " + ELEMENT_LABELS.get(item.get("element"), item.get("element") or "水质"),
            "category": "补充回看", "icon": "↻",
            "state": "overdue" if delta < 0 else ("due" if delta == 0 else "soon"),
            "timing": _days_text(delta),
            "reason": (
                (recorded_at.strftime("%m月%d日") + "补过 " if recorded_at else "上次补过 ")
                + f"{amount:g} {unit} {item.get('additive_name') or ''}，看看这次读数怎么走"
            ),
            "action_type": "retest", "target_tab": "water",
            "element": item.get("element"), "supplement_event_id": item.get("id"),
        })
    pending_retests.sort(key=lambda item: (0 if item["state"] == "overdue" else 1, item["task_key"]))
    actions = (pending_retests + actions)[:3]
    action_finding = severe[0] if severe else (warnings[0] if warnings and warnings[0]["priority"] >= 50 else None)
    if action_finding:
        actions.insert(0, {"task_key": "water_warning", "title": "复核 " + ELEMENT_LABELS.get(action_finding["element"], action_finding["element"]),
                           "category": "水质复核", "icon": "!", "state": "due", "timing": "优先" if severe else "建议复核",
                           "reason": action_finding["summary"], "action_type": "record", "target_tab": "water"})
        actions = actions[:3]

    if not observation or not observation["is_today"]:
        if observation:
            timing = f"上次 {observation['age_days']} 天前"
            reason = "再扫一眼，看看和上次有没有变化"
        else:
            timing = ""
            reason = "看看珊瑚、鱼和设备，记下今天的状态"
        reef_round = {
            "task_key": "reef_round", "title": "看一圈", "category": "整缸观察",
            "icon": "◉", "state": "due", "timing": timing, "reason": reason,
            "action_type": "observe", "target_tab": None,
        }
        actions.insert(1 if action_finding else 0, reef_round)
        actions = actions[:3]

    insights = [item["summary"] for item in priority_findings[:3] if item.get("summary")]
    if not insights and fresh_count >= 3:
        insights = ["关键数据目前没有明显越界；稳定期里，少动往往比频繁调整更好。"]

    coverage_label = f"{fresh_count}/{len(ELEMENT_ORDER)} 项仍在各自检测周期内"
    latest_date = newest.strftime("%Y-%m-%d") if newest else None
    return {
        "status": status,
        "coverage": {"count": fresh_count, "total": len(ELEMENT_ORDER), "latest_date": latest_date, "label": coverage_label},
        "evidence": evidence, "actions": actions, "rhythm": rhythm, "insights": insights,
        "recent_events": _build_recent_events(
            records_by_element, water_changes, dosing_logs, observations, supplement_events, now
        ),
        "observation": observation,
        "basis_note": (
            f"参考范围按 {tank.get('tank_type', '当前')} · {tank.get('stage', '当前阶段')} 生成，只看已经记下的数据。"
            + ("今天的整缸观察也已经放进礁况里；它记录的是当时所见，不替代逐项排查。"
               if observation and observation["is_today"]
               else "最近还没有整缸观察，生物状态和设备运行要留在判断里。")
        ),
    }
