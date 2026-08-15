# -*- coding: utf-8 -*-
"""
pytest 共享 fixtures：
- 使用临时测试数据库（不污染真实 water_records.db）
- 提供 TestClient 实例
"""
import os
import sys
import tempfile

import pytest

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(scope="session")
def test_client():
    """使用临时数据库的 FastAPI TestClient。"""
    # 临时数据库文件
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

    # 创建 TestClient
    from fastapi.testclient import TestClient
    import main
    client = TestClient(main.app)

    yield client

    # 清理
    water_store.DB_PATH = original_db
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
