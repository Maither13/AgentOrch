"""API 请求 / 响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.orchestration.models import RunStatus, TaskSpec
from app.orchestration.workflow import WorkflowStep

Role = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: Role = "user"
    content: str = Field(min_length=1, max_length=200_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, description="默认取 settings.deepseek_model")
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32_768)
    json_mode: bool = False
    stream: bool = False


class UsageOut(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    id: str
    model: str
    content: str
    reasoning_content: str | None = None
    finish_reason: str | None = None
    usage: UsageOut = Field(default_factory=UsageOut)
    latency_ms: int
    mode: str


class PingResponse(BaseModel):
    ok: bool
    reply: str
    model: str
    mode: str
    latency_ms: int
    usage: UsageOut


class ModelInfo(BaseModel):
    id: str
    label: str
    description: str
    supports_reasoning: bool = False


class LLMStatus(BaseModel):
    provider: str
    model: str
    base_url: str
    mode: str
    configured: bool


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    llm: LLMStatus


# --------------------------------------------------------------------------- #
# Agent / 团队
# --------------------------------------------------------------------------- #
class ToolOut(BaseModel):
    name: str
    display_name: str
    description: str


class AgentSpecOut(BaseModel):
    id: str
    role: str
    display_name: str
    description: str
    system_prompt: str
    allowed_tools: list[ToolOut]
    model: str | None = None
    temperature: float


class RoleOut(BaseModel):
    role: str
    display_name: str
    description: str
    allowed_tools: list[ToolOut]
    temperature: float


class TeamOut(BaseModel):
    id: str
    name: str
    description: str
    captain: str
    members: list[AgentSpecOut]
    source: str


class AgentRunRequest(BaseModel):
    task: str = Field(min_length=1, max_length=50_000)
    context: str | None = Field(default=None, max_length=200_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32_768)


class AgentRunResponse(BaseModel):
    agent_id: str
    role: str
    display_name: str
    content: str
    model: str
    mode: str
    usage: UsageOut
    latency_ms: int
    allowed_tools: list[str]


# --------------------------------------------------------------------------- #
# 任务调度
# --------------------------------------------------------------------------- #
class RunCreate(BaseModel):
    """tasks 与 goal 至少给一个：给 tasks 直接执行，只给 goal 由队长先拆解。"""

    goal: str | None = Field(default=None, max_length=2_000)
    tasks: list[TaskSpec] | None = Field(default=None, min_length=1, max_length=20)
    max_repair_rounds: int = Field(default=3, ge=0, le=5, description="验收/测试失败后的最大修复轮次")

    @model_validator(mode="after")
    def _require_input(self) -> "RunCreate":
        if not self.tasks and not (self.goal and self.goal.strip()):
            raise ValueError("tasks 与 goal 至少提供一个")
        return self


class PlanRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2_000)
    context: str | None = Field(default=None, max_length=20_000)


class PlanResponse(BaseModel):
    tasks: list[TaskSpec]
    order: list[str]
    raw: str
    mode: str
    latency_ms: int
    usage: UsageOut


class ValidateResponse(BaseModel):
    valid: bool = True
    order: list[str]
    tasks: list[TaskSpec]


class TaskListRequest(BaseModel):
    tasks: list[TaskSpec] = Field(min_length=1, max_length=20)


class RunSummary(BaseModel):
    id: str
    status: RunStatus
    acceptance_status: str = "pending"
    rounds: int = 0
    goal: str | None = None
    plan_source: str = "manual"
    workflow: str | None = None
    total: int
    completed: int
    failed: int
    skipped: int
    created_at: datetime
    finished_at: datetime | None = None


# --------------------------------------------------------------------------- #
# 工作流
# --------------------------------------------------------------------------- #
class WorkflowOut(BaseModel):
    id: str
    name: str
    description: str = ""
    steps: list[WorkflowStep]
    layers: list[list[str]]


class WorkflowRunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2_000)
    max_repair_rounds: int = Field(default=3, ge=0, le=5)
    max_parallel: int = Field(default=3, ge=1, le=5)
