"""API 请求 / 响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
