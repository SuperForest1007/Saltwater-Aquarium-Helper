# -*- coding: utf-8 -*-
"""
pytest 共享 fixtures：
- 每个测试使用独立的临时数据库（严格隔离，互不污染）
- 提供 TestClient 实例
"""
import os
import sys
import tempfile
import shutil

import pytest

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(scope="function")
def test_client():
    """每个测试独立的临时数据库 TestClient。"""
    # 每个测试独立临时目录
    tmp_dir = tempfile.mkdtemp(prefix="seawater_test_")
    tmp_db = os.path.join(tmp_dir, "test.db")

    # 让 water_store 使用临时数据库
    import water_store
    original_db = water_store.DB_PATH
    water_store.DB_PATH = tmp_db

    # 初始化表
    water_store.init_db()
    water_store.init_dosing_log()
    water_store.init_water_change()
    water_store.init_maintenance()

    # 创建 TestClient
    from fastapi.testclient import TestClient
    import main
    client = TestClient(main.app)

    yield client

    # 清理：恢复DB路径并删除临时目录
    water_store.DB_PATH = original_db
    shutil.rmtree(tmp_dir, ignore_errors=True)
