"""v1 路由聚合。后续 agents / workflows / tasks / runs 模块在此挂载。"""

from fastapi import APIRouter

from app.api.v1 import chat, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(chat.router)
