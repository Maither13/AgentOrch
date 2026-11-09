"""v1 路由聚合。后续 workflows / tasks / runs 模块在此挂载。"""

from fastapi import APIRouter

from app.api.v1 import agents, chat, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(chat.router)
api_router.include_router(agents.router)
