"""pytest 公共夹具：TestClient + 三角色 token + 数据工厂。

设计约束（来自 tasks/S2.md 裁决）：
- 鉴权：静态 Bearer Token，token-admin / token-teacher / token-student-1 / token-student-2
- 每个测试用例使用独立的内存 SQLite（fixture 级隔离），用例相互独立、可重复执行
- 不依赖外部网络
"""
from __future__ import annotations

import itertools
import uuid

import pytest

# ---------------------------------------------------------------------------
# 应用导入：实现尚未落地时，整个测试目录应被 skip 而不是 error
# ---------------------------------------------------------------------------
APP_IMPORT_ERROR: str | None = None
try:  # pragma: no cover - 导入路径由开发实现决定
    from app.main import app  # type: ignore
except Exception as exc:  # noqa: BLE001
    app = None
    APP_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

try:
    from fastapi.testclient import TestClient  # type: ignore
except Exception as exc:  # noqa: BLE001
    TestClient = None
    APP_IMPORT_ERROR = APP_IMPORT_ERROR or f"TestClient 不可用: {type(exc).__name__}: {exc}"


# 固定测试凭证（S2 §5.5）
TOKEN_ADMIN = "token-admin"
TOKEN_TEACHER = "token-teacher"
TOKEN_STUDENT_1 = "token-student-1"
TOKEN_STUDENT_2 = "token-student-2"

API = "/api/v1"

_seq = itertools.count(1)


def _uniq(prefix: str = "") -> str:
    """生成唯一后缀，避免同一测试内多次创建时撞唯一键。"""
    return f"{prefix}{next(_seq)}{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="session", autouse=True)
def _require_app():
    if app is None or TestClient is None:
        pytest.skip(f"应用不可导入，跳过集成测试（原因：{APP_IMPORT_ERROR}）")


@pytest.fixture()
def client():
    """每个用例一个全新的 TestClient（内存库由应用自身按测试环境创建）。"""
    with TestClient(app) as c:  # with 触发 startup/shutdown（建表/清库）
        yield c


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers() -> dict:
    return auth(TOKEN_ADMIN)


@pytest.fixture()
def teacher_headers() -> dict:
    return auth(TOKEN_TEACHER)


@pytest.fixture()
def student1_headers() -> dict:
    return auth(TOKEN_STUDENT_1)


@pytest.fixture()
def student2_headers() -> dict:
    return auth(TOKEN_STUDENT_2)


# ---------------------------------------------------------------------------
# 数据工厂
# ---------------------------------------------------------------------------
@pytest.fixture()
def make_student(client, admin_headers):
    def _make(**overrides) -> dict:
        payload = {
            "student_no": _uniq("S"),
            "name": "张三",
            "class_name": "一班",
            "grade_year": 2024,
            "status": "active",
        }
        payload.update(overrides)
        resp = client.post(f"{API}/students", json=payload, headers=admin_headers)
        assert resp.status_code == 201, f"创建学生失败: {resp.status_code} {resp.text}"
        return resp.json()

    return _make


@pytest.fixture()
def make_course(client, admin_headers):
    def _make(**overrides) -> dict:
        payload = {
            "course_code": _uniq("C"),
            "name": "数学",
            "credit": 3.0,
            "full_score": 100,
        }
        payload.update(overrides)
        resp = client.post(f"{API}/courses", json=payload, headers=admin_headers)
        assert resp.status_code == 201, f"创建课程失败: {resp.status_code} {resp.text}"
        return resp.json()

    return _make


@pytest.fixture()
def make_score(client, admin_headers):
    def _make(student_id: str, course_id: str, score=80, semester="2024-1", **overrides) -> dict:
        payload = {
            "student_id": student_id,
            "course_id": course_id,
            "semester": semester,
            "score": score,
            "operator_id": "op-admin",
        }
        payload.update(overrides)
        resp = client.post(f"{API}/scores", json=payload, headers=admin_headers)
        assert resp.status_code == 201, f"录入成绩失败: {resp.status_code} {resp.text}"
        return resp.json()

    return _make


@pytest.fixture()
def assert_error():
    """统一断言错误响应结构：{error_code, message, details}。"""

    def _assert(resp, status: int, error_code: str):
        assert resp.status_code == status, f"期望 HTTP {status}，实际 {resp.status_code}: {resp.text}"
        body = resp.json()
        assert isinstance(body, dict), f"错误响应应为 JSON 对象，实际: {body!r}"
        assert body.get("error_code") == error_code, f"期望 error_code={error_code}，实际 {body.get('error_code')}: {body}"
        assert isinstance(body.get("message"), str) and body["message"], "message 必须为非空字符串"
        assert "details" in body, "错误响应必须包含 details 字段（可为 null）"
        return body

    return _assert
