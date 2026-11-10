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
