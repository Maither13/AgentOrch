"""队长规划：把一句需求变成可执行的 TaskSpec 列表。

队长输出是自然语言 + ```json 代码块，这里负责：
1. 从输出里提取 JSON（兼容带围栏和不带围栏两种写法）；
2. 按 TaskSpec 校验每个任务；
3. 交给调度器做依赖检查与拓扑排序。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from pydantic import ValidationError

from app.agents.registry import Team
from app.core.errors import AppError
from app.llm.client import Usage
from app.orchestration.models import TaskSpec
from app.orchestration.scheduler import validate_task_list

_FENCED_BLOCK = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


@dataclass(slots=True)
class PlannedTasks:
    tasks: list[TaskSpec]
    order: list[str]
    raw: str
    mode: str
    latency_ms: int
    usage: Usage


def parse_task_plan(text: str) -> list[TaskSpec]:
    """从队长输出中提取并校验任务列表。"""
    candidates = [block.strip() for block in _FENCED_BLOCK.findall(text) if block.strip()]

    # 兜底：没有围栏时，取第一个 { 到最后一个 } 之间
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("tasks"), list):
            continue

        tasks: list[TaskSpec] = []
        for index, item in enumerate(payload["tasks"], start=1):
            try:
                tasks.append(TaskSpec.model_validate(item))
            except ValidationError as exc:
                first = exc.errors()[0]
                location = ".".join(str(part) for part in first["loc"])
                raise AppError(
                    f"队长输出中第 {index} 个任务字段不合法：{location} {first['msg']}",
                    status_code=422,
                    code="plan_invalid_task",
                ) from exc

        if not tasks:
            raise AppError("队长没有拆出任何任务", status_code=422, code="plan_empty")
        return tasks

    raise AppError(
        "无法从队长输出中解析任务列表（没有找到合法的 tasks JSON）",
        status_code=422,
        code="plan_parse_failed",
    )


async def plan_tasks(team: Team, goal: str, *, context: str | None = None) -> PlannedTasks:
    """调用队长拆解任务，并完成依赖校验。"""
    goal = (goal or "").strip()
    if not goal:
        raise AppError("goal 不能为空", status_code=400, code="empty_goal")

    started = time.perf_counter()
    result = await team.captain.run(goal, context=context)
    planning_ms = int((time.perf_counter() - started) * 1000)

    tasks = parse_task_plan(result.content)
    ordered = validate_task_list(tasks, set(team.members))
    return PlannedTasks(
        tasks=ordered,
        order=[task.id for task in ordered],
        raw=result.content,
        mode=result.mode,
        latency_ms=planning_ms,
        usage=result.usage,
    )
