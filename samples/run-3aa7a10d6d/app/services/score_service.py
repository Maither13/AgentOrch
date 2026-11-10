"""成绩业务逻辑：录入、更正、删除、批量导入（供路由层复用）。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError, ErrorCode
from app.models import Course, Score, ScoreHistory, Student
from app.repositories import course_repo, score_repo, student_repo

logger = logging.getLogger(__name__)

MAX_DECIMAL_PLACES = 1


def utc_now() -> str:
    """ISO 8601 UTC 时间字符串。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid.uuid4())


def validate_score_value(score: float, full_score: float) -> None:
    """0 ≤ score ≤ full_score，且最多 1 位小数（AC11）。"""
    if score < 0 or score > full_score:
        raise AppError(
            ErrorCode.SCORE_OUT_OF_RANGE,
            message=f"成绩必须在 0 至 {full_score} 之间",
            details={"score": score, "full_score": full_score},
        )
    if round(score, MAX_DECIMAL_PLACES) != score:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            message="score 最多保留 1 位小数",
            details={"field": "score", "reason": "最多 1 位小数"},
        )


def resolve_student(db: Session, student_id: str) -> Student:
    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})
    return student


def resolve_course(db: Session, course_id: str) -> Course:
    course = course_repo.get_active(db, course_id)
    if course is None:
        raise AppError(ErrorCode.COURSE_NOT_FOUND, details={"course_id": course_id})
    return course


def create_score(
    db: Session,
    student_id: str,
    course_id: str,
    semester: str,
    score: float,
    operator_id: str,
) -> Score:
    """录入成绩（AC9–AC13）。"""
    resolve_student(db, student_id)
    course = resolve_course(db, course_id)
    validate_score_value(score, course.full_score)

    existing = score_repo.get_active_triplet(db, student_id, course_id, semester)
    if existing is not None:
        raise AppError(
            ErrorCode.SCORE_DUPLICATED,
            details={"student_id": student_id, "course_id": course_id, "semester": semester},
        )

    now = utc_now()
    record = Score(
        id=new_id(),
        student_id=student_id,
        course_id=course_id,
        semester=semester,
        score=score,
        operator_id=operator_id,
        is_deleted=0,
        created_at=now,
        updated_at=now,
    )
    try:
        score_repo.insert(db, record)
    except IntegrityError as exc:
        db.rollback()
        logger.warning("成绩唯一索引冲突: %s", exc)
        raise AppError(
            ErrorCode.SCORE_DUPLICATED,
            details={"student_id": student_id, "course_id": course_id, "semester": semester},
        ) from exc
    return record


def update_score(
    db: Session,
    score_id: str,
    new_score: float,
    operator_id: str,
    reason: Optional[str],
) -> Tuple[Score, float]:
    """更正成绩并写入变更历史（AC17/AC18）。"""
    record = score_repo.get_active(db, score_id)
    if record is None:
        raise AppError(ErrorCode.SCORE_NOT_FOUND, details={"score_id": score_id})
    course = resolve_course(db, record.course_id)
    validate_score_value(new_score, course.full_score)

    previous = float(record.score)
    now = utc_now()
    record.score = new_score
    record.operator_id = operator_id
    record.updated_at = now
    score_repo.add_history(
        db,
        ScoreHistory(
            id=new_id(),
            score_id=record.id,
            previous_score=previous,
            new_score=new_score,
            operator_id=operator_id,
            reason=reason,
            changed_at=now,
        ),
    )
    db.flush()
    return record, previous


def delete_score(db: Session, score_id: str) -> None:
    """逻辑删除成绩（AC19）。"""
    record = score_repo.get_active(db, score_id)
    if record is None:
        raise AppError(ErrorCode.SCORE_NOT_FOUND, details={"score_id": score_id})
    score_repo.soft_delete(db, record, utc_now())


def batch_create(
    db: Session, records: List[dict], operator_id: str
) -> Tuple[int, int, List[dict]]:
    """批量录入：逐条独立校验，单条失败不影响其他条（AC24/AC25）。"""
    results: List[dict] = []
    succeeded = 0
    failed = 0
    for index, item in enumerate(records):
        try:
            record = create_score(
                db,
                student_id=item["student_id"],
                course_id=item["course_id"],
                semester=item["semester"],
                score=float(item["score"]),
                operator_id=operator_id,
            )
            db.commit()
        except AppError as exc:
            db.rollback()
            failed += 1
            results.append(
                {
                    "index": index,
                    "status": "failed",
                    "score_id": None,
                    "error_code": exc.code.value,
                }
            )
            logger.info("批量导入第 %d 条失败: %s", index, exc.code.value)
            continue
        except IntegrityError as exc:
            db.rollback()
            failed += 1
            results.append(
                {
                    "index": index,
                    "status": "failed",
                    "score_id": None,
                    "error_code": ErrorCode.SCORE_DUPLICATED.value,
                }
            )
            logger.warning("批量导入第 %d 条唯一冲突: %s", index, exc)
            continue
        succeeded += 1
        results.append(
            {"index": index, "status": "success", "score_id": record.id, "error_code": None}
        )
    return succeeded, failed, results


def pass_line_for(full_score: float) -> float:
    """及格线 = 满分 × 配置比例（需求 §7 待确认项 1 的默认口径）。"""
    return round(full_score * settings.pass_line_ratio, 2)
