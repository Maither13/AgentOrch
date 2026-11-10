"""学生档案管理路由（F1）：AC1–AC6、AC27。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AppError, ErrorCode
from app.models import Student
from app.repositories import student_repo
from app.routers.deps import Pagination, pagination
from app.schemas import Page, StudentCreate, StudentOut, StudentUpdate
from app.security import Principal, require_admin, require_staff

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/students", tags=["students"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_out(student: Student) -> StudentOut:
    return StudentOut.model_validate(student)


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> StudentOut:
    """创建学生（AC1）；学号重复返回 409（AC2）。"""
    if student_repo.get_by_student_no(db, payload.student_no) is not None:
        raise AppError(
            ErrorCode.STUDENT_NO_DUPLICATED,
            details={"student_no": payload.student_no},
        )

    now = _utc_now()
    student = Student(
        id=str(uuid.uuid4()),
        student_no=payload.student_no,
        name=payload.name,
        class_name=payload.class_name,
        grade_year=payload.grade_year,
        status=payload.status,
        is_deleted=0,
        created_at=now,
        updated_at=now,
    )
    try:
        student_repo.insert(db, student)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("创建学生唯一约束冲突: %s", exc)
        raise AppError(
            ErrorCode.STUDENT_NO_DUPLICATED,
            details={"student_no": payload.student_no},
        ) from exc
    db.refresh(student)
    return _to_out(student)


@router.get("", response_model=Page[StudentOut])
def list_students(
    class_name: Optional[str] = Query(default=None, max_length=50),
    grade_year: Optional[int] = Query(default=None, ge=1900, le=2100),
    status_filter: Optional[str] = Query(default=None, alias="status", pattern="^(active|inactive)$"),
    keyword: Optional[str] = Query(default=None, max_length=50),
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> Page[StudentOut]:
    """分页查询学生，支持班级/年级/状态/关键字过滤（AC5）。"""
    items, total = student_repo.list_students(
        db,
        class_name=class_name,
        grade_year=grade_year,
        status=status_filter,
        keyword=keyword,
        page=page.page,
        page_size=page.page_size,
    )
    return Page[StudentOut](
        items=[_to_out(item) for item in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/{student_id}", response_model=StudentOut)
def get_student(
    student_id: str,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> StudentOut:
    """按 ID 查询学生（AC4）。"""
    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})
    return _to_out(student)


@router.patch("/{student_id}", response_model=StudentOut)
def update_student(
    student_id: str,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> StudentOut:
    """局部更新学生；空请求体视为校验失败，student_no 不可修改。"""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            message="请求体不能为空，至少提供一个可更新字段",
            details={"field": "body", "reason": "empty_patch"},
        )

    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})

    for field_name, value in changes.items():
        if value is None:
            continue
        setattr(student, field_name, value)
    student.updated_at = _utc_now()
    db.commit()
    db.refresh(student)
    return _to_out(student)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(
    student_id: str,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_admin),
) -> Response:
    """逻辑删除学生（AC6）；存在未删除成绩时拒绝（AC27）。"""
    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})

    active_scores = student_repo.count_active_scores(db, student_id)
    if active_scores > 0:
        raise AppError(
            ErrorCode.STUDENT_HAS_SCORES,
            details={"student_id": student_id, "active_score_count": active_scores},
        )

    student_repo.soft_delete(db, student, _utc_now())
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
