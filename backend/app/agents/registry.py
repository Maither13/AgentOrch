"""团队装配：一个团队就是一份 JSON 配置 + 6 个固定角色类。

团队 JSON 只决定三件事：团队元信息、队长是谁、有哪些成员（成员 id -> 角色）。
不做动态注册、不做版本管理、不做可视化配置。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.base import BaseAgent
from app.agents.roles import AGENT_CLASSES
from app.core.errors import AppError
from app.llm.client import DeepSeekClient

TEAM_DIR = Path(__file__).resolve().parent / "teams"


# --------------------------------------------------------------------------- #
# 团队配置模型
# --------------------------------------------------------------------------- #
class TeamMemberConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    role: str
    name: str | None = Field(default=None, max_length=40)


class TeamConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    captain: str
    members: list[TeamMemberConfig] = Field(min_length=1)


# --------------------------------------------------------------------------- #
# 运行时团队
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Team:
    id: str
    name: str
    description: str
    captain: BaseAgent
    members: dict[str, BaseAgent]
    source: Path

    def get(self, agent_id: str) -> BaseAgent:
        agent = self.members.get(agent_id)
        if agent is None:
            raise AppError(
                f"团队中不存在 Agent：{agent_id}",
                status_code=404,
                code="agent_not_found",
            )
        return agent

    def ordered(self) -> list[BaseAgent]:
        """按团队配置中的声明顺序返回成员。"""
        return list(self.members.values())


@dataclass(frozen=True, slots=True)
class RoleInfo:
    role: str
    display_name: str
    description: str
    allowed_tools: tuple[str, ...]
    temperature: float


def list_roles() -> list[RoleInfo]:
    return [
        RoleInfo(
            role=cls.role,
            display_name=cls.display_name,
            description=cls.description,
            allowed_tools=cls.allowed_tools,
            temperature=cls.temperature,
        )
        for cls in AGENT_CLASSES.values()
    ]


def create_agent(
    llm: DeepSeekClient,
    role: str,
    *,
    agent_id: str | None = None,
    name: str | None = None,
) -> BaseAgent:
    cls = AGENT_CLASSES.get(role)
    if cls is None:
        raise AppError(f"未知的 Agent 角色：{role}", status_code=404, code="role_not_found")
    return cls(llm, agent_id=agent_id, name=name)


# --------------------------------------------------------------------------- #
# 加载与校验
# --------------------------------------------------------------------------- #
def load_team(llm: DeepSeekClient, team_id: str) -> Team:
    path = TEAM_DIR / f"{team_id}.json"
    if not path.is_file():
        raise AppError(
            f"团队配置不存在：{path.name}",
            status_code=500,
            code="team_config_missing",
        )
    return load_team_file(llm, path)


def load_team_file(llm: DeepSeekClient, path: Path) -> Team:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AppError(f"读取团队配置失败：{exc}", status_code=500, code="team_config_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise AppError(f"团队配置不是合法 JSON：{exc}", status_code=500, code="team_config_invalid") from exc

    try:
        config = TeamConfig.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(item) for item in first["loc"])
        raise AppError(
            f"团队配置校验失败：{location} {first['msg']}",
            status_code=500,
            code="team_config_invalid",
        ) from exc

    ids = [member.id for member in config.members]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise AppError(f"团队成员 id 重复：{duplicates}", status_code=500, code="team_config_invalid")

    unknown_roles = sorted({member.role for member in config.members} - AGENT_CLASSES.keys())
    if unknown_roles:
        raise AppError(f"团队配置包含未知角色：{unknown_roles}", status_code=500, code="team_config_invalid")

    if config.captain not in ids:
        raise AppError(
            f"队长 {config.captain} 不在成员列表中",
            status_code=500,
            code="team_config_invalid",
        )

    captain_member = next(member for member in config.members if member.id == config.captain)
    if captain_member.role != "captain":
        raise AppError(
            f"队长 {config.captain} 的角色必须是 captain，当前为 {captain_member.role}",
            status_code=500,
            code="team_config_invalid",
        )

    members: dict[str, BaseAgent] = {}
    for member in config.members:
        members[member.id] = create_agent(
            llm,
            member.role,
            agent_id=member.id,
            name=member.name,
        )

    return Team(
        id=config.id,
        name=config.name,
        description=config.description,
        captain=members[config.captain],
        members=members,
        source=path,
    )
