"""pytest 公共 fixture：TestClient（AC14 一键执行，无需起真实端口）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    """返回 FastAPI TestClient 实例。"""
    return TestClient(app)
