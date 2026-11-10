"""Pydantic 请求/响应模型（横切模块）。"""

from __future__ import annotations

import re
from typing import Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")

SEMESTER_PATTERN = re.compile(r"^\d{4}-[12]$")
STUDENT_NO_PATTERN = re.compile(r"^[A-Za-z0-9]{4,20}$")
COURSE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9]{2,20}$")


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: Optional[dict] = None


# ---------------------------------------------------------------- 学生
class StudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_no: str = Field(min_length=4, max_length=20)
    name: str = Field(min_length=1, max_length=50)
    class_name: str = Field(min_length=1, max_length=50)
    grade_year: int = Field(ge=1900, le=2100)
    status: Literal["active", "inactive"] = "active"

    @field_validator("student_no")
    @classmethod
    def _check_student_no(cls, value: str) -> str:
        if not STUDENT_NO_PATTERN.match(value):
            raise ValueError("student_no 必须为 4-20 位字母或数字")
        return value

    @field_validator("name", "class_name")
    @classmethod
    def _strip_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空白字符串")
        return value


class StudentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    class_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    grade_year: Optional[int] = Field(default=None, ge=1900, le=2100)
    status: Optional[Literal["active", "inactive"]] = None

    @field_validator("name", "class_name")
    @classmethod
    def _strip_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("不能为空白字符串")
        return value


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_no: str
    name: str
    class_name: str
    grade_year: int
    status: str
    created_at: str
    updated_at: str


# ---------------------------------------------------------------- 课程
class CourseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=1, max_length=50)
    credit: float = Field(ge=0.5, le=10)
    full_score: float = Field(default=100.0, ge=1, le=1000)

    @field_validator("course_code")
    @classmethod
    def _check_course_code(cls, value: str) -> str:
        if not COURSE_CODE_PATTERN.match(value):
            raise ValueError("course_code 必须为 2-20 位字母或数字")
        return value

    @field_validator("credit")
    @classmethod
    def _check_credit_step(cls, value: float) -> float:
        if round(value * 2) != value * 2:
            raise ValueError("credit 必须为 0.5 的整数倍")
        return value

    @field_validator("name")
    @classmethod
    def _strip_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空白字符串")
        return value


class CourseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    credit: Optional[float] = Field(default=None, ge=0.5, le=10)
    full_score: Optional[float] = Field(default=None, ge=1, le=1000)

    @field_validator("credit")
    @classmethod
    def _check_credit_step(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and round(value * 2) != value * 2:
            raise ValueError("credit 必须为 0.5 的整数倍")
        return value

    @field_validator("name")
    @classmethod
    def _strip_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("不能为空白字符串")
        return value


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_code: str
    name: str
    credit: float
    full_score: float
    created_at: str
    updated_at: str


# ---------------------------------------------------------------- 成绩
class ScoreCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: str = Field(min_length=1, max_length=36)
    course_id: str = Field(min_length=1, max_length=36)
    semester: str
    score: float
    operator_id: str = Field(min_length=1, max_length=64)

    @field_validator("semester")
    @classmethod
    def _check_semester(cls, value: str) -> str:
        if not SEMESTER_PATTERN.match(value):
            raise ValueError("semester 必须匹配 YYYY-S，S 为 1 或 2")
        return value


class ScoreUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    operator_id: str = Field(min_length=1, max_length=64)
    reason: Optional[str] = Field(default=None, max_length=200)


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    course_id: str
    semester: str
    score: float
    operator_id: str
    created_at: str
    updated_at: str


class ScoreUpdateOut(ScoreOut):
    previous_score: float


class ScoreListItem(BaseModel):
    id: str
    student_id: str
    student_no: str
    student_name: str
    course_id: str
    course_code: str
    course_name: str
    semester: str
    score: float
    updated_at: str


class ScoreHistoryItem(BaseModel):
    changed_at: str
    operator_id: str
    previous_score: float
    new_score: float
    reason: Optional[str] = None


class ScoreHistoryList(BaseModel):
    items: List[ScoreHistoryItem]


class BatchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: str = Field(min_length=1, max_length=36)
    course_id: str = Field(min_length=1, max_length=36)
    semester: str
    score: float

    @field_validator("semester")
    @classmethod
    def _check_semester(cls, value: str) -> str:
        if not SEMESTER_PATTERN.match(value):
            raise ValueError("semester 必须匹配 YYYY-S，S 为 1 或 2")
        return value


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: List[BatchRecord] = Field(min_length=1, max_length=200)
    operator_id: str = Field(min_length=1, max_length=64)


class BatchResultItem(BaseModel):
    index: int
    status: Literal["success", "failed"]
    score_id: Optional[str] = None
    error_code: Optional[str] = None


class BatchResponse(BaseModel):
    succeeded: int
    failed: int
    results: List[BatchResultItem]


# ---------------------------------------------------------------- 统计
class CourseStatistics(BaseModel):
    course_id: str
    semester: Optional[str] = None
    count: int
    average: Optional[float] = None
    max: Optional[float] = None
    min: Optional[float] = None
    pass_rate: Optional[float] = None
    pass_line: float


class ClassStatistics(BaseModel):
    class_name: str
    semester: str
    student_count: int
    average: Optional[float] = None
    pass_rate: Optional[float] = None


class TranscriptItem(BaseModel):
    course_id: str
    course_code: str
    course_name: str
    credit: float
    score: float
    full_score: float


class Transcript(BaseModel):
    student_id: str
    student_no: str
    student_name: str
    semester: str
    items: List[TranscriptItem]
    average: Optional[float] = None
    total_credit: float
