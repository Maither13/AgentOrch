"""任务与运行状态模型。

这一版只支持顺序执行：任务按拓扑序一个一个跑，不并行、不重试、不持久化。
状态字段预留了并行调度需要的结构（依赖、时间、用量），后续升级不用改表。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


TERMINAL_TASK_STATUSES = {TaskStatus.completed, TaskStatus.failed, TaskStatus.skipped}


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    # 执行完成但评审验收未通过
    rejected = "rejected"


class ExecutionStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class AcceptanceStatus(StrEnum):
    pending = "pending"
    passed = "passed"
    rejected = "rejected"


class AcceptanceState(BaseModel):
    """评审 Agent 给出的验收结论，与执行状态正交。"""

    status: AcceptanceStatus = AcceptanceStatus.pending
    verdict: str | None = None  # 通过 / 有条件通过 / 驳回
    summary: str | None = None
    blockers: list[str] = Field(default_factory=list)
    reviewer_task: str | None = None
    reviewed_at: datetime | None = None


class LogLevel(StrEnum):
    info = "info"
    warning = "warning"
    error = "error"


class LogEntry(BaseModel):
    """一条执行日志，存在内存里，跟着 RunState 一起返回。"""

    at: datetime = Field(default_factory=utcnow)
    level: LogLevel = LogLevel.info
    message: str
    task_id: str | None = None


class TaskSpec(BaseModel):
    """任务清单里的一条任务，也是调度器的输入。"""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=5_000)
    owner: str = Field(min_length=1, max_length=40)
    depends_on: list[str] = Field(default_factory=list)
    deliverable: str = Field(default="", max_length=500)


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class TaskState(BaseModel):
    spec: TaskSpec
    status: TaskStatus = TaskStatus.pending
    agent_name: str | None = None
    model: str | None = None
    mode: str | None = None
    output: str | None = None
    error: str | None = None
    # 本次任务新建或修改的工作区文件
    files: list[str] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None


class RunState(BaseModel):
    id: str
    status: RunStatus = RunStatus.pending
    # 两个正交维度：调度器看 execution_status，评审看 acceptance
    execution_status: ExecutionStatus = ExecutionStatus.pending
    acceptance: AcceptanceState = Field(default_factory=AcceptanceState)
    goal: str | None = None
    # manual：调用方直接给任务清单；captain：由队长拆解生成
    plan_source: str = "manual"
    workflow: str | None = None
    planning_ms: int | None = None
    rounds: int = 0
    needs_human: bool = False
    workspace_dir: str | None = None
    logs: list[LogEntry] = Field(default_factory=list)
    tasks: list[TaskState]
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None

    def log(
        self,
        message: str,
        *,
        level: LogLevel = LogLevel.info,
        task_id: str | None = None,
    ) -> None:
        self.logs.append(LogEntry(level=level, message=message, task_id=task_id))
        if len(self.logs) > 200:  # 内存版日志，防止无限增长
            del self.logs[:-200]

    def count(self, status: TaskStatus) -> int:
        return sum(1 for task in self.tasks if task.status is status)
