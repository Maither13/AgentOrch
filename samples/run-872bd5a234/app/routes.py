"""路由与校验顺序编排。

全局不变量（C4）：Content-Type → JSON 解析 → 字段校验 → 计算 → 有限性检查。
顺序颠倒会让 text/plain 的非 JSON body 误返 400 而非 415（AC11 vs AC12）。
追溯：F1, F2, F5, F6。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.errors import ApiError, ErrorCode
from app.schemas import AddResponse, BatchResponse, HealthResponse
from app.service import add, add_batch, ensure_finite, validate_pair

logger = logging.getLogger(__name__)

router = APIRouter()

#: 允许的 Content-Type 主类型（允许 application/json; charset=utf-8）
_JSON_MEDIA_TYPE = "application/json"


def _check_content_type(request: Request) -> None:
    """步骤 1：Content-Type 检查（AC12）。

    在 JSON 解析之前执行，保证 text/plain 的非 JSON body 返回 415。
    """
    raw = request.headers.get("content-type")
    if raw is None:
        # 无 Content-Type 视为不支持（需求 4.1 要求 application/json）
        raise ApiError(
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "Content-Type header must be application/json",
        )
    media_type = raw.split(";", 1)[0].strip().lower()
    if media_type != _JSON_MEDIA_TYPE:
        raise ApiError(
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            f"unsupported media type '{media_type}', expected application/json",
        )


async def _read_json(request: Request) -> Any:
    """步骤 2：JSON 解析（AC11）。空 body 与非法 JSON 同码。"""
    body = await request.body()
    if not body or not body.strip():
        raise ApiError(ErrorCode.INVALID_JSON, "request body must not be empty")
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.info("JSON parse failure: %s", exc)
        raise ApiError(
            ErrorCode.INVALID_JSON,
            "request body is not valid JSON",
        ) from exc


@router.post("/add", response_model=AddResponse)
async def add_endpoint(request: Request) -> JSONResponse:
    """POST /add：返回两数之和（AC1–AC13, AC19）。"""
    _check_content_type(request)
    payload = await _read_json(request)

    # 步骤 3：字段存在性 + 类型校验（AC6–AC10）
    a, b = validate_pair(payload)

    # 步骤 4：计算（AC1–AC5，严格 IEEE 754）
    result = add(a, b)

    # 步骤 5：有限性检查（AC19）
    ensure_finite(result)

    # AC3：显式回显 a、b，不用 **payload 展开
    return JSONResponse(
        status_code=200,
        content={"result": result, "a": a, "b": b},
    )


@router.get("/health", response_model=HealthResponse)
async def health_endpoint() -> Dict[str, str]:
    """GET /health：健康检查（AC16）。无入参、无依赖，恒成功。"""
    return {"status": "ok"}


@router.post("/add/batch", response_model=BatchResponse)
async def add_batch_endpoint(request: Request) -> JSONResponse:
    """POST /add/batch：批量加法（AC17/AC18）。"""
    _check_content_type(request)
    payload = await _read_json(request)

    if not isinstance(payload, dict):
        raise ApiError(
            ErrorCode.INVALID_ARGUMENT,
            "request body must be a JSON object with field 'items'",
            field="items",
        )
    if "items" not in payload:
        raise ApiError(
            ErrorCode.INVALID_ARGUMENT,
            "field 'items' is required",
            field="items",
        )

    results = add_batch(payload["items"])
    return JSONResponse(status_code=200, content={"results": results})


__all__ = ["router", "add_endpoint", "health_endpoint", "add_batch_endpoint"]
