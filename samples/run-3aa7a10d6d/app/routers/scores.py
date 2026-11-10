"""成绩管理路由（F3）：AC9–AC19。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AppError, ErrorCode
from app.repositories import score_repo
from app.routers.deps import Pagination, pagination
from app.schemas import (
    Page,
    ScoreCreate,
    ScoreHistoryItem,
    ScoreHistoryList,
    ScoreListItem,
    ScoreOut,
    ScoreUpdate,
    ScoreUpdateOut,
)
from app.security import Principal, ensure_student_self, get_principal, require_staff
from app.services import score_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scores", tags=["scores"])


@router.post("", response_model=ScoreOut, status_code=status.HTTP_201_CREATED)
def create_score(
    payload: ScoreCreate,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> ScoreOut:
    """录入成绩（AC9–AC13）。"""
    record = score_service.create_score(
        db,
        student_id=payload.student_id,
        course_id=payload.course_id,
        semester=payload.semester,
        score=payload.score,
        operator_id=payload.operator_id,
    )
    db.commit()
    db.refresh(record)
    return ScoreOut.model_validate(record)


@router.get("", response_model=Page[ScoreListItem])
def list_scores(
    student_id: Optional[str] = Query(default=None, max_length=36),
    course_id: Optional[str] = Query(default=None, max_length=36),
    semester: Optional[str] = Query(default=None, max_length=7),
    class_name: Optional[str] = Query(default=None, max_length=50),
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Page[ScoreListItem]:
    """组合条件分页查询成绩（AC14–AC16）；学生仅可查本人。"""
    if principal.is_student:
        if principal.student_id is None:
            raise AppError(ErrorCode.FORBIDDEN, message="学生凭证未绑定 student_id")
        if student_id is not None:
            ensure_student_self(principal, student_id)
        student_id = principal.student_id

    rows, total = score_repo.list_scores(
        db,
        student_id=student_id,
        course_id=course_id,
        semester=semester,
        class_name=class_name,
        page=page.page,
        page_size=page.page_size,
    )
    items = [
        ScoreListItem(
            id=score.id,
            student_id=score.student_id,
            student_no=student.student_no,
            student_name=student.name,
            course_id=score.course_id,
            course_code=course.course_code,
            course_name=course.name,
            semester=score.semester,
            score=float(score.score),
            updated_at=score.updated_at,
        )
        for score, student, course in rows
    ]
    return Page[ScoreListItem](
        items=items, total=total, page=page.page, page_size=page.page_size
    )


@router.get("/{score_id}", response_model=ScoreOut)
def get_score(
    score_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> ScoreOut:
    """按 ID 查询成绩；学生仅可查本人。"""
    record = score_repo.get_active(db, score_id)
    if record is None:
        raise AppError(ErrorCode.SCORE_NOT_FOUND, details={"score_id": score_id})
    if principal.is_student:
        ensure_student_self(principal, record.student_id)
    return ScoreOut.model_validate(record)


@router.patch("/{score_id}", response_model=ScoreUpdateOut)
def update_score(
    score_id: str,
    payload: ScoreUpdate,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> ScoreUpdateOut:
    """更正成绩并记录变更历史（AC17）。"""
    record, previous = score_service.update_score(
        db,
        score_id=score_id,
        new_score=payload.score,
        operator_id=payload.operator_id,
        reason=payload.reason,
    )
    db.commit()
    db.refresh(record)
    out = ScoreUpdateOut.model_validate(record)
    out.previous_score = previous
    return out


@router.delete("/{score_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_score(
    score_id: str,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> Response:
    """逻辑删除成绩（AC19）。"""
    score_service.delete_score(db, score_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{score_id}/histories", response_model=ScoreHistoryList)
def list_score_histories(
    score_id: str,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> ScoreHistoryList:
    """查询成绩变更历史（AC18）。"""
    record = score_repo.get_active(db, score_id)
    if record is None:
        raise AppError(ErrorCode.SCORE_NOT_FOUND, details={"score_id": score_id})
    histories = score_repo.list_histories(db, score_id)
    return ScoreHistoryList(
        items=[
            ScoreHistoryItem(
                changed_at=item.changed_at,
                operator_id=item.operator_id,
                previous_score=float(item.previous_score),
                new_score=float(item.new_score),
                reason=item.reason,
            )
            for item in histories
        ]
    )
