"""AgentOrch 应用入口。

启动：python run.py  或  uvicorn app.main:app --reload
文档：http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.llm.client import DeepSeekClient

logger = logging.getLogger("agentorch")
WEB_DIR = Path(__file__).resolve().parent / "web"

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings)
    app.state.llm = DeepSeekClient(settings)
    logger.info(
        "AgentOrch 启动 | env=%s | mode=%s | docs=http://%s:%s/docs",
        settings.environment,
        app.state.llm.mode,
        settings.host,
        settings.port,
    )
    try:
        yield
    finally:
        await app.state.llm.aclose()
        logger.info("AgentOrch 已停止")


app = FastAPI(
    title="AgentOrch API",
    version=settings.app_version,
    description="多智能体编排调度平台 · 后端服务（FastAPI + DeepSeek）",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """给每个请求打上 request_id，并记录耗时。"""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    cost_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info("%s %s -> %s (%.1fms) rid=%s", request.method, request.url.path, response.status_code, cost_ms, request_id)
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("业务异常 [%s] %s %s: %s", exc.code, request.method, request.url.path, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}, "request_id": getattr(request.state, "request_id", None)},
    )


app.include_router(api_router, prefix=settings.api_prefix)

if WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
