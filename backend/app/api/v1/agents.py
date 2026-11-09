"""Agent / 团队接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agents.base import BaseAgent
from app.agents.registry import Team, list_roles
from app.agents.tools import TOOL_REGISTRY
from app.api.deps import get_team
from app.api.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    AgentSpecOut,
    RoleOut,
    TeamOut,
    ToolOut,
    UsageOut,
)

router = APIRouter(tags=["agents"])


def _tool_out(name: str) -> ToolOut:
    spec = TOOL_REGISTRY[name]
    return ToolOut(
        name=spec.name,
        display_name=spec.display_name,
        description=spec.description,
        implemented=spec.implemented,
    )


def _agent_out(agent: BaseAgent) -> AgentSpecOut:
    spec = agent.spec
    return AgentSpecOut(
        id=spec.id,
        role=spec.role,
        display_name=spec.display_name,
        description=spec.description,
        system_prompt=spec.system_prompt,
        allowed_tools=[_tool_out(tool.name) for tool in spec.allowed_tools],
        model=spec.model,
        temperature=spec.temperature,
    )


@router.get("/agents/roles", response_model=list[RoleOut], summary="6 个内置 Agent 角色")
async def get_roles() -> list[RoleOut]:
    return [
        RoleOut(
            role=item.role,
            display_name=item.display_name,
            description=item.description,
            allowed_tools=[_tool_out(name) for name in item.allowed_tools],
            temperature=item.temperature,
        )
        for item in list_roles()
    ]


@router.get("/agents/tools", response_model=list[ToolOut], summary="全部工具及说明")
async def get_tools() -> list[ToolOut]:
    return [_tool_out(name) for name in TOOL_REGISTRY]


@router.get("/team", response_model=TeamOut, summary="当前团队配置")
async def get_team_config(team: Team = Depends(get_team)) -> TeamOut:
    return TeamOut(
        id=team.id,
        name=team.name,
        description=team.description,
        captain=team.captain.id,
        members=[_agent_out(agent) for agent in team.ordered()],
        source=team.source.name,
    )


@router.get("/agents/{agent_id}", response_model=AgentSpecOut, summary="单个 Agent 配置")
async def get_agent(agent_id: str, team: Team = Depends(get_team)) -> AgentSpecOut:
    return _agent_out(team.get(agent_id))


@router.post("/agents/{agent_id}/run", response_model=AgentRunResponse, summary="试跑单个 Agent")
async def run_agent(
    agent_id: str,
    payload: AgentRunRequest,
    team: Team = Depends(get_team),
) -> AgentRunResponse:
    agent = team.get(agent_id)
    result = await agent.run(
        payload.task,
        context=payload.context,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    return AgentRunResponse(
        agent_id=result.agent_id,
        role=result.role,
        display_name=result.display_name,
        content=result.content,
        model=result.model,
        mode=result.mode,
        usage=UsageOut(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
        latency_ms=result.latency_ms,
        allowed_tools=list(result.allowed_tools),
    )
