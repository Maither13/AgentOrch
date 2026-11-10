## 根因

评审驳回的根因是**交付物缺失**，并非逻辑错误：

1. **B1 应用入口与路由层完全缺失**：工作区只有横切模块（config/db/errors/models/schemas）和 student/course 两个仓储，没有 `app/main.py`，也没有任何路由模块。`tests/conftest.py:47-50` 的 `_require_app` 因 `from app.main import app` 失败而 skip 全部 33 个用例，所以 `pytest` 退出码为 0 但零断言执行。
2. **B2 `app/repositories/score_repo.py` 未落盘**：S3 文本被截断，成绩仓储从未写入磁盘，AC9–AC25 全部无依赖。
3. **B3 `app/models.py:88-95` 的 `ux_scores_active_triplet` 传 `sqlite_where=None`**：退化为全量唯一索引，逻辑删除后重新录入同一 `(student_id, course_id, semester)` 会被索引拒绝，违反需求 §5.3「在未删除记录中唯一」。
4. **B4 `aggregate_by_course` 使用 `func.case(...)`**：SQLAlchemy 2.0 中 `func.case` 生成非法 SQL，统计接口必然 500。
5. **B6 鉴权无实现**：`tests/conftest.py:36-39` 的 4 个 token 无消费方，AC26 无法通过。
6. **B5 测试资产缺失**：`test_scores.py`、`test_statistics.py`、`test_batch.py`、`test_auth_pagination.py` 未落盘。

## 修复内容（全部 file_write 落盘）

```python path=app/models.py
"""ORM 映射（与 sql/schema.sql 保持一致）。"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Real,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_no: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    class_name: Mapped[str] = mapped_column(String(50), nullable=False)
    grade_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active','inactive')", name="ck_students_status"),
        CheckConstraint("is_deleted IN (0,1)", name="ck_students_is_deleted"),
        CheckConstraint("grade_year BETWEEN 1900 AND 2100", name="ck_students_grade_year"),
        CheckConstraint("length(student_no) BETWEEN 4 AND 20", name="ck_students_no_len"),
        Index("ux_students_student_no", "student_no", unique=True),
        Index("ix_students_class_status", "class_name", "status", "is_deleted"),
        Index("ix_students_grade_year", "grade_year", "is_deleted"),
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    credit: Mapped[float] = mapped_column(Real, nullable=False)
    full_score: Mapped[float] = mapped_column(Real, nullable=False, default=100.0)
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint("is_deleted IN (0,1)", name="ck_courses_is_deleted"),
        CheckConstraint("credit >= 0.5 AND credit <= 10", name="ck_courses_credit"),
        CheckConstraint("full_score >= 1 AND full_score <= 1000", name="ck_courses_full_score"),
        Index("ux_courses_course_code", "course_code", unique=True),
        Index("ix_courses_is_deleted", "is_deleted"),
    )


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(36), ForeignKey("courses.id"), nullable=False)
    semester: Mapped[str] = mapped_column(String(7), nullable=False)
    score: Mapped[float] = mapped_column(Real, nullable=False)
    operator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint("is_deleted IN (0,1)", name="ck_scores_is_deleted"),
        CheckConstraint("score >= 0", name="ck_scores_score"),
        CheckConstraint("length(operator_id) BETWEEN 1 AND 64", name="ck_scores_operator"),
        # 部分唯一索引：仅在未删除记录中唯一（需求 §5.3 / 裁决 C7）
        Index(
            "ux_scores_active_triplet",
            "student_id",
            "course_id",
            "semester",
            unique=True,
            sqlite_where=text("is_deleted = 0"),
            postgresql_where=text("is_deleted = 0"),
        ),
        Index("ix_scores_student_semester", "student_id", "semester", "is_deleted"),
        Index("ix_scores_course_semester", "course_id", "semester", "is_deleted"),
        Index("ix_scores_active", "is_deleted"),
    )


class ScoreHistory(Base):
    __tablename__ = "score_histories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    score_id: Mapped[str] = mapped_column(String(36), ForeignKey("scores.id"), nullable=False)
    previous_score: Mapped[float] = mapped_column(Real, nullable=False)
    new_score: Mapped[float] = mapped_column(Real, nullable=False)
    operator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint("reason IS NULL OR length(reason) <= 200", name="ck_hist_reason_len"),
        Index("ix_histories_score_changed", "score_id", "changed_at"),
    )
```

```python path=app/repositories/student_repo.py
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
```

```python path=app/repositories/course_repo.py
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
```

```python path=app/repositories/score_repo.py
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
```

```python path=app/security.py
"""鉴权依赖：静态 Bearer Token + 角色判定（F12 / AC26）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header

from app.config import settings
from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    token: str
    role: str
    student_id: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_teacher(self) -> bool:
        return self.role == "teacher"

    @property
    def is_student(self) -> bool:
        return self.role == "student"


def get_principal(authorization: Optional[str] = Header(default=None)) -> Principal:
    """解析 Authorization: Bearer <token>，无效则 401 UNAUTHORIZED。"""
    if not authorization:
        raise AppError(ErrorCode.UNAUTHORIZED, message="缺少 Authorization 请求头")
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AppError(ErrorCode.UNAUTHORIZED, message="Authorization 必须为 Bearer 方案")
    token = parts[1].strip()
    if not token:
        raise AppError(ErrorCode.UNAUTHORIZED, message="Bearer Token 为空")
    payload = settings.auth_tokens.get(token)
    if payload is None:
        logger.warning("收到未知 token 的请求")
        raise AppError(ErrorCode.UNAUTHORIZED, message="凭证无效")
    return Principal(token=token, role=str(payload["role"]), student_id=payload.get("student_id"))


def require_roles(*roles: str):
    """角色白名单依赖工厂。"""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise AppError(
                ErrorCode.FORBIDDEN,
                message=f"角色 {principal.role} 无权访问该资源",
                details={"required_roles": list(roles)},
            )
        return principal

    return _dep


require_admin = require_roles("admin")
require_staff = require_roles("admin", "teacher")


def ensure_student_self(principal: Principal, student_id: str) -> None:
    """学生角色只能访问本人数据（AC26）。"""
    if principal.is_student and principal.student_id != student_id:
        raise AppError(
            ErrorCode.FORBIDDEN,
            message="学生只能查询本人成绩",
            details={"student_id": student_id},
        )
```

```python path=app/services/__init__.py
"""业务服务层。"""
```

```python path=app/services/score_service.py
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
```

```python path=app/routers/__init__.py
"""HTTP 路由层。"""
```

```python path=app/routers/deps.py
"""路由层公共依赖：分页参数校验（AC28）。"""

from __future__ import annotations

from fastapi import Query

from app.errors import validation_error

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class Pagination:
    """分页参数容器，构造时完成范围校验。"""

    __slots__ = ("page", "page_size")

    def __init__(self, page: int, page_size: int) -> None:
        if page < 1:
            raise validation_error("page", "必须 >= 1")
        if page_size < 1 or page_size > MAX_PAGE_SIZE:
            raise validation_error("page_size", f"必须在 1 至 {MAX_PAGE_SIZE} 之间")
        self.page = page
        self.page_size = page_size


def pagination(
    page: int = Query(default=1, description="页码，最小 1"),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, description="每页条数，1-100"),
) -> Pagination:
    return Pagination(page=page, page_size=page_size)
```

```python path=app/routers/students.py
"""学生档案路由（F1 / AC1–AC6、AC23、AC27）。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db, write_transaction
from app.errors import AppError, ErrorCode, validation_error
from app.models import Student
from app.repositories import student_repo
from app.routers.deps import Pagination, pagination
from app.schemas import Page, StudentCreate, StudentOut, StudentUpdate, Transcript
from app.security import Principal, ensure_student_self, get_principal, require_admin, require_staff
from app.services import score_service
from app.services.score_service import new_id, utc_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/students", tags=["students"])


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
) -> StudentOut:
    """创建学生（AC1/AC2/AC3）。"""
    if student_repo.get_by_student_no(db, payload.student_no) is not None:
        raise AppError(
            ErrorCode.STUDENT_NO_DUPLICATED, details={"student_no": payload.student_no}
        )
    now = utc_now()
    student = Student(
        id=new_id(),
        student_no=payload.student_no,
        name=payload.name,
        class_name=payload.class_name,
        grade_year=payload.grade_year,
        status=payload.status,
        is_deleted=0,
        created_at=now,
        updated_at=now,
    )
    with write_transaction(db):
        student_repo.insert(db, student)
    logger.info("学生已创建 id=%s student_no=%s", student.id, student.student_no)
    return StudentOut.model_validate(student)


@router.get("", response_model=Page[StudentOut])
def list_students(
    class_name: Optional[str] = Query(default=None),
    grade_year: Optional[int] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    keyword: Optional[str] = Query(default=None),
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_staff),
) -> Page[StudentOut]:
    """分页查询学生（AC5/AC28）。"""
    if status_filter is not None and status_filter not in ("active", "inactive"):
        raise validation_error("status", "必须为 active 或 inactive")
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
        items=[StudentOut.model_validate(i) for i in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/{student_id}", response_model=StudentOut)
def get_student(
    student_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> StudentOut:
    """查询单个学生（AC4）；学生角色仅可查本人。"""
    ensure_student_self(principal, student_id)
    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})
    return StudentOut.model_validate(student)


@router.patch("/{student_id}", response_model=StudentOut)
def update_student(
    student_id: str,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
) -> StudentOut:
    """更新学生（student_no 不可修改）。"""
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise validation_error("body", "至少提供一个可更新字段")
    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})
    with write_transaction(db):
        for field, value in changes.items():
            setattr(student, field, value)
        student.updated_at = utc_now()
        db.flush()
    return StudentOut.model_validate(student)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(
    student_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
) -> Response:
    """逻辑删除学生（AC6/AC27）。"""
    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})
    active_scores = student_repo.count_active_scores(db, student_id)
    if active_scores > 0:
        raise AppError(
            ErrorCode.STUDENT_HAS_SCORES,
            details={"student_id": student_id, "active_scores": active_scores},
        )
    with write_transaction(db):
        student_repo.soft_delete(db, student,