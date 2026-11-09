"""Agent 包：内置角色、工具权限与团队装配。"""

from app.agents.base import AgentRunResult, AgentSpec, BaseAgent
from app.agents.registry import RoleInfo, Team, list_roles, load_team
from app.agents.roles import AGENT_CLASSES

__all__ = [
    "AGENT_CLASSES",
    "AgentRunResult",
    "AgentSpec",
    "BaseAgent",
    "RoleInfo",
    "Team",
    "list_roles",
    "load_team",
]
