"""系统接口：健康检查、模型列表、连通性探测。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_app_settings, get_llm
from app.api.schemas import HealthResponse, LLMStatus, ModelInfo, PingResponse, UsageOut
from app.core.config import Settings
from app.llm.client import DeepSeekClient

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health(
    settings: Settings = Depends(get_app_settings),
    llm: DeepSeekClient = Depends(get_llm),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        llm=LLMStatus(
            provider=llm.provider,
            model=llm.default_model,
            base_url=llm.base_url,
            mode=llm.mode,
            configured=llm.available,
        ),
    )


@router.get("/llm/models", response_model=list[ModelInfo], summary="可用模型")
async def list_models(settings: Settings = Depends(get_app_settings)) -> list[ModelInfo]:
    return [
        ModelInfo(
            id=settings.deepseek_model,
            label="DeepSeek Chat",
            description="通用对话 / 代码生成，Agent 默认模型",
        ),
        ModelInfo(
            id=settings.deepseek_reasoner_model,
            label="DeepSeek Reasoner",
            description="深度推理，适合任务拆解与方案设计",
            supports_reasoning=True,
        ),
    ]


@router.post("/llm/ping", response_model=PingResponse, summary="真实调用一次模型，验证连通性")
async def ping(llm: DeepSeekClient = Depends(get_llm)) -> PingResponse:
    result = await llm.ping()
    return PingResponse(
        ok=bool(result.content.strip()),
        reply=result.content.strip(),
        model=result.model,
        mode=result.mode,
        latency_ms=result.latency_ms,
        usage=UsageOut(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
    )
