"""任务调度器：依赖校验 + 顺序执行 + 验收 + Self-Loop。

执行模型：
1. 先把任务列表校验成一张合法 DAG（id 唯一、负责人存在、依赖存在、无环）；
2. 按拓扑序逐个执行；某任务失败时，它的下游全部标记 skipped，无关任务继续执行；
3. 代码与产出落盘到运行工作区，下游只拿清单，通过文件工具按需读取；
4. 执行结束后由评审 Agent 给验收结论；驳回则追加「修复 + 复评」任务并重跑。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from app.agents.registry import Team
from app.core.errors import AppError
from app.orchestration.acceptance import apply_test_gate, evaluate_acceptance
from app.orchestration.models import (
    AcceptanceStatus,
    ExecutionStatus,
    LogLevel,
    RunState,
    RunStatus,
    TaskSpec,
    TaskState,
    TaskStatus,
    TestResult,
    TokenUsage,
    utcnow,
)
from app.orchestration.self_loop import append_repair_tasks
from app.orchestration.workspace import Workspace

logger = logging.getLogger(__name__)

MAX_TASKS = 20


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
async def execute_run(
    run: RunState,
    team: Team,
    *,
    workspace: Workspace | None = None,
    max_rounds: int = 0,
    parallel: bool = False,
    max_parallel: int = 3,
) -> None:
    """执行任务列表，并在验收驳回时进入 Self-Loop。异常兜底，保证落到终态。"""
    workspace = workspace or Workspace.for_run(run.id)
    run.workspace_dir = str(workspace.root)
    run.execution_status = ExecutionStatus.running
    run.status = RunStatus.running
    run.started_at = utcnow()
    run.log(
        f"运行开始：{len(run.tasks)} 个任务，{'并行' if parallel else '顺序'}执行，最多 {max_rounds} 轮修复"
    )

    try:
        if parallel:
            await execute_layers(run, team, workspace, max_parallel=max_parallel)
        else:
            await execute_pending(run, team, workspace)
        evaluate_acceptance(run)
        apply_test_gate(run)
        run.log(f"验收结论：{run.acceptance.verdict or '未给出'}（{run.acceptance.status.value}）")

        round_no = 0
        while run.acceptance.status is AcceptanceStatus.rejected and round_no < max_rounds:
            round_no += 1
            appended = append_repair_tasks(run, round_no)
            run.rounds = round_no
            run.log(
                f"Self-Loop 第 {round_no} 轮：追加 {len(appended)} 个任务"
                f"（{', '.join(state.spec.id for state in appended)}）"
            )
            logger.info(
                "Self-Loop: 第 %d 轮修复，追加 %d 个任务（%s）",
                round_no,
                len(appended),
                ", ".join(state.spec.id for state in appended),
            )
            # 修复链本身是串行的：修复 → 重测 → 复评
            await execute_pending(run, team, workspace)
            evaluate_acceptance(run)
            apply_test_gate(run)
            run.log(f"第 {round_no} 轮复评：{run.acceptance.verdict or '未给出'}（{run.acceptance.status.value}）")

        if run.acceptance.status is AcceptanceStatus.rejected:
            run.needs_human = True
            run.log("修复轮次用尽仍未通过，转人工介入", level=LogLevel.warning)
            logger.warning(
                "Self-Loop 结束：%d 轮修复后仍未通过，需要人工介入", run.rounds
            )
    except Exception as exc:  # noqa: BLE001 —— 后台任务不能静默死掉
        logger.exception("调度器执行异常")
        run.error = f"调度器异常：{exc}"
        run.log(run.error, level=LogLevel.error)
    finally:
        run.finished_at = utcnow()
        failed = any(state.status is TaskStatus.failed for state in run.tasks)
        if run.error or failed:
            run.execution_status = ExecutionStatus.failed
            run.status = RunStatus.failed
        else:
            run.execution_status = ExecutionStatus.completed
            if run.acceptance.status is AcceptanceStatus.rejected:
                run.status = RunStatus.rejected
            else:
                run.status = RunStatus.completed
        run.log(f"运行结束：{run.status.value}（执行={run.execution_status.value}）")


async def execute_pending(run: RunState, team: Team, workspace: Workspace) -> None:
    """按列表顺序执行所有 pending 任务（Self-Loop 追加的任务也走这里）。"""
    by_id = {state.spec.id: state for state in run.tasks}
    for state in list(run.tasks):
        if state.status is not TaskStatus.pending:
            continue
        dependencies = [by_id[item] for item in state.spec.depends_on if item in by_id]
        unfinished = [
            dep.spec.id for dep in dependencies if dep.status is not TaskStatus.completed
        ]
        if unfinished:
            state.status = TaskStatus.skipped
            state.error = f"上游任务未成功：{', '.join(unfinished)}"
            state.finished_at = utcnow()
            run.log(f"跳过任务 {state.spec.id}：{state.error}", level=LogLevel.warning, task_id=state.spec.id)
            logger.warning("跳过任务 %s（%s）", state.spec.id, state.error)
            continue
        await _execute_task(run, state, dependencies, team, workspace)


async def execute_layers(
    run: RunState,
    team: Team,
    workspace: Workspace,
    *,
    max_parallel: int = 3,
) -> None:
    """分层并行：每一波只执行依赖已全部完成的任务，层内用 asyncio.gather 并发。"""
    by_id = {state.spec.id: state for state in run.tasks}
    semaphore = asyncio.Semaphore(max(1, max_parallel))

    while True:
        pending = [state for state in run.tasks if state.status is TaskStatus.pending]
        if not pending:
            return

        ready: list[TaskState] = []
        skipped_any = False
        for state in pending:
            dependencies = [by_id[item] for item in state.spec.depends_on if item in by_id]
            failed_deps = [
                dep.spec.id
                for dep in dependencies
                if dep.status in {TaskStatus.failed, TaskStatus.skipped}
            ]
            if failed_deps:
                state.status = TaskStatus.skipped
                state.error = f"上游任务未成功：{', '.join(failed_deps)}"
                state.finished_at = utcnow()
                run.log(f"跳过任务 {state.spec.id}：{state.error}", level=LogLevel.warning, task_id=state.spec.id)
                logger.warning("跳过任务 %s（%s）", state.spec.id, state.error)
                skipped_any = True
                continue
            if all(dep.status is TaskStatus.completed for dep in dependencies):
                ready.append(state)

        if not ready:
            if skipped_any:
                continue
            logger.error("分层执行卡住：没有就绪任务，剩余 %d 个", len(pending))
            return

        logger.info(
            "并行层启动：%d 个任务（%s）",
            len(ready),
            ", ".join(state.spec.id for state in ready),
        )
        run.log(
            "并行层启动："
            + "、".join(state.spec.id for state in ready)
            + f"（共 {len(ready)} 个任务）"
        )

        async def run_one(state: TaskState) -> None:
            async with semaphore:
                dependencies = [by_id[item] for item in state.spec.depends_on if item in by_id]
                await _execute_task(run, state, dependencies, team, workspace)

        await asyncio.gather(*(run_one(state) for state in ready))


async def _execute_task(
    run: RunState,
    state: TaskState,
    dependencies: list[TaskState],
    team: Team,
    workspace: Workspace,
) -> None:
    agent = team.members.get(state.spec.owner)
    if agent is None:  # 校验阶段已挡住，这里只做兜底
        state.status = TaskStatus.failed
        state.error = f"负责人不存在：{state.spec.owner}"
        state.finished_at = utcnow()
        run.log(state.error, level=LogLevel.error, task_id=state.spec.id)
        return

    before = {item.path: item.sha256 for item in workspace.list_files()}
    state.status = TaskStatus.running
    state.started_at = utcnow()
    started = time.perf_counter()
    context = build_context(state, dependencies, workspace)
    run.log(
        f"任务 {state.spec.id}「{state.spec.title}」开始（{state.spec.owner}，context {len(context)} 字符）",
        task_id=state.spec.id,
    )
    logger.info(
        "任务 %s 启动（owner=%s，context=%d 字符，工作区文件 %d 个）",
        state.spec.id,
        state.spec.owner,
        len(context),
        len(before),
    )

    try:
        result = await agent.run(state.spec.goal, context=context, workspace=workspace)
    except AppError as exc:
        state.status = TaskStatus.failed
        state.error = f"[{exc.code}] {exc.message}"
        run.log(f"任务 {state.spec.id} 失败：{state.error}", level=LogLevel.error, task_id=state.spec.id)
        logger.warning("任务 %s 失败：%s", state.spec.id, state.error)
    except Exception as exc:  # noqa: BLE001
        state.status = TaskStatus.failed
        state.error = f"{type(exc).__name__}: {exc}"
        run.log(f"任务 {state.spec.id} 异常：{state.error}", level=LogLevel.error, task_id=state.spec.id)
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
        # 产出全部落盘：先存完整回复，再从开发输出里兜底提取代码块
        workspace.save_artifact(state.spec.id, result.content)
        if state.spec.owner == "developer":
            workspace.write_code_blocks(result.content)
        after = {item.path: item.sha256 for item in workspace.list_files()}
        state.files = [path for path, digest in after.items() if before.get(path) != digest]
        # 记录本轮 test_runner 的真实结果，供测试门和 Self-Loop 使用
        for call in result.tool_calls:
            if call.get("name") != "test_runner" or not isinstance(call.get("result"), dict):
                continue
            raw = call["result"]
            state.test_result = TestResult(
                exit_code=int(raw.get("exit_code", -1)),
                output=str(raw.get("output", "")),
                command=str(raw.get("command", "python -m pytest -q")),
            )
    finally:
        state.finished_at = utcnow()
        state.duration_ms = int((time.perf_counter() - started) * 1000)
        if state.status is TaskStatus.completed:
            run.log(
                f"任务 {state.spec.id} 完成：{state.duration_ms}ms，"
                f"{state.usage.total_tokens} tokens，新增/修改 {len(state.files)} 个文件",
                task_id=state.spec.id,
            )
        if state.test_result is not None:
            run.log(
                f"测试结果：pytest 退出码 {state.test_result.exit_code}",
                level=LogLevel.info if state.test_result.exit_code == 0 else LogLevel.warning,
                task_id=state.spec.id,
            )


def build_context(
    state: TaskState,
    dependencies: list[TaskState],
    workspace: Workspace,
) -> str:
    """交接只给清单，不给全文——正文通过 file_read 工具按需读取。"""
    parts = ["## 工作区（代码与产出已落盘，可用文件工具读取）", workspace.manifest()]
    if dependencies:
        parts.append("## 上游任务")
        for dep in dependencies:
            parts.append(
                f"- {dep.spec.id} {dep.spec.title}（{dep.spec.owner}）"
                f"→ tasks/{dep.spec.id}.md"
            )
    return "\n".join(parts)
