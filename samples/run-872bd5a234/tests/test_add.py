"""AC1–AC15：/add 正常路径、参数校验、错误形状。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

JSON_HEADERS = {"Content-Type": "application/json"}


def test_add_integers(client: TestClient) -> None:
    """AC1：{"a":1,"b":2} → 200, result == 3。"""
    resp = client.post("/add", json={"a": 1, "b": 2})
    assert resp.status_code == 200
    assert resp.json()["result"] == 3


def test_add_float_and_int(client: TestClient) -> None:
    """AC2：{"a":1.5,"b":2} → 200, result == 3.5。"""
    resp = client.post("/add", json={"a": 1.5, "b": 2})
    assert resp.status_code == 200
    assert resp.json()["result"] == 3.5


def test_add_echoes_operands(client: TestClient) -> None:
    """AC3：响应含 a、b 且等于请求值。"""
    resp = client.post("/add", json={"a": 1.5, "b": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["a"] == 1.5
    assert body["b"] == 2


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (-5, 3, -2),
        (0, 0, 0),
        (-1.5, -2.5, -4.0),
    ],
)
def test_add_negative_zero_float(
    client: TestClient, a: float, b: float, expected: float
) -> None:
    """AC4：负数、零、小数。"""
    resp = client.post("/add", json={"a": a, "b": b})
    assert resp.status_code == 200
    assert resp.json()["result"] == expected


def test_add_ieee754_strict(client: TestClient) -> None:
    """AC5：0.1 + 0.2 严格等于 0.30000000000000004，不做舍入。"""
    resp = client.post("/add", json={"a": 0.1, "b": 0.2})
    assert resp.status_code == 200
    assert resp.json()["result"] == 0.30000000000000004
    assert resp.json()["result"] == 0.1 + 0.2


def test_missing_b(client: TestClient) -> None:
    """AC6：缺 b → 400 INVALID_ARGUMENT, field == "b"。"""
    resp = client.post("/add", json={"a": 1})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["field"] == "b"


def test_missing_a(client: TestClient) -> None:
    """AC7：缺 a → 400 INVALID_ARGUMENT, field == "a"。"""
    resp = client.post("/add", json={"b": 1})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["field"] == "a"


def test_string_number_rejected(client: TestClient) -> None:
    """AC8：字符串数字必须被拒。"""
    resp = client.post("/add", json={"a": "1", "b": 2})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["field"] == "a"


def test_boolean_rejected(client: TestClient) -> None:
    """AC9：布尔值必须被拒（isinstance(True, int) 陷阱）。"""
    resp = client.post("/add", json={"a": True, "b": 2})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["field"] == "a"


def test_null_rejected(client: TestClient) -> None:
    """AC10：null 必须被拒。"""
    resp = client.post("/add", json={"a": None, "b": 2})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["field"] == "a"


def test_invalid_json(client: TestClient) -> None:
    """AC11：非 JSON body → 400 INVALID_JSON。"""
    resp = client.post("/add", content=b"not-json", headers=JSON_HEADERS)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_JSON"


def test_empty_body(client: TestClient) -> None:
    """AC11 补充：空 body → 400 INVALID_JSON。"""
    resp = client.post("/add", content=b"", headers=JSON_HEADERS)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_JSON"


def test_unsupported_media_type(client: TestClient) -> None:
    """AC12：Content-Type: text/plain → 415（且先于 JSON 解析，C4）。"""
    resp = client.post(
        "/add",
        content=b"not-json",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code == 415
    assert resp.json()["error_code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_charset_suffix_accepted(client: TestClient) -> None:
    """AC12 补充：application/json; charset=utf-8 应被接受。"""
    resp = client.post(
        "/add",
        content=b'{"a": 1, "b": 2}',
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert resp.status_code == 200
    assert resp.json()["result"] == 3


@pytest.mark.parametrize(
    ("payload", "headers"),
    [
        ({"a": "1", "b": 2}, JSON_HEADERS),
        ({"a": 1}, JSON_HEADERS),
        ({"a": None, "b": 2}, JSON_HEADERS),
        ({"a": True, "b": 2}, JSON_HEADERS),
        (b"not-json", JSON_HEADERS),
        (b"not-json", {"Content-Type": "text/plain"}),
        ({"a": 1e308, "b": 1e308}, JSON_HEADERS),
    ],
)
def test_error_shape(client: TestClient, payload, headers) -> None:
    """AC13：所有错误响应体均为合法 JSON，含非空 error_code 与 message。"""
    if isinstance(payload, bytes):
        resp = client.post("/add", content=payload, headers=headers)
    else:
        resp = client.post("/add", json=payload, headers=headers)
    assert resp.status_code >= 400
    body = resp.json()  # 解析失败会抛异常，即证明不是合法 JSON
    assert isinstance(body.get("error_code"), str) and body["error_code"]
    assert isinstance(body.get("message"), str) and body["message"].strip()


def test_non_object_body_rejected(client: TestClient) -> None:
    """补充分支：body 为数组 → 400 INVALID_ARGUMENT。"""
    resp = client.post("/add", json=[1, 2])
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_ARGUMENT"


def test_empty_object_rejected(client: TestClient) -> None:
    """补充分支：body 为 {} → 400 INVALID_ARGUMENT, field == "a"。"""
    resp = client.post("/add", json={})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_ARGUMENT"
    assert body["field"] == "a"
