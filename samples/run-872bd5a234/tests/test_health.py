"""AC16：健康检查接口。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    """AC16：GET /health → 200, status == "ok"。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
