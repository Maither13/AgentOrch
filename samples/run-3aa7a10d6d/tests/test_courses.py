"""课程管理（F2）：AC7–AC8、AC27（课程侧）。"""
from __future__ import annotations

from conftest import API


# --------------------------- AC7 正常创建 ---------------------------
def test_ac7_create_course_default_full_score(client, admin_headers):
    resp = client.post(
        f"{API}/courses",
        json={"course_code": "MATH01", "name": "高等数学", "credit": 4.0},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert isinstance(body.get("id"), str) and body["id"]
    assert body["course_code"] == "MATH01"
    assert body["name"] == "高等数学"
    assert body["credit"] == 4.0
    assert body["full_score"] == 100, "full_score 未提供时应默认 100"
    assert body.get("created_at") and body.get("updated_at")


def test_ac7_create_course_custom_full_score(client, admin_headers):
    resp = client.post(
        f"{API}/courses",
        json={"course_code": "PHY01", "name": "物理", "credit": 0.5, "full_score": 150},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["full_score"] == 150


# --------------------------- AC8 重复编号 / credit 越界 ---------------------------
def test_ac8_duplicated_course_code(client, admin_headers, make_course, assert_error):
    make_course(course_code="DUP01")
    resp = client.post(
        f"{API}/courses",
        json={"course_code": "DUP01", "name": "重复课程", "credit": 2.0},
        headers=admin_headers,
    )
    assert_error(resp, 409, "COURSE_CODE_DUPLICATED")


def test_ac8_credit_zero_rejected(client, admin_headers, assert_error):
    resp = client.post(
        f"{API}/courses",
        json={"course_code": "CR0", "name": "零学分", "credit": 0},
        headers=admin_headers,
    )
    assert_error(resp, 400, "VALIDATION_ERROR")


def test_ac8_credit_eleven_rejected(client, admin_headers, assert_error):
    resp = client.post(
        f"{API}/courses",
        json={"course_code": "CR11", "name": "超学分", "credit": 11},
        headers=admin_headers,
    )
    assert_error(resp, 400, "VALIDATION_ERROR")


def test_ac8_credit_step_half_rejected(client, admin_headers, assert_error):
    """credit 步长 0.5：2.3 应被拒绝（§4.2）。"""
    resp = client.post(
        f"{API}/courses",
        json={"course_code": "CR23", "name": "步长非法", "credit": 2.3},
        headers=admin_headers,
    )
    assert_error(resp, 400, "VALIDATION_ERROR")


def test_ac8_course_code_too_short(client, admin_headers, assert_error):
    resp = client.post(
        f"{API}/courses",
        json={"course_code": "A", "name": "短编号", "credit": 1.0},
        headers=admin_headers,
    )
    assert_error(resp, 400, "VALIDATION_ERROR")


# --------------------------- 查询 / 更新（§4.2） ---------------------------
def test_get_course_by_id_and_not_found(client, admin_headers, make_course, assert_error):
    course = make_course(name="化学")
    ok = client.get(f"{API}/courses/{course['id']}", headers=admin_headers)
    assert ok.status_code == 200
    assert ok.json()["name"] == "化学"
    assert_error(client.get(f"{API}/courses/nope", headers=admin_headers), 404, "COURSE_NOT_FOUND")


def test_list_courses_keyword(client, admin_headers, make_course):
    make_course(course_code="BIO01", name="生物")
    make_course(course_code="HIS01", name="历史")
    resp = client.get(f"{API}/courses", params={"keyword": "生物"}, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["course_code"] == "BIO01"


def test_patch_course_updates_fields(client, admin_headers, make_course):
    course = make_course(name="旧课程", credit=2.0)
    resp = client.patch(
        f"{API}/courses/{course['id']}",
        json={"name": "新课程", "credit": 3.5, "full_score": 120},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "新课程"
    assert body["credit"] == 3.5
    assert body["full_score"] == 120
    assert body["course_code"] == course["course_code"], "course_code 不可修改"


def test_patch_course_code_immutable(client, admin_headers, make_course, assert_error):
    course = make_course()
    assert_error(
        client.patch(f"{API}/courses/{course['id']}", json={"course_code": "NEWCODE"}, headers=admin_headers),
        400,
        "VALIDATION_ERROR",
    )


def test_patch_course_not_found(client, admin_headers, assert_error):
    assert_error(
        client.patch(f"{API}/courses/nope", json={"name": "x"}, headers=admin_headers),
        404,
        "COURSE_NOT_FOUND",
    )


# --------------------------- AC27 课程有成绩禁止删除 ---------------------------
def test_ac27_delete_course_with_scores(client, admin_headers, make_student, make_course, make_score, assert_error):
    stu = make_student()
    course = make_course()
    make_score(stu["id"], course["id"], score=70)
    assert_error(
        client.delete(f"{API}/courses/{course['id']}", headers=admin_headers),
        409,
        "COURSE_HAS_SCORES",
    )
    assert client.get(f"{API}/courses/{course['id']}", headers=admin_headers).status_code == 200


def test_delete_course_success_and_invisible(client, admin_headers, make_course, assert_error):
    course = make_course()
    assert client.delete(f"{API}/courses/{course['id']}", headers=admin_headers).status_code == 204
    assert_error(client.get(f"{API}/courses/{course['id']}", headers=admin_headers), 404, "COURSE_NOT_FOUND")
    listed = client.get(f"{API}/courses", headers=admin_headers).json()
    assert all(i["id"] != course["id"] for i in listed["items"])
