"""对话接口：普通返回 + SSE 流式返回。"""

from __future__ import annotations

import json
import logging
import time
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_llm
from app.api.schemas import ChatRequest, ChatResponse, UsageOut
from app.core.errors import LLMError
from app.llm.client import DeepSeekClient, Usage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # 关闭 Nginx 缓冲
}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _usage_out(usage: Usage | None) -> dict:
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


@router.post("/chat", response_model=ChatResponse, summary="对话（一次性返回）")
async def chat(payload: ChatRequest, llm: DeepSeekClient = Depends(get_llm)) -> ChatResponse:
    result = await llm.chat(
        [m.model_dump() for m in payload.messages],
        model=payload.model,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        json_mode=payload.json_mode,
    )
    return ChatResponse(
        id=result.id,
        model=result.model,
        content=result.content,
        reasoning_content=result.reasoning_content,
        finish_reason=result.finish_reason,
        usage=UsageOut(**_usage_out(result.usage)),
        latency_ms=result.latency_ms,
        mode=result.mode,
    )


@router.post("/chat/stream", summary="对话（SSE 流式返回）")
async def chat_stream(payload: ChatRequest, llm: DeepSeekClient = Depends(get_llm)) -> StreamingResponse:
    # 配置问题在建立流之前抛出，前端能拿到真实的 4xx/5xx
    if not llm.available:
        raise LLMError(
            "未配置 DEEPSEEK_API_KEY，请在 backend/.env 中填写后重启服务",
            status_code=503,
            code="llm_not_configured",
        )

    messages = [m.model_dump() for m in payload.messages]

    async def event_source() -> AsyncIterator[str]:
        started = time.perf_counter()
        usage: Usage | None = None
        finish_reason: str | None = None
        try:
            async for chunk in llm.stream(
                messages,
                model=payload.model,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                json_mode=payload.json_mode,
            ):
                if chunk.reasoning_content:
                    yield _sse({"type": "reasoning", "delta": chunk.reasoning_content})
                if chunk.content:
                    yield _sse({"type": "delta", "delta": chunk.content})
                if chunk.usage:
                    usage = chunk.usage
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason
        except LLMError as exc:
            logger.warning("流式调用失败 code=%s: %s", exc.code, exc.message)
            yield _sse({"type": "error", "code": exc.code, "message": exc.message})
            return
        except Exception:  # noqa: BLE001
            logger.exception("流式调用出现未预期异常")
            yield _sse({"type": "error", "code": "internal_error", "message": "服务内部错误"})
            return

        yield _sse(
            {
                "type": "done",
                "finish_reason": finish_reason,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "usage": _usage_out(usage),
                "mode": llm.mode,
            }
        )

    return StreamingResponse(event_source(), media_type="text/event-stream", headers=SSE_HEADERS)
