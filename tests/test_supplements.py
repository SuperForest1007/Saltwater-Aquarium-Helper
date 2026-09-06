from datetime import date, timedelta


def _event_payload(**overrides):
    today = date.today()
    payload = {
        "element": "KH",
        "additive_name": "碳酸氢钠",
        "product_name": "",
        "dose_form": "powder",
        "calculated_amount": 1.2,
        "actual_amount": 1.0,
        "pre_value": 6.8,
        "target_value": 7.5,
        "reference_low": 7.0,
        "reference_high": 8.5,
        "recorded_at": today.isoformat(),
        "recommended_retest_at": (today + timedelta(days=1)).isoformat(),
        "note": "分两次加完",
    }
    payload.update(overrides)
    return payload


def test_create_list_and_cancel_supplement(test_client):
    created = test_client.post("/api/supplement/events", json=_event_payload())
    assert created.status_code == 200
    event = created.json()["event"]
    assert event["status"] == "awaiting_test"
    assert event["amount_unit"] == "g"

    pending = test_client.get("/api/supplement/events/pending").json()["events"]
    assert [row["id"] for row in pending] == [event["id"]]

    cancelled = test_client.post(f"/api/supplement/events/{event['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["event"]["status"] == "cancelled"
    assert test_client.get("/api/supplement/events/pending").json()["events"] == []


def test_link_retest_resolves_event(test_client):
    event = test_client.post("/api/supplement/events", json=_event_payload()).json()["event"]
    water = test_client.post("/api/water/record", json={
        "element": "KH", "value": 7.4, "recorded_at": date.today().isoformat(), "note": "复测"
    }).json()
    linked = test_client.post(
        f"/api/supplement/events/{event['id']}/link-retest", json={"record_id": water["id"]}
    )
    assert linked.status_code == 200
    body = linked.json()
    assert body["event"]["status"] == "resolved"
    assert body["result"]["code"] == "in_range"
    assert "参考范围" in body["result"]["summary"]


def test_link_retest_rejects_wrong_element(test_client):
    event = test_client.post("/api/supplement/events", json=_event_payload()).json()["event"]
    water = test_client.post("/api/water/record", json={
        "element": "钙", "value": 420, "recorded_at": date.today().isoformat(), "note": ""
    }).json()
    linked = test_client.post(
        f"/api/supplement/events/{event['id']}/link-retest", json={"record_id": water["id"]}
    )
    assert linked.status_code == 409
    assert "对不上" in linked.json()["detail"]


def test_supplement_retest_date_validation(test_client):
    payload = _event_payload(
        recorded_at=date.today().isoformat(),
        recommended_retest_at=(date.today() - timedelta(days=1)).isoformat(),
    )
    response = test_client.post("/api/supplement/events", json=payload)
    assert response.status_code == 422


def test_today_surfaces_due_supplement_retest(test_client):
    test_client.put("/api/tank", json={
        "name": "测试缸", "water_liters": 46, "tank_type": "LPS", "stage": "稳定期",
        "started_at": "", "custom_targets": {}, "salt_brand": "",
    })
    payload = _event_payload(recommended_retest_at=date.today().isoformat())
    event = test_client.post("/api/supplement/events", json=payload).json()["event"]
    today = test_client.get("/api/today").json()
    action = next(item for item in today["actions"] if item["action_type"] == "retest")
    assert action["element"] == "KH"
    assert action["supplement_event_id"] == event["id"]
    assert "碳酸氢钠" in action["reason"]


def test_backup_roundtrip_includes_supplements(test_client):
    test_client.post("/api/supplement/events", json=_event_payload())
    exported = test_client.get("/api/export/json").json()
    assert exported["schema_version"] == 7
    assert len(exported["supplement_events"]) == 1

    imported = test_client.post("/api/import", json=exported)
    assert imported.status_code == 200
    assert len(test_client.get("/api/supplement/events").json()["events"]) == 1
