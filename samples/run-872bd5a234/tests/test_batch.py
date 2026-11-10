"""AC17–AC18：批量加法接口。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_batch_success(client: TestClient) -> None:
    """AC17：两个元素 → results == [3, 7]。"""
    resp = client.post(
        "/add/batch",
        json={"items": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]},
    )
    assert resp.status_code == 200
    assert resp.json()["results"] == [3, 7]


def test_batch_invalid_element_index(client: TestClient) -> None:
    """AC18：第二个元素 b 为字符串 → 400, index == 1。"""
    resp = client.post(
        "/add/batch",
        json={"items": [{"a": 1, "b": 2}, {"a": 3, "b": "4"}]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["index"] == 1


def test_batch_missing_items(client: TestClient) -> None:
    """补充分支：缺 items → 400, field == "items"，无 index。"""
    resp = client.post("/add/batch", json={})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["field"] == "items"
    assert "index" not in body


def test_batch_empty_items(client: TestClient) -> None:
    """补充分支：items 为空数组 → 400, field == "items"。"""
    resp = client.post("/add/batch", json={"items": []})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["field"] == "items"


def test_batch_too_many_items(client: TestClient) -> None:
    """补充分支：items 长度 > 100 → 400, field == "items"。"""
    items = [{"a": 1, "b": 1} for _ in range(101)]
    resp = client.post("/add/batch", json={"items": items})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["field"] == "items"


def test_batch_element_not_object(client: TestClient) -> None:
    """补充分支：元素非对象 → 400, index == 0。"""
    resp = client.post("/add/batch", json={"items": [5]})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["index"] == 0
