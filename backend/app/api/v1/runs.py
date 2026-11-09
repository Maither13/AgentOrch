"""任务调度接口：依赖校验、创建运行、查询运行状态。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query, Response

from app.agents.registry import Team
from app.api.deps import get_run_store, get_team
from app.api.schemas import RunCreate, RunSummary, ValidateResponse
from app.orchestration.models import RunState, RunStatus, TaskState, TaskStatus
from app.orchestration.scheduler import execute_run, validate_task_list
from app.orchestration.store import RunStore

router = APIRouter(tags=["runs"])


def _summary(run: RunState) -> RunSummary:
    return RunSummary(
        id=run.id,
        status=run.status,
        goal=run.goal,
        total=len(run.tasks),
        completed=run.count(TaskStatus.completed),
        failed=run.count(TaskStatus.failed),
        skipped=run.count(TaskStatus.skipped),
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


@router.post("/runs/validate", response_model=ValidateResponse, summary="只做依赖检查，不执行")
async def validate_run(payload: RunCreate, team: Team = Depends(get_team)) -> ValidateResponse:
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
    ordered = validate_task_list(payload.tasks, set(team.members))
    run = RunState(
        id=store.new_id(),
        status=RunStatus.pending,
        goal=payload.goal,
        tasks=[TaskState(spec=task) for task in ordered],
    )
    store.add(run)

    execution = asyncio.create_task(execute_run(run, team))
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
