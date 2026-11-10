"""成绩数据访问（含变更历史与统计聚合）。"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Course, Score, ScoreHistory, Student

logger = logging.getLogger(__name__)


def get_active(db: Session, score_id: str) -> Optional[Score]:
    stmt = select(Score).where(Score.id == score_id, Score.is_deleted == 0)
    return db.execute(stmt).scalar_one_or_none()


def get_active_triplet(
    db: Session, student_id: str, course_id: str, semester: str
) -> Optional[Score]:
    """未删除记录中 (student_id, course_id, semester) 唯一（AC10）。"""
    stmt = select(Score).where(
        Score.student_id == student_id,
        Score.course_id == course_id,
        Score.semester == semester,
        Score.is_deleted == 0,
    )
    return db.execute(stmt).scalar_one_or_none()


def insert(db: Session, score: Score) -> Score:
    db.add(score)
    db.flush()
    return score


def soft_delete(db: Session, score: Score, now: str) -> None:
    score.is_deleted = 1
    score.updated_at = now
    db.flush()


def add_history(db: Session, history: ScoreHistory) -> ScoreHistory:
    db.add(history)
    db.flush()
    return history


def list_histories(db: Session, score_id: str) -> List[ScoreHistory]:
    stmt = (
        select(ScoreHistory)
        .where(ScoreHistory.score_id == score_id)
        .order_by(ScoreHistory.changed_at.asc(), ScoreHistory.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def list_scores(
    db: Session,
    student_id: Optional[str],
    course_id: Optional[str],
    semester: Optional[str],
    class_name: Optional[str],
    page: int,
    page_size: int,
) -> Tuple[List[Tuple[Score, Student, Course]], int]:
    """组合条件分页查询，返回 (Score, Student, Course) 三元组（AC14/AC15/AC16）。"""
    conditions = [Score.is_deleted == 0, Student.is_deleted == 0, Course.is_deleted == 0]
    if student_id is not None:
        conditions.append(Score.student_id == student_id)
    if course_id is not None:
        conditions.append(Score.course_id == course_id)
    if semester is not None:
        conditions.append(Score.semester == semester)
    if class_name is not None:
        conditions.append(Student.class_name == class_name)

    base = (
        select(Score, Student, Course)
        .join(Student, Student.id == Score.student_id)
        .join(Course, Course.id == Score.course_id)
        .where(*conditions)
    )
    count_stmt = (
        select(func.count())
        .select_from(Score)
        .join(Student, Student.id == Score.student_id)
        .join(Course, Course.id == Score.course_id)
        .where(*conditions)
    )
    total = int(db.execute(count_stmt).scalar_one())
    stmt = (
        base.order_by(Score.created_at.asc(), Score.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = [(row[0], row[1], row[2]) for row in db.execute(stmt).all()]
    return rows, total


def aggregate_by_course(
    db: Session, course_id: str, semester: Optional[str], pass_line: float
) -> Tuple[int, Optional[float], Optional[float], Optional[float], Optional[int]]:
    """课程维度聚合：count / avg / max / min / 及格数（AC20/AC21）。

    注意：SQLAlchemy 2.0 必须使用 sqlalchemy.case，func.case 会生成非法 SQL。
    """
    conditions = [Score.course_id == course_id, Score.is_deleted == 0]
    if semester is not None:
        conditions.append(Score.semester == semester)

    pass_flag = case((Score.score >= pass_line, 1), else_=0)
    stmt = select(
        func.count(Score.id),
        func.avg(Score.score),
        func.max(Score.score),
        func.min(Score.score),
        func.sum(pass_flag),
    ).where(*conditions)
    row = db.execute(stmt).one()
    count = int(row[0] or 0)
    if count == 0:
        return 0, None, None, None, None
    average = float(row[1]) if row[1] is not None else None
    maximum = float(row[2]) if row[2] is not None else None
    minimum = float(row[3]) if row[3] is not None else None
    passed = int(row[4] or 0)
    return count, average, maximum, minimum, passed


def aggregate_by_class(
    db: Session, class_name: str, semester: str, pass_line: float
) -> Tuple[int, Optional[float], Optional[int]]:
    """班级维度聚合：去重学生数 / 平均分 / 及格数（AC22）。

    口径：该班在该学期有未删除成绩记录的去重学生数。
    """
    conditions = [
        Score.is_deleted == 0,
        Score.semester == semester,
        Student.is_deleted == 0,
        Student.class_name == class_name,
    ]
    pass_flag = case((Score.score >= pass_line, 1), else_=0)
    stmt = (
        select(
            func.count(func.distinct(Score.student_id)),
            func.avg(Score.score),
            func.sum(pass_flag),
        )
        .select_from(Score)
        .join(Student, Student.id == Score.student_id)
        .where(*conditions)
    )
    row = db.execute(stmt).one()
    student_count = int(row[0] or 0)
    if student_count == 0:
        return 0, None, None
    average = float(row[1]) if row[1] is not None else None
    passed = int(row[2] or 0)
    return student_count, average, passed


def list_transcript(
    db: Session, student_id: str, semester: str
) -> List[Tuple[Score, Course]]:
    """学生某学期未删除成绩 + 课程信息（AC23）。"""
    stmt = (
        select(Score, Course)
        .join(Course, Course.id == Score.course_id)
        .where(
            Score.student_id == student_id,
            Score.semester == semester,
            Score.is_deleted == 0,
            Course.is_deleted == 0,
        )
        .order_by(Course.course_code.asc(), Score.id.asc())
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]
