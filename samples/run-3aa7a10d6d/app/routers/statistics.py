"""统计与成绩单路由（F4）：AC20–AC23。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AppError, ErrorCode
from app.repositories import score_repo, student_repo
from app.schemas import ClassStatistics, CourseStatistics, Transcript, TranscriptItem
from app.security import Principal, ensure_student_self, get_principal, require_staff
from app.services import score_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("/courses/{course_id}", response_model=CourseStatistics)
def course_statistics(
    course_id: str,
    semester: Optional[str] = Query(default=None, max_length=7),
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> CourseStatistics:
    """课程维度统计：count/avg/max/min/及格率（AC20/AC21）。"""
    course = score_service.resolve_course(db, course_id)
    pass_line = score_service.pass_line_for(course.full_score)
    count, average, maximum, minimum, passed = score_repo.aggregate_by_course(
        db, course_id=course_id, semester=semester, pass_line=pass_line
    )
    if count == 0:
        return CourseStatistics(
            course_id=course_id,
            semester=semester,
            count=0,
            average=None,
            max=None,
            min=None,
            pass_rate=None,
            pass_line=pass_line,
        )
    pass_rate = round((passed or 0) / count, 4)
    return CourseStatistics(
        course_id=course_id,
        semester=semester,
        count=count,
        average=round(average, 2) if average is not None else None,
        max=maximum,
        min=minimum,
        pass_rate=pass_rate,
        pass_line=pass_line,
    )


@router.get("/classes/{class_name}", response_model=ClassStatistics)
def class_statistics(
    class_name: str,
    semester: str = Query(..., max_length=7),
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> ClassStatistics:
    """班级维度统计：去重学生数/平均分/及格率（AC22）。"""
    student_count, average, passed = score_repo.aggregate_by_class(
        db,
        class_name=class_name,
        semester=semester,
        pass_line=score_service.pass_line_for(100.0),
    )
    if student_count == 0:
        return ClassStatistics(
            class_name=class_name,
            semester=semester,
            student_count=0,
            average=None,
            pass_rate=None,
        )
    pass_rate = round((passed or 0) / student_count, 4)
    return ClassStatistics(
        class_name=class_name,
        semester=semester,
        student_count=student_count,
        average=round(average, 2) if average is not None else None,
        pass_rate=pass_rate,
    )


@router.get("/transcript/{student_id}", response_model=Transcript)
def transcript(
    student_id: str,
    semester: str = Query(..., max_length=7),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Transcript:
    """学生学期成绩单（AC23）；学生仅可查本人。"""
    ensure_student_self(principal, student_id)
    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})

    rows = score_repo.list_transcript(db, student_id=student_id, semester=semester)
    items = [
        TranscriptItem(
            course_id=course.id,
            course_code=course.course_code,
            course_name=course.name,
            credit=float(course.credit),
            score=float(score.score),
            full_score=float(course.full_score),
        )
        for score, course in rows
    ]
    total_credit = round(sum(item.credit for item in items), 2)
    average = round(sum(item.score for item in items) / len(items), 2) if items else None
    return Transcript(
        student_id=student.id,
        student_no=student.student_no,
        student_name=student.name,
        semester=semester,
        items=items,
        average=average,
        total_credit=total_credit,
    )
