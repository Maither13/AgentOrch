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
