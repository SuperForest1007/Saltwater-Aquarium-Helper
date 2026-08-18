# -*- coding: utf-8 -*-
"""
记录编辑（PUT）API 测试：水质/换水/滴定记录更新
"""
import pytest


class TestWaterRecordUpdate:
    def test_update_water_record(self, test_client):
        """水质记录：添加→更新→验证。"""
        r = test_client.post("/api/water/record", json={
            "element": "KH", "value": 7.8, "note": "初始", "recorded_at": "2025-02-01"
        })
        rid = r.json()["id"]

        r = test_client.put(f"/api/water/record/{rid}", json={
            "element": "钙", "value": 420.5, "note": "修改后", "recorded_at": "2025-02-02"
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

        recs = test_client.get("/api/water/records").json()["records"]
        assert len(recs) == 1
        rec = recs[0]
        assert rec["element"] == "钙"
        assert rec["value"] == 420.5
        assert rec["note"] == "修改后"
        assert rec["recorded_at"].startswith("2025-02-02")

    def test_update_water_record_unit_follows_element(self, test_client):
        """更新元素后，单位应跟随新元素（KH→dKH）。"""
        r = test_client.post("/api/water/record", json={
            "element": "钙", "value": 400, "recorded_at": "2025-02-01"
        })
        rid = r.json()["id"]
        test_client.put(f"/api/water/record/{rid}", json={
            "element": "KH", "value": 9.0, "recorded_at": "2025-02-03"
        })
        rec = test_client.get("/api/water/records").json()["records"][0]
        assert rec["unit"] == "dKH"

    def test_update_water_record_invalid_value(self, test_client):
        """KH更新为0或负数应返回422；营养盐0值另有专门测试。"""
        r = test_client.post("/api/water/record", json={
            "element": "KH", "value": 7.8, "recorded_at": "2025-02-01"
        })
        rid = r.json()["id"]
        for bad in [0, -3]:
            resp = test_client.put(f"/api/water/record/{rid}", json={
                "element": "KH", "value": bad, "recorded_at": "2025-02-02"
            })
            assert resp.status_code == 422, f"值{bad}应被拒绝"

    def test_update_water_record_not_found(self, test_client):
        """更新不存在的记录应返回ok=False。"""
        r = test_client.put("/api/water/record/99999", json={
            "element": "KH", "value": 8.0, "recorded_at": "2025-02-02"
        })
        assert r.status_code == 200
        assert r.json()["ok"] is False


class TestWaterChangeUpdate:
    def test_update_water_change(self, test_client):
        """换水记录：添加→更新→验证。"""
        r = test_client.post("/api/water-change", json={
            "water_liters": 30, "salt_brand": "红海", "note": "初次", "recorded_at": "2025-03-01"
        })
        cid = r.json()["id"]

        r = test_client.put(f"/api/water-change/{cid}", json={
            "water_liters": 45, "salt_brand": "法红", "note": "修改", "recorded_at": "2025-03-05"
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

        changes = test_client.get("/api/water-change").json()["changes"]
        assert len(changes) == 1
        c = changes[0]
        assert c["water_liters"] == 45
        assert c["salt_brand"] == "法红"
        assert c["note"] == "修改"

    def test_update_water_change_invalid(self, test_client):
        """更新为0/负数换水量应返回422。"""
        r = test_client.post("/api/water-change", json={"water_liters": 30})
        cid = r.json()["id"]
        for bad in [0, -10]:
            resp = test_client.put(f"/api/water-change/{cid}", json={
                "water_liters": bad, "recorded_at": "2025-03-05"
            })
            assert resp.status_code == 422


class TestDosingLogUpdate:
    def test_update_dosing_log(self, test_client):
        """滴定记录：添加→更新→验证。"""
        r = test_client.post("/api/dosing/log", json={
            "element": "KH", "dose_ml": 30, "action": "start", "recorded_at": "2025-04-01"
        })
        lid = r.json()["id"]

        r = test_client.put(f"/api/dosing/log/{lid}", json={
            "element": "钙", "dose_ml": 25.5, "action": "adjust",
            "note": "调整", "recorded_at": "2025-04-10"
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

        logs = test_client.get("/api/dosing/logs").json()["logs"]
        assert len(logs) == 1
        log = logs[0]
        assert log["element"] == "钙"
        assert log["dose_ml"] == 25.5
        assert log["action"] == "adjust"

    def test_update_dosing_log_invalid(self, test_client):
        """更新为0/负数滴定量应返回422。"""
        r = test_client.post("/api/dosing/log", json={
            "element": "KH", "dose_ml": 30, "action": "start", "recorded_at": "2025-04-01"
        })
        lid = r.json()["id"]
        for bad in [0, -5]:
            resp = test_client.put(f"/api/dosing/log/{lid}", json={
                "element": "KH", "dose_ml": bad, "recorded_at": "2025-04-02"
            })
            assert resp.status_code == 422
