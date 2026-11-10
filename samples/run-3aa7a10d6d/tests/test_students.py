"""学生档案管理（F1）：AC1–AC6、AC27（学生侧）。"""
from __future__ import annotations

from conftest import API


# --------------------------- AC1 正常创建 ---------------------------
def test_ac1_create_student_success(client, admin_headers):
    payload = {
        "student_no": "S2024001",
        "name": "李四",
        "class_name": "二班",
        "grade_year": 2024,
    }
    resp = client.post(f"{API}/students", json=payload, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert isinstance(body.get("id"), str) and body["id"], "id 必须为非空字符串"
    assert body["student_no"] == payload["student_no"]
    assert body["name"] == payload["name"]
    assert body["class_name"] == payload["class_name"]
    assert body["grade_year"] == payload["grade_year"]
    # status 未提供时默认 active（§4.1）
    assert body["status"] == "active"
    assert body.get("created_at") and body.get("updated_at")


def test_ac1_create_student_explicit_inactive(client, admin_headers):
    resp = client.post(
        f"{API}/students",
        json={
            "student_no": "S2024002",
            "name": "王五",
            "class_name": "二班",
            "grade_year": 2023,
            "status": "inactive",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "inactive"


# --------------------------- AC2 学号重复 ---------------------------
def test_ac2_duplicated_student_no(client, admin_headers, make_student, assert_error):
    stu = make_student(student_no="S2024100")
    resp = client.post(
        f"{API}/students",
        json={"student_no": "S2024100", "name": "重复", "class_name": "三班", "grade_year": 2024},
        headers=admin_headers,
    )
    assert_error(resp, 409, "STUDENT_NO_DUPLICATED")
    # 原记录未被覆盖
    got = client.get(f"{API}/students/{stu['id']}", headers=admin_headers)
    assert got.status_code == 200
    assert got.json()["name"] == stu["name"]


# --------------------------- AC3 字段校验 ---------------------------
def test_ac3_missing_name(client, admin_headers, assert_error):
    resp = client.post(
        f"{API}/students",
        json={"student_no": "S2024200", "class_name": "一班", "grade_year": 2024},
        headers=admin_headers,
    )
    assert_error(resp, 400, "VALIDATION_ERROR")


def test_ac3_student_no_too_short(client, admin_headers, assert_error):
    resp = client.post(
        f"{API}/students",
        json={"student_no": "S12", "name": "短号", "class_name": "一班", "grade_year": 2024},
        headers=admin_headers,
    )
    assert_error(resp, 400, "VALIDATION_ERROR")


def test_ac3_student_no_non_alnum(client, admin_headers, assert_error):
    resp = client.post(
        f"{API}/students",
        json={"student_no": "S-2024-01", "name": "非法字符", "class_name": "一班", "grade_year": 2024},
        headers=admin_headers,
    )
    assert_error(resp, 400, "VALIDATION_ERROR")


def test_ac3_grade_year_out_of_range(client, admin_headers, assert_error):
    resp = client.post(
        f"{API}/students",
        json={"student_no": "S2024300", "name": "越界", "class_name": "一班", "grade_year": 1800},
        headers=admin_headers,
    )
    assert_error(resp, 400, "VALIDATION_ERROR")


# --------------------------- AC4 查询单个 ---------------------------
def test_ac4_get_student_by_id(client, admin_headers, make_student):
    stu = make_student(name="赵六", class_name="四班", grade_year=2022)
    resp = client.get(f"{API}/students/{stu['id']}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == stu["id"]
    assert body["student_no"] == stu["student_no"]
    assert body["name"] == "赵六"
    assert body["class_name"] == "四班"
    assert body["grade_year"] == 2022


def test_ac4_get_student_not_found(client, admin_headers, assert_error):
    resp = client.get(f"{API}/students/not-exist-id", headers=admin_headers)
    assert_error(resp, 404, "STUDENT_NOT_FOUND")


# --------------------------- AC5 分页 + 班级过滤 ---------------------------
def test_ac5_list_students_filter_by_class(client, admin_headers, make_student):
    for i in range(12):
        make_student(class_name="五班", student_no=f"F5{i:04d}")
    for i in range(3):
        make_student(class_name="六班", student_no=f"F6{i:04d}")

    resp = client.get(
        f"{API}/students",
        params={"class_name": "五班", "page": 1, "page_size": 10},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 12, f"total 应为该类学生总数 12，实际 {body['total']}"
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert len(body["items"]) == 10, "第一页 items 长度应为 10"
    assert all(item["class_name"] == "五班" for item in body["items"])

    page2 = client.get(
        f"{API}/students",
        params={"class_name": "五班", "page": 2, "page_size": 10},
        headers=admin_headers,
    ).json()
    assert len(page2["items"]) == 2, "第二页应剩 2 条"
    ids = {i["id"] for i in body["items"]} | {i["id"] for i in page2["items"]}
    assert len(ids) == 12, "两页合计应覆盖 12 条且无重复"


def test_ac5_list_students_keyword(client, admin_headers, make_student):
    make_student(student_no="KW0001", name="关键词甲")
    make_student(student_no="KW0002", name="关键词乙")
    make_student(student_no="ZZ0003", name="无关")
    resp = client.get(f"{API}/students", params={"keyword": "关键词"}, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {i["name"] for i in body["items"]} == {"关键词甲", "关键词乙"}


# --------------------------- AC6 逻辑删除 ---------------------------
def test_ac6_delete_student_then_invisible(client, admin_headers, make_student, assert_error):
    stu = make_student(class_name="七班")
    resp = client.delete(f"{API}/students/{stu['id']}", headers=admin_headers)
    assert resp.status_code == 204, resp.text
    assert resp.content in (b"", None), "204 不应返回响应体"

    assert_error(client.get(f"{API}/students/{stu['id']}", headers=admin_headers), 404, "STUDENT_NOT_FOUND")

    listed = client.get(f"{API}/students", params={"class_name": "七班"}, headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 0
    assert all(i["id"] != stu["id"] for i in listed.json()["items"])


def test_ac6_delete_student_not_found(client, admin_headers, assert_error):
    assert_error(client.delete(f"{API}/students/nope", headers=admin_headers), 404, "STUDENT_NOT_FOUND")


# --------------------------- AC27 有成绩禁止删除 ---------------------------
def test_ac27_delete_student_with_scores(client, admin_headers, make_student, make_course, make_score, assert_error):
    stu = make_student()
    course = make_course()
    make_score(stu["id"], course["id"], score=88)

    body = assert_error(
        client.delete(f"{API}/students/{stu['id']}", headers=admin_headers),
        409,
        "STUDENT_HAS_SCORES",
    )
    assert body["details"] is None or isinstance(body["details"], dict)
    # 学生仍存在
    assert client.get(f"{API}/students/{stu['id']}", headers=admin_headers).status_code == 200


def test_ac27_delete_student_after_score_deleted(client, admin_headers, make_student, make_course, make_score):
    """成绩逻辑删除后，学生应可删除（AC27 只约束未删除成绩）。"""
    stu = make_student()
    course = make_course()
    score = make_score(stu["id"], course["id"])
    assert client.delete(f"{API}/scores/{score['id']}", headers=admin_headers).status_code == 204
    resp = client.delete(f"{API}/students/{stu['id']}", headers=admin_headers)
    assert resp.status_code == 204, resp.text


# --------------------------- PATCH 学生（§4.1） ---------------------------
def test_patch_student_updates_fields(client, admin_headers, make_student):
    stu = make_student(name="旧名", class_name="八班")
    resp = client.patch(
        f"{API}/students/{stu['id']}",
        json={"name": "新名", "class_name": "九班", "status": "inactive"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "新名"
    assert body["class_name"] == "九班"
    assert body["status"] == "inactive"
    assert body["student_no"] == stu["student_no"], "student_no 不可修改"


def test_patch_student_empty_body_rejected(client, admin_headers, make_student, assert_error):
    stu = make_student()
    assert_error(
        client.patch(f"{API}/students/{stu['id']}", json={}, headers=admin_headers),
        400,
        "VALIDATION_ERROR",
    )


def test_patch_student_no_immutable(client, admin_headers, make_student, assert_error):
    stu = make_student()
    assert_error(
        client.patch(f"{API}/students/{stu['id']}", json={"student_no": "NEW0001"}, headers=admin_headers),
        400,
        "VALIDATION_ERROR",
    )


def test_patch_student_not_found(client, admin_headers, assert_error):
    assert_error(
        client.patch(f"{API}/students/nope", json={"name": "x"}, headers=admin_headers),
        404,
        "STUDENT_NOT_FOUND",
    )
