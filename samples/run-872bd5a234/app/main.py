"""应用装配、异常处理器注册、app 实例导出。

AC13 要求所有错误响应体均为合法 JSON 且含非空 error_code / message，
因此这里注册 ApiError、RequestValidationError 与兜底 Exception 三个处理器，
保证不出现 5xx 裸栈。
追溯：F1, F2, F5。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import ApiError, ErrorCode, error_response
from app.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Calculator Add API",
    version="1.0.0",
    description="计算器加法 REST API：POST /add、GET /health、POST /add/batch",
)

app.include_router(router)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """业务异常 → 结构化错误响应（AC6–AC12, AC18, AC19）。"""
    logger.info(
        "ApiError on %s %s: %s field=%r index=%r",
        request.method,
        request.url.path,
        exc.error_code,
        exc.field,
        exc.index,
    )
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """框架级校验异常 → 400 INVALID_ARGUMENT（保持错误形状统一）。"""
    logger.info("RequestValidationError on %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=400,
        content=error_response(
            ErrorCode.INVALID_ARGUMENT,
            "request validation failed",
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """兜底处理器：仍返回合法 JSON，避免裸栈（AC13）。"""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_response(
            ErrorCode.INTERNAL_ERROR,
            "internal server error",
        ),
    )


__all__ = ["app"]
