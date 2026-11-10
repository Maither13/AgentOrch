"""课程数据访问。"""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Course, Score


def get_active(db: Session, course_id: str) -> Optional[Course]:
    stmt = select(Course).where(Course.id == course_id, Course.is_deleted == 0)
    return db.execute(stmt).scalar_one_or_none()


def get_by_course_code(db: Session, course_code: str) -> Optional[Course]:
    """课程编号全局唯一（含已删除记录，裁决 C8）。"""
    stmt = select(Course).where(Course.course_code == course_code)
    return db.execute(stmt).scalar_one_or_none()


def list_courses(
    db: Session, keyword: Optional[str], page: int, page_size: int
) -> Tuple[List[Course], int]:
    conditions = [Course.is_deleted == 0]
    if keyword:
        like = f"%{keyword}%"
        conditions.append(or_(Course.course_code.like(like), Course.name.like(like)))

    total = db.execute(select(func.count()).select_from(Course).where(*conditions)).scalar_one()
    stmt = (
        select(Course)
        .where(*conditions)
        .order_by(Course.created_at.asc(), Course.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.execute(stmt).scalars().all())
    return items, int(total)


def insert(db: Session, course: Course) -> Course:
    db.add(course)
    db.flush()
    return course


def soft_delete(db: Session, course: Course, now: str) -> None:
    """逻辑删除课程。"""
    course.is_deleted = 1
    course.updated_at = now
    db.flush()


def count_active_scores(db: Session, course_id: str) -> int:
    """该课程未删除成绩条数（AC27）。"""
    stmt = select(func.count()).select_from(Score).where(
        Score.course_id == course_id, Score.is_deleted == 0
    )
    return int(db.execute(stmt).scalar_one())
