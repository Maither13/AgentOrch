"""学生数据访问。"""

from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Score, Student


def get_active(db: Session, student_id: str) -> Optional[Student]:
    stmt = select(Student).where(Student.id == student_id, Student.is_deleted == 0)
    return db.execute(stmt).scalar_one_or_none()


def get_by_student_no(db: Session, student_no: str) -> Optional[Student]:
    """学号全局唯一（含已删除记录，裁决 C8）。"""
    stmt = select(Student).where(Student.student_no == student_no)
    return db.execute(stmt).scalar_one_or_none()


def list_students(
    db: Session,
    class_name: Optional[str],
    grade_year: Optional[int],
    status: Optional[str],
    keyword: Optional[str],
    page: int,
    page_size: int,
) -> Tuple[List[Student], int]:
    conditions = [Student.is_deleted == 0]
    if class_name is not None:
        conditions.append(Student.class_name == class_name)
    if grade_year is not None:
        conditions.append(Student.grade_year == grade_year)
    if status is not None:
        conditions.append(Student.status == status)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(or_(Student.student_no.like(like), Student.name.like(like)))

    total = db.execute(select(func.count()).select_from(Student).where(*conditions)).scalar_one()
    stmt = (
        select(Student)
        .where(*conditions)
        .order_by(Student.created_at.asc(), Student.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.execute(stmt).scalars().all())
    return items, int(total)


def insert(db: Session, student: Student) -> Student:
    db.add(student)
    db.flush()
    return student


def soft_delete(db: Session, student: Student, now: str) -> None:
    """逻辑删除学生（AC6）。"""
    student.is_deleted = 1
    student.updated_at = now
    db.flush()


def count_active_scores(db: Session, student_id: str) -> int:
    """该学生未删除成绩条数（AC27）。"""
    stmt = select(func.count()).select_from(Score).where(
        Score.student_id == student_id, Score.is_deleted == 0
    )
    return int(db.execute(stmt).scalar_one())


def count_active_by_class(db: Session, class_name: str) -> int:
    stmt = select(func.count()).select_from(Student).where(
        Student.class_name == class_name, Student.is_deleted == 0
    )
    return int(db.execute(stmt).scalar_one())
