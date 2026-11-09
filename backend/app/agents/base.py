"""Agent 基类。

每个 Agent = 一段系统提示词 + 一组写死的工具权限 + 调用大模型。
子类只需声明类属性，不写任何调度逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Iterable

from app.agents.tools import (
    TOOL_REGISTRY,
    ToolPermissionError,
    ToolSpec,
    tool_infos,
)
from app.core.errors import AppError
from app.llm.client import DeepSeekClient, Usage


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Agent 的对外描述（不含运行状态）。"""

    id: str
    role: str
    display_name: str
    description: str
    system_prompt: str
    allowed_tools: tuple[ToolSpec, ...]
    model: str | None
    temperature: float


@dataclass(slots=True)
class AgentRunResult:
    agent_id: str
    role: str
    display_name: str
    model: str
    content: str
    usage: Usage
    latency_ms: int
    mode: str
    allowed_tools: tuple[str, ...]


class BaseAgent:
    """所有内置 Agent 的基类。

    子类必须声明：role / display_name / description / system_prompt / allowed_tools。
    声明错误会在 import 阶段直接抛错，避免带病上线。
    """

    role: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    system_prompt: ClassVar[str] = ""
    allowed_tools: ClassVar[tuple[str, ...]] = ()
    temperature: ClassVar[float] = 0.7
    model: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        for attr in ("role", "display_name", "description", "system_prompt"):
            value = getattr(cls, attr, "")
            if not isinstance(value, str) or not value.strip():
                raise TypeError(f"{cls.__name__} 缺少必填属性 {attr}")
        if not cls.allowed_tools:
            raise TypeError(f"{cls.__name__} 至少需要绑定一个工具")
        unknown = [name for name in cls.allowed_tools if name not in TOOL_REGISTRY]
        if unknown:
            raise TypeError(f"{cls.__name__} 声明了未注册的工具：{unknown}")
        if not 0 <= cls.temperature <= 2:
            raise TypeError(f"{cls.__name__} 的 temperature 必须在 0~2 之间")

    def __init__(
        self,
        llm: DeepSeekClient,
        *,
        agent_id: str | None = None,
        name: str | None = None,
    ) -> None:
        self.llm = llm
        self.id = agent_id or self.role
        self.name = name or self.display_name

    # ---------------- 描述信息 ----------------
    @property
    def spec(self) -> AgentSpec:
        return AgentSpec(
            id=self.id,
            role=self.role,
            display_name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            allowed_tools=tool_infos(self.allowed_tools),
            model=self.model,
            temperature=self.temperature,
        )

    def can_use(self, tool: str) -> bool:
        return tool in self.allowed_tools

    def ensure_tools(self, tools: Iterable[str]) -> None:
        """工具准入校验，后续工具执行层调用。"""
        denied = [name for name in tools if name not in self.allowed_tools]
        if denied:
            raise ToolPermissionError(self.id, denied)

    # ---------------- 执行 ----------------
    async def run(
        self,
        task: str,
        *,
        context: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AgentRunResult:
        task = (task or "").strip()
        if not task:
            raise AppError("任务内容不能为空", status_code=400, code="empty_task")

        result = await self.llm.chat(
            [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self._compose_user_message(task, context)},
            ],
            model=self.model,
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=max_tokens,
        )
        return AgentRunResult(
            agent_id=self.id,
            role=self.role,
            display_name=self.name,
            model=result.model,
            content=result.content,
            usage=result.usage,
            latency_ms=result.latency_ms,
            mode=result.mode,
            allowed_tools=self.allowed_tools,
        )

    @staticmethod
    def _compose_user_message(task: str, context: str | None) -> str:
        if not context or not context.strip():
            return task
        return f"## 上游背景与产物\n{context.strip()}\n\n## 你的任务\n{task}"

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<{type(self).__name__} id={self.id}>"
