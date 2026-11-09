"""任务调度器：依赖校验 + 顺序执行。

执行模型：
1. 先把任务列表校验成一张合法 DAG（id 唯一、负责人存在、依赖存在、无环）；
2. 按拓扑序逐个执行；某任务失败时，它的下游全部标记 skipped，无关任务继续执行；
3. 每个任务通过队长/成员 Agent 的 `run()` 调用模型，上游产出作为 context 注入。

这一版是单线程顺序执行，故意不引入并发、重试与持久化——先把状态机跑对。
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from app.agents.registry import Team
from app.core.errors import AppError
from app.orchestration.models import (
    RunState,
    RunStatus,
    TaskSpec,
    TaskState,
    TaskStatus,
    TokenUsage,
    utcnow,
)

logger = logging.getLogger(__name__)

MAX_TASKS = 20
# 单个上游产物和总上下文的上限，避免 prompt 爆炸。
# 代码类产出动辄上万字，上限给得比文档场景宽；真正解耦要靠工具读写文件，而不是靠拼 prompt。
MAX_DEP_CONTEXT_CHARS = 30_000
MAX_TOTAL_CONTEXT_CHARS = 80_000


# --------------------------------------------------------------------------- #
# 依赖检查
# --------------------------------------------------------------------------- #
def validate_task_list(tasks: list[TaskSpec], member_ids: set[str]) -> list[TaskSpec]:
    """校验任务列表并返回拓扑排序后的顺序（同层保持输入顺序）。"""
    if not tasks:
        raise AppError("任务列表不能为空", status_code=400, code="task_list_empty")
    if len(tasks) > MAX_TASKS:
        raise AppError(
            f"任务数量超过上限 {MAX_TASKS}",
            status_code=400,
            code="task_too_many",
        )

    ids = [task.id for task in tasks]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise AppError(f"任务 id 重复：{duplicates}", status_code=400, code="task_duplicate_id")

    by_id = {task.id: task for task in tasks}

    for task in tasks:
        if task.owner not in member_ids:
            raise AppError(
                f"任务 {task.id} 的负责人不存在：{task.owner}",
                status_code=400,
                code="task_unknown_owner",
            )
        if len(set(task.depends_on)) != len(task.depends_on):
            raise AppError(
                f"任务 {task.id} 的依赖重复声明",
                status_code=400,
                code="task_duplicate_dependency",
            )
        for dependency in task.depends_on:
            if dependency == task.id:
                raise AppError(
                    f"任务 {task.id} 不能依赖自己",
                    status_code=400,
                    code="task_self_dependency",
                )
            if dependency not in by_id:
                raise AppError(
                    f"任务 {task.id} 依赖了不存在的任务：{dependency}",
                    status_code=400,
                    code="task_unknown_dependency",
                )

    # Kahn 拓扑排序
    indegree = {task.id: len(task.depends_on) for task in tasks}
    children: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        for dependency in task.depends_on:
            children[dependency].append(task.id)

    ready = [task.id for task in tasks if indegree[task.id] == 0]
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)

    if len(order) != len(tasks):
        cycle_nodes = [task_id for task_id in ids if task_id not in order]
        raise AppError(
            f"任务依赖存在环：{cycle_nodes}",
            status_code=400,
            code="task_cycle",
        )

    return [by_id[task_id] for task_id in order]


# --------------------------------------------------------------------------- #
# 执行
# --------------------------------------------------------------------------- #
async def execute_run(run: RunState, team: Team) -> None:
    """按顺序执行整个任务列表。异常兜底，保证 run 一定落到终态。"""
    run.status = RunStatus.running
    run.started_at = utcnow()
    by_id = {state.spec.id: state for state in run.tasks}

    try:
        for state in run.tasks:  # 已在创建时按拓扑序排列
            if state.status is not TaskStatus.pending:
                continue
            dependencies = [by_id[item] for item in state.spec.depends_on]
            unfinished = [dep.spec.id for dep in dependencies if dep.status is not TaskStatus.completed]
            if unfinished:
                # 上游失败/跳过，下游不再执行
                state.status = TaskStatus.skipped
                state.error = f"上游任务未成功：{', '.join(unfinished)}"
                state.finished_at = utcnow()
                logger.warning("跳过任务 %s（%s）", state.spec.id, state.error)
                continue
            await _execute_task(state, dependencies, team)
    except Exception as exc:  # noqa: BLE001 —— 后台任务不能静默死掉
        logger.exception("调度器执行异常")
        run.error = f"调度器异常：{exc}"
    finally:
        run.finished_at = utcnow()
        if not run.error:
            run.status = (
                RunStatus.failed
                if any(state.status is TaskStatus.failed for state in run.tasks)
                else RunStatus.completed
            )
        else:
            run.status = RunStatus.failed


async def _execute_task(state: TaskState, dependencies: list[TaskState], team: Team) -> None:
    agent = team.members.get(state.spec.owner)
    if agent is None:  # 校验阶段已挡住，这里只做兜底
        state.status = TaskStatus.failed
        state.error = f"负责人不存在：{state.spec.owner}"
        state.finished_at = utcnow()
        return

    state.status = TaskStatus.running
    state.started_at = utcnow()
    started = time.perf_counter()
    context = build_context(dependencies)

    try:
        result = await agent.run(state.spec.goal, context=context or None)
    except AppError as exc:
        state.status = TaskStatus.failed
        state.error = f"[{exc.code}] {exc.message}"
        logger.warning("任务 %s 失败：%s", state.spec.id, state.error)
    except Exception as exc:  # noqa: BLE001
        state.status = TaskStatus.failed
        state.error = f"{type(exc).__name__}: {exc}"
        logger.exception("任务 %s 出现未预期异常", state.spec.id)
    else:
        state.status = TaskStatus.completed
        state.output = result.content
        state.agent_name = result.display_name
        state.model = result.model
        state.mode = result.mode
        state.usage = TokenUsage(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        )
    finally:
        state.finished_at = utcnow()
        state.duration_ms = int((time.perf_counter() - started) * 1000)


def build_context(dependencies: list[TaskState]) -> str:
    """把上游任务的产出拼成 context，单条和总量都做截断。"""
    parts: list[str] = []
    total = 0
    for dep in dependencies:
        if not dep.output:
            continue
        text = dep.output.strip()
        original = len(text)
        if original > MAX_DEP_CONTEXT_CHARS:
            text = (
                text[:MAX_DEP_CONTEXT_CHARS]
                + f"\n…（内容过长，已从 {original} 字截断；如需完整内容请向队长申请拆分任务）"
            )
        block = f"### {dep.spec.id} {dep.spec.title}（{dep.spec.owner}）\n{text}"
        if total + len(block) > MAX_TOTAL_CONTEXT_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)
