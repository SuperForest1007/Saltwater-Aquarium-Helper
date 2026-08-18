# -*- coding: utf-8 -*-
"""
数据备份/导出/导入 API 测试
"""
import json


class TestExport:
    def test_export_json_empty(self, test_client):
        """空库导出 JSON 结构完整。"""
        r = test_client.get("/api/export/json")
        assert r.status_code == 200
        data = r.json()
        assert "water_records" in data
        assert "dosing_log" in data
        assert "water_change" in data
        assert data["water_records"] == []

    def test_export_json_contains_data(self, test_client):
        """导出包含已添加的数据。"""
        test_client.post("/api/water/record", json={"element": "KH", "value": 7.8, "recorded_at": "2025-05-01"})
        test_client.post("/api/water-change", json={"water_liters": 30, "recorded_at": "2025-05-02"})
        test_client.post("/api/dosing/log", json={"element": "KH", "dose_ml": 30, "action": "start", "recorded_at": "2025-05-03"})

        r = test_client.get("/api/export/json")
        data = r.json()
        assert len(data["water_records"]) == 1
        assert len(data["dosing_log"]) == 1
        assert len(data["water_change"]) == 1
        assert data["water_records"][0]["element"] == "KH"
        assert data["water_records"][0]["value"] == 7.8

    def test_export_csv_water(self, test_client):
        """水质 CSV 导出带 BOM 和表头。"""
        test_client.post("/api/water/record", json={"element": "钙", "value": 420, "recorded_at": "2025-05-01"})
        r = test_client.get("/api/export/csv?kind=water")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        # BOM + 表头
        text = r.content.decode("utf-8-sig")
        assert "element" in text
        assert "钙" in text

    def test_export_csv_bad_kind(self, test_client):
        """非法 kind 返回错误。"""
        r = test_client.get("/api/export/csv?kind=xxx")
        assert r.status_code == 200
        assert "error" in r.json()


class TestImport:
    def test_import_json(self, test_client):
        """导入备份数据。"""
        payload = {
            "water_records": [
                {"element": "KH", "value": 8.1, "unit": "dKH", "note": "导入", "recorded_at": "2025-06-01"},
                {"element": "镁", "value": 1320, "unit": "ppm", "note": "", "recorded_at": "2025-06-02"},
            ],
            "dosing_log": [
                {"element": "KH", "dose_ml": 25, "action": "start", "note": "", "recorded_at": "2025-06-03"},
            ],
            "water_change": [
                {"water_liters": 40, "salt_grams": 1440, "salt_brand": "红海", "note": "", "recorded_at": "2025-06-04"},
            ],
        }
        r = test_client.post("/api/import", json=payload)
        assert r.status_code == 200
        result = r.json()
        assert result["ok"] is True
        assert result["inserted"] == 4
        assert result["skipped"] == 0

        # 验证导入的数据可查询
        recs = test_client.get("/api/water/records").json()["records"]
        assert len(recs) == 2
        assert test_client.get("/api/dosing/logs").json()["logs"][0]["dose_ml"] == 25
        imported_change = test_client.get("/api/water-change").json()["changes"][0]
        assert imported_change["water_liters"] == 40
        assert imported_change["salt_grams"] == 1440

    def test_import_deduplicates(self, test_client):
        """重复导入同一数据应跳过。"""
        payload = {
            "water_records": [
                {"element": "KH", "value": 8.1, "unit": "dKH", "note": "", "recorded_at": "2025-06-01"},
            ],
            "dosing_log": [], "water_change": [],
        }
        r1 = test_client.post("/api/import", json=payload).json()
        r2 = test_client.post("/api/import", json=payload).json()
        assert r1["inserted"] == 1
        assert r2["inserted"] == 0
        assert r2["skipped"] == 1
        assert len(test_client.get("/api/water/records").json()["records"]) == 1

    def test_import_bad_payload(self, test_client):
        """非备份结构的数据不应崩溃。"""
        r = test_client.post("/api/import", json={"foo": "bar"})
        assert r.status_code == 200
        assert r.json()["inserted"] == 0

    def test_import_roundtrip(self, test_client):
        """导出→导入→再导出，数据应一致（幂等）。"""
        # 先造数据
        test_client.post("/api/water/record", json={"element": "NO3", "value": 3.5, "recorded_at": "2025-07-01"})
        test_client.post("/api/water-change", json={"water_liters": 25, "recorded_at": "2025-07-02"})
        backup1 = test_client.get("/api/export/json").json()
        # 导入到（同一个）库：应全部跳过
        r = test_client.post("/api/import", json=backup1).json()
        assert r["inserted"] == 0
        assert r["skipped"] == 2
        # 再导出应与第一次一致
        backup2 = test_client.get("/api/export/json").json()
        assert len(backup2["water_records"]) == len(backup1["water_records"])
        assert len(backup2["water_change"]) == len(backup1["water_change"])
