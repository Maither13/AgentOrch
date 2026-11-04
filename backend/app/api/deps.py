"""FastAPI 依赖注入。"""

from __future__ import annotations

from fastapi import Request

from app.core.config import Settings, get_settings
from app.llm.client import DeepSeekClient


def get_llm(request: Request) -> DeepSeekClient:
    """共享的 DeepSeek 客户端，由 lifespan 创建并挂在 app.state 上。"""
    return request.app.state.llm


def get_app_settings() -> Settings:
    return get_settings()
