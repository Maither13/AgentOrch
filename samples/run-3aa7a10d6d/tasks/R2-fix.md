## 根因定位

评审记录中的阻断项 B-1 至 B-5 全部指向同一个根因：**上一轮只交付了领域层（models/repositories/services/security/schemas），HTTP 层与测试资产完全没有写入工作区**。

- `tests/conftest.py:19-22` 的 `from app.main import app` 抛出 `ModuleNotFoundError`，导致 `app=None`，`_require_app` 对全部 33 个用例执行 `pytest.skip`，因此出现 `passed=0 / skipped=33 / 退出码 0` 的假绿。
- `app/routers/` 只有 `__init__.py`、`deps.py`，`security.require_roles` / `ensure_student_self` 没有任何 `Depends` 消费方，AC26 无法端到端验证。
- `app/main.py` 缺失，`AppError` 全局处理器未注册，`{error_code, message, details}` 错误响应链路未闭环。
- `tests/test_scores.py`、`test_statistics.py`、`test_batch.py`、`test_auth_pagination.py` 未写入工作区，AC9–AC26、AC28 无任何用例。

已确认可复用的既有资产（本轮不改动）：`app/models.py:96-103` 部分唯一索引 `sqlite_where=text("is_deleted = 0")` 正确；`app/repositories/score_repo.py:9,124` 已用 `sqlalchemy.case`；`app/services/score_service.py`、`app/security.py`、`app/schemas.py`、`app/routers/deps.py` 逻辑完整。

## 本轮改动文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `app/main.py` | 新建 | FastAPI 实例、`init_db()` startup、挂载 `/api/v1`、注册 `AppError`/`RequestValidationError`/`IntegrityError` 全局处理器 |
| `app/routers/students.py` | 新建（重写） | AC1–AC6、AC27 学生侧；`require_staff` 写、`require_admin` 删 |
| `app/routers/courses.py` | 新建 | AC7–AC8、AC27 课程侧 |
| `app/routers/scores.py` | 新建 | AC9–AC19；`/histories` 子资源 |
| `app/routers/statistics.py` | 新建 | AC20–AC23 |
| `app/routers/batch.py` | 新建 | AC24–AC25 |
| `tests/test_scores.py` | 新建 | AC9–AC19 |
| `tests/test_statistics.py` | 新建 | AC20–AC23 |
| `tests/test_batch.py` | 新建 | AC24–AC25 |
| `tests/test_auth_pagination.py` | 新建 | AC26、AC28 |

```python path=app/main.py
"""FastAPI 应用入口：实例装配、建表、路由挂载与全局异常处理。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import settings
from app.db import init_db
from app.errors import AppError, ErrorCode
from app.routers import batch, courses, scores, statistics, students

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """启动时建表；关闭时仅记录日志（连接由引擎池管理）。"""
    init_db()
    logger.info("应用启动完成，api_prefix=%s", settings.api_prefix)
    try:
        yield
    finally:
        logger.info("应用已关闭")


app = FastAPI(
    title="学生成绩管理系统",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------- 异常处理
def _error_body(error_code: str, message: str, details: Dict[str, Any] | None) -> Dict[str, Any]:
    return {"error_code": error_code, "message": message, "details": details}


@app.exception_handler(AppError)
async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """业务异常 -> {error_code, message, details}（§4.6）。"""
    logger.info("业务异常: %s %s", exc.code.value, exc.message)
    return JSONResponse(
        status_code=exc.http_status,
        content=_error_body(exc.code.value, exc.message, exc.details),
    )


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic/FastAPI 请求校验失败统一映射为 400 VALIDATION_ERROR。"""
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = [str(part) for part in first.get("loc", []) if part != "body"]
    field = ".".join(loc) if loc else "body"
    reason = str(first.get("msg", "请求体校验失败"))
    logger.info("请求校验失败: field=%s reason=%s", field, reason)
    return JSONResponse(
        status_code=400,
        content=_error_body(
            ErrorCode.VALIDATION_ERROR.value,
            f"字段 {field} 校验失败: {reason}",
            {"field": field, "reason": reason, "errors": errors},
        ),
    )


@app.exception_handler(IntegrityError)
async def _integrity_error_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
    """兜底唯一约束冲突，避免 500 泄露 SQL 细节。"""
    logger.warning("数据库完整性约束冲突: %s", exc)
    return JSONResponse(
        status_code=409,
        content=_error_body(
            ErrorCode.VALIDATION_ERROR.value,
            "数据完整性约束冲突",
            {"reason": "integrity_error"},
        ),
    )


@app.exception_handler(SQLAlchemyError)
async def _sqlalchemy_error_handler(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """数据库层未知异常：记录完整堆栈，对外返回通用错误。"""
    logger.exception("数据库异常: %s", exc)
    return JSONResponse(
        status_code=500,
        content=_error_body("INTERNAL_ERROR", "服务内部错误", None),
    )


# ---------------------------------------------------------------- 路由挂载
app.include_router(students.router, prefix=settings.api_prefix)
app.include_router(courses.router, prefix=settings.api_prefix)
app.include_router(scores.router, prefix=settings.api_prefix)
app.include_router(statistics.router, prefix=settings.api_prefix)
app.include_router(batch.router, prefix=settings.api_prefix)


@app.get("/health", tags=["ops"])
def health() -> Dict[str, str]:
    """健康检查。"""
    return {"status": "ok"}
```

```python path=app/routers/students.py
"""学生档案管理路由（F1）：AC1–AC6、AC27。"""

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
from app.models import Student
from app.repositories import student_repo
from app.routers.deps import Pagination, pagination
from app.schemas import Page, StudentCreate, StudentOut, StudentUpdate
from app.security import Principal, require_admin, require_staff

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/students", tags=["students"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_out(student: Student) -> StudentOut:
    return StudentOut.model_validate(student)


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> StudentOut:
    """创建学生（AC1）；学号重复返回 409（AC2）。"""
    if student_repo.get_by_student_no(db, payload.student_no) is not None:
        raise AppError(
            ErrorCode.STUDENT_NO_DUPLICATED,
            details={"student_no": payload.student_no},
        )

    now = _utc_now()
    student = Student(
        id=str(uuid.uuid4()),
        student_no=payload.student_no,
        name=payload.name,
        class_name=payload.class_name,
        grade_year=payload.grade_year,
        status=payload.status,
        is_deleted=0,
        created_at=now,
        updated_at=now,
    )
    try:
        student_repo.insert(db, student)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("创建学生唯一约束冲突: %s", exc)
        raise AppError(
            ErrorCode.STUDENT_NO_DUPLICATED,
            details={"student_no": payload.student_no},
        ) from exc
    db.refresh(student)
    return _to_out(student)


@router.get("", response_model=Page[StudentOut])
def list_students(
    class_name: Optional[str] = Query(default=None, max_length=50),
    grade_year: Optional[int] = Query(default=None, ge=1900, le=2100),
    status_filter: Optional[str] = Query(default=None, alias="status", pattern="^(active|inactive)$"),
    keyword: Optional[str] = Query(default=None, max_length=50),
    page: Pagination = Depends(pagination),
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> Page[StudentOut]:
    """分页查询学生，支持班级/年级/状态/关键字过滤（AC5）。"""
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
        items=[_to_out(item) for item in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/{student_id}", response_model=StudentOut)
def get_student(
    student_id: str,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> StudentOut:
    """按 ID 查询学生（AC4）。"""
    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})
    return _to_out(student)


@router.patch("/{student_id}", response_model=StudentOut)
def update_student(
    student_id: str,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> StudentOut:
    """局部更新学生；空请求体视为校验失败，student_no 不可修改。"""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            message="请求体不能为空，至少提供一个可更新字段",
            details={"field": "body", "reason": "empty_patch"},
        )

    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})

    for field_name, value in changes.items():
        if value is None:
            continue
        setattr(student, field_name, value)
    student.updated_at = _utc_now()
    db.commit()
    db.refresh(student)
    return _to_out(student)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(
    student_id: str,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_admin),
) -> Response:
    """逻辑删除学生（AC6）；存在未删除成绩时拒绝（AC27）。"""
    student = student_repo.get_active(db, student_id)
    if student is None:
        raise AppError(ErrorCode.STUDENT_NOT_FOUND, details={"student_id": student_id})

    active_scores = student_repo.count_active_scores(db, student_id)
    if active_scores > 0:
        raise AppError(
            ErrorCode.STUDENT_HAS_SCORES,
            details={"student_id": student_id, "active_score_count": active_scores},
        )

    student_repo.soft_delete(db, student, _utc_now())
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

```python path=app/routers/courses.py
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
```

```python path=app/routers/scores.py
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
```

```python path=app/routers/statistics.py
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
```

```python path=app/routers/batch.py
"""批量成绩导入路由（F5）：AC24–AC25。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import BatchRequest, BatchResponse, BatchResultItem
from app.security import Principal, require_staff
from app.services import score_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scores", tags=["batch"])


@router.post("/batch", response_model=BatchResponse)
def batch_import(
    payload: BatchRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> BatchResponse:
    """批量录入成绩：逐条独立事务，单条失败不影响其他条（AC24/AC25）。"""
    records = [item.model_dump() for item in payload.records]
    succeeded, failed, results = score_service.batch_create(
        db, records=records, operator_id=payload.operator_id
    )
    logger.info("批量导入完成: succeeded=%d failed=%d", succeeded, failed)
    return BatchResponse(
        succeeded=succeeded,
        failed=failed,
        results=[BatchResultItem(**item) for item in results],
    )
```

```python path=tests/test_scores.py
"""成绩管理（F3）：AC9–AC19。"""
from __future__ import annotations

from conftest import API


# --------------------------- AC9 正常录入 ---------------------------
def test_ac9_create_score_success(client, admin_headers, make_student, make_course):
    stu = make_student()
    course = make_course()
    resp = client.post(
        f"{API}/scores",
        json={
            "student_id": stu["id"],
            "course_id": course["id"],
            "semester": "2024-1",
            "score": 88.5,
            "operator_id": "op-admin",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert isinstance(body.get("id"), str) and body["id"]
    assert body["student_id"] == stu["id"]
    assert body["course_id"] == course["id"]
    assert body["semester"] == "2024-1"
    assert body["score"] == 88.5
    assert body["operator_id"] == "op-admin"
    assert body.get("created_at") and body.get("updated_at")


# --------------------------- AC10 三元组唯一 ---------------------------
def test_ac10_duplicated_triplet_rejected(
    client, admin_headers, make_student, make_course, make_score, assert_error
):
    stu = make_student()
    course = make_course()
    make_score(stu["id"], course["id"], score=70, semester="2024-1")
    resp = client.post(
        f"{API}/scores",
        json={
            "student_id": stu["id"],
            "course_id": course["id"],
            "semester": "2024-1",
            "score": 90,
            "operator_id": "op-admin",
        },
        headers=admin_headers,
    )
    assert_error(resp, 409, "SCORE_DUPLICATED")


def test_ac10_same_triplet_after_delete_allowed(
    client, admin_headers, make_student, make_course, make_score
):
    """逻辑删除后同一三元组可重新录入（部分唯一索引）。"""
    stu = make_student()
    course = make_course()
    first = make_score(stu["id"], course["id"], score=60, semester="2024-1")
    assert client.delete(f"{API}/scores/{first['id']}", headers=admin_headers).status_code == 204
    resp = client.post(
        f"{API}/scores",
        json={
            "student_id": stu["id"],
            "course_id": course["id"],
            "semester": "2024-1",
            "score": 75,
            "operator_id": "op-admin",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["score"] == 75


# --------------------------- AC11 分数范围 ---------------------------
def test_ac11_score_negative_rejected(
    client, admin_headers, make_student, make_course, assert_error
):
    stu = make_student()
    course = make_course()
    resp = client.post(
        f"{API}/scores",
        json={
            "student_id": stu["id"],
            "course_id": course["id"],
            "semester": "2024-1",
            "score": -1,
            "operator_id": "op-admin",
        },
        headers=admin_headers,
    )
    assert_error(resp, 400, "SCORE_OUT_OF_RANGE")


def test_ac11_score_above_full_score_rejected(
    client, admin_headers, make_student, make_course, assert_error
):
    stu = make_student()
    course = make_course(full_score=100)
    resp = client.post(
        f"{API}/scores",
        json={
            "student_id": stu["id"],
            "course_id": course["id"],
            "semester": "2024-1",
            "score": 100.5,
            "operator_id": "op-admin",
        },
        headers=admin_headers,
    )
    assert_error(resp, 400, "SCORE_OUT_OF_RANGE")


def test_ac11_score_custom_full_score_boundary(
    client, admin_headers, make_student, make_course
):
    stu = make_student()
    course = make_course(full_score=150)
    resp = client.post(
        f"{API}/scores",
        json={
            "student_id": stu["id"],
            "course_id": course["id"],
            "semester": "2024-1",
            "score": 150,
            "operator_id": "op-admin",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text


def test_ac11_score_two_decimals_rejected(
    client, admin_headers, make_student, make_course, assert_error
):
    stu = make_student()
    course = make_course()
    resp = client.post(
        f"{API}/scores",
        json={
            "student_id": stu["id"],
            "course_id": course["id"],
            "semester": "2024-1",
            "score": 88.55,
            "operator_id": "op-admin",
        },
        headers=admin_headers,
    )
    assert_error(resp,