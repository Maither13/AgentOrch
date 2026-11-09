"""任务调度接口：队长拆解、依赖校验、创建运行、查询运行状态。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query, Response

from app.agents.registry import Team
from app.api.deps import get_run_store, get_team
from app.api.schemas import (
    PlanRequest,
    PlanResponse,
    RunCreate,
    RunSummary,
    TaskListRequest,
    UsageOut,
    ValidateResponse,
)
from app.orchestration.models import RunState, RunStatus, TaskState, TaskStatus
from app.orchestration.planner import plan_tasks
from app.orchestration.scheduler import execute_run, validate_task_list
from app.orchestration.store import RunStore
from app.orchestration.workspace import Workspace

router = APIRouter(tags=["runs"])


def _summary(run: RunState) -> RunSummary:
    return RunSummary(
        id=run.id,
        status=run.status,
        acceptance_status=run.acceptance.status.value,
        rounds=run.rounds,
        goal=run.goal,
        plan_source=run.plan_source,
        workflow=run.workflow,
        total=len(run.tasks),
        completed=run.count(TaskStatus.completed),
        failed=run.count(TaskStatus.failed),
        skipped=run.count(TaskStatus.skipped),
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


@router.post("/runs/plan", response_model=PlanResponse, summary="只让队长拆解任务，不执行")
async def plan_run(payload: PlanRequest, team: Team = Depends(get_team)) -> PlanResponse:
    plan = await plan_tasks(team, payload.goal, context=payload.context)
    return PlanResponse(
        tasks=plan.tasks,
        order=plan.order,
        raw=plan.raw,
        mode=plan.mode,
        latency_ms=plan.latency_ms,
        usage=UsageOut(
            prompt_tokens=plan.usage.prompt_tokens,
            completion_tokens=plan.usage.completion_tokens,
            total_tokens=plan.usage.total_tokens,
        ),
    )


@router.post("/runs/validate", response_model=ValidateResponse, summary="只做依赖检查，不执行")
async def validate_run(payload: TaskListRequest, team: Team = Depends(get_team)) -> ValidateResponse:
    ordered = validate_task_list(payload.tasks, set(team.members))
    return ValidateResponse(order=[task.id for task in ordered], tasks=ordered)


@router.post("/runs", response_model=RunState, status_code=202, summary="创建并执行一次运行")
async def create_run(
    payload: RunCreate,
    response: Response,
    wait: bool = Query(default=False, description="true 时等执行结束再返回"),
    team: Team = Depends(get_team),
    store: RunStore = Depends(get_run_store),
) -> RunState:
    # 只给 goal 时，先让队长拆解；拆解失败直接 4xx，不会创建空 run
    if payload.tasks:
        tasks = payload.tasks
        plan_source = "manual"
        planning_ms = None
    else:
        plan = await plan_tasks(team, payload.goal or "")
        tasks = plan.tasks
        plan_source = "captain"
        planning_ms = plan.latency_ms

    ordered = validate_task_list(tasks, set(team.members))
    run = RunState(
        id=store.new_id(),
        status=RunStatus.pending,
        goal=payload.goal,
        plan_source=plan_source,
        planning_ms=planning_ms,
        tasks=[TaskState(spec=task) for task in ordered],
    )
    store.add(run)

    workspace = Workspace.for_run(run.id)
    execution = asyncio.create_task(
        execute_run(
            run,
            team,
            workspace=workspace,
            max_rounds=payload.max_repair_rounds,
        )
    )
    store.track(execution)

    if wait:
        await execution
        response.status_code = 200
    return run


@router.get("/runs", response_model=list[RunSummary], summary="最近运行列表")
async def list_runs(
    limit: int = Query(default=20, ge=1, le=50),
    store: RunStore = Depends(get_run_store),
) -> list[RunSummary]:
    return [_summary(run) for run in store.list(limit)]


@router.get("/runs/{run_id}", response_model=RunState, summary="运行详情（含每个任务的输出）")
async def get_run(run_id: str, store: RunStore = Depends(get_run_store)) -> RunState:
    return store.get(run_id)
