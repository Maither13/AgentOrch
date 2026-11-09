"""FastAPI 依赖注入。"""

from __future__ import annotations

from fastapi import Request

from app.agents.registry import Team
from app.core.config import Settings, get_settings
from app.llm.client import DeepSeekClient
from app.orchestration.store import RunStore


def get_llm(request: Request) -> DeepSeekClient:
    """共享的 DeepSeek 客户端，由 lifespan 创建并挂在 app.state 上。"""
    return request.app.state.llm


def get_team(request: Request) -> Team:
    """lifespan 中装配好的默认团队。"""
    return request.app.state.team


def get_run_store(request: Request) -> RunStore:
    """进程内运行记录存储。"""
    return request.app.state.runs


def get_app_settings() -> Settings:
    return get_settings()
