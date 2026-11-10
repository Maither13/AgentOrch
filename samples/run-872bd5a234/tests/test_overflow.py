"""AC19：非有限结果错误码。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_add_overflow(client: TestClient) -> None:
    """AC19：1e308 + 1e308 → 422 RESULT_NOT_FINITE。"""
    resp = client.post("/add", json={"a": 1e308, "b": 1e308})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "RESULT_NOT_FINITE"
    assert body["message"].strip()


def test_batch_overflow_index(client: TestClient) -> None:
    """补充分支：批量中元素溢出 → 422, index 指向该元素。"""
    resp = client.post(
        "/add/batch",
        json={"items": [{"a": 1, "b": 2}, {"a": 1e308, "b": 1e308}]},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "RESULT_NOT_FINITE"
    assert body["index"] == 1
