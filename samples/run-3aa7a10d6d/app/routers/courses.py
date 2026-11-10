"""课程管理路由（F2）：AC7–AC8、AC27。"""

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
from app.models import Course
from app.repositories import course_repo
from app.routers.deps import Pagination, pagination
from app.schemas import CourseCreate, CourseOut, CourseUpdate, Page
from app.security import Principal, require_admin, require_staff

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["courses"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_out(course: Course) -> CourseOut:
    return CourseOut.model_validate(course)


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> CourseOut:
    """创建课程（AC7）；编号重复返回 409（AC8）。"""
    if course_repo.get_by_course_code(db, payload.course_code) is not None:
        raise AppError(
            ErrorCode.COURSE_CODE_DUPLICATED,
            details={"course_code": payload.course_code},
        )

    now = _utc_now()
    course = Course(
        id=str(uuid.uuid4()),
        course_code=payload.course_code,
        name=payload.name,
        credit=payload.credit,
        full_score=payload.full_score,
        is_deleted=0,
        created_at=now,
        updated_at=now,
    )
    try:
        course_repo.insert(db, course)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("创建课程唯一约束冲突: %s", exc)
        raise AppError(
            ErrorCode.COURSE_CODE_DUPLICATED,
            details={"course_code": payload.course_code},
        ) from exc
    db.refresh(course)
    return _to_out(course)


@router.get("", response_model=Page[CourseOut])
def list_courses(
    keyword: Optional[str] = Query(default=None, max_length=50),
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> Page[CourseOut]:
    """分页查询课程，支持编号/名称关键字。"""
    items, total = course_repo.list_courses(
        db, keyword=keyword, page=page.page, page_size=page.page_size
    )
    return Page[CourseOut](
        items=[_to_out(item) for item in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/{course_id}", response_model=CourseOut)
def get_course(
    course_id: str,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> CourseOut:
    """按 ID 查询课程。"""
    course = course_repo.get_active(db, course_id)
    if course is None:
        raise AppError(ErrorCode.COURSE_NOT_FOUND, details={"course_id": course_id})
    return _to_out(course)


@router.patch("/{course_id}", response_model=CourseOut)
def update_course(
    course_id: str,
    payload: CourseUpdate,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> CourseOut:
    """局部更新课程；course_code 不可修改。"""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            message="请求体不能为空，至少提供一个可更新字段",
            details={"field": "body", "reason": "empty_patch"},
        )

    course = course_repo.get_active(db, course_id)
    if course is None:
        raise AppError(ErrorCode.COURSE_NOT_FOUND, details={"course_id": course_id})

    for field_name, value in changes.items():
        if value is None:
            continue
        setattr(course, field_name, value)
    course.updated_at = _utc_now()
    db.commit()
    db.refresh(course)
    return _to_out(course)


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: str,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_admin),
) -> Response:
    """逻辑删除课程；存在未删除成绩时拒绝（AC27）。"""
    course = course_repo.get_active(db, course_id)
    if course is None:
        raise AppError(ErrorCode.COURSE_NOT_FOUND, details={"course_id": course_id})

    active_scores = course_repo.count_active_scores(db, course_id)
    if active_scores > 0:
        raise AppError(
            ErrorCode.COURSE_HAS_SCORES,
            details={"course_id": course_id, "active_score_count": active_scores},
        )

    course_repo.soft_delete(db, course, _utc_now())
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
