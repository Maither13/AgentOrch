"""6 个内置 Agent 角色。

角色是固定写死的，不支持动态注册；团队配置只决定「用哪些角色、各叫什么 id」。
"""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.roles.architect import ArchitectAgent
from app.agents.roles.captain import CaptainAgent
from app.agents.roles.developer import DeveloperAgent
from app.agents.roles.product_manager import ProductManagerAgent
from app.agents.roles.reviewer import ReviewerAgent
from app.agents.roles.tester import TesterAgent

AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    cls.role: cls
    for cls in (
        CaptainAgent,
        ProductManagerAgent,
        ArchitectAgent,
        DeveloperAgent,
        TesterAgent,
        ReviewerAgent,
    )
}

__all__ = [
    "AGENT_CLASSES",
    "ArchitectAgent",
    "CaptainAgent",
    "DeveloperAgent",
    "ProductManagerAgent",
    "ReviewerAgent",
    "TesterAgent",
]
