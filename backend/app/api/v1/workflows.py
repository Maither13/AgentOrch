"""固定工作流：模板查询与按模板发起运行。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query, Response

from app.agents.registry import Team
from app.api.deps import get_run_store, get_team
from app.api.schemas import WorkflowOut, WorkflowRunRequest
from app.core.errors import AppError
from app.orchestration.models import RunState, RunStatus, TaskState
from app.orchestration.scheduler import execute_run
from app.orchestration.store import RunStore
from app.orchestration.workflow import WORKFLOWS, WorkflowTemplate, build_task_specs, topological_layers
from app.orchestration.workspace import Workspace

router = APIRouter(tags=["workflows"])


def _workflow_out(template: WorkflowTemplate) -> WorkflowOut:
    return WorkflowOut(
        id=template.id,
        name=template.name,
        description=template.description,
        steps=template.steps,
        layers=topological_layers(template.steps),
    )


def _get_template(workflow_id: str) -> WorkflowTemplate:
    template = WORKFLOWS.get(workflow_id)
    if template is None:
        raise AppError(f"工作流不存在：{workflow_id}", status_code=404, code="workflow_not_found")
    return template


@router.get("/workflows", response_model=list[WorkflowOut], summary="内置工作流模板")
async def list_workflows() -> list[WorkflowOut]:
    return [_workflow_out(template) for template in WORKFLOWS.values()]


@router.get("/workflows/{workflow_id}", response_model=WorkflowOut, summary="工作流模板详情")
async def get_workflow(workflow_id: str) -> WorkflowOut:
    return _workflow_out(_get_template(workflow_id))


@router.post(
    "/workflows/{workflow_id}/runs",
    response_model=RunState,
    status_code=202,
    summary="按固定模板发起运行（分层并行）",
)
async def run_workflow(
    workflow_id: str,
    payload: WorkflowRunRequest,
    response: Response,
    wait: bool = Query(default=False, description="true 时等执行结束再返回"),
    team: Team = Depends(get_team),
    store: RunStore = Depends(get_run_store),
) -> RunState:
    template = _get_template(workflow_id)
    missing = sorted({step.agent for step in template.steps} - set(team.members))
    if missing:
        raise AppError(
            f"当前团队缺少工作流所需成员：{missing}",
            status_code=400,
            code="workflow_member_missing",
        )

    tasks = build_task_specs(template, payload.goal)
    run = RunState(
        id=store.new_id(),
        status=RunStatus.pending,
        goal=payload.goal,
        plan_source="workflow",
        workflow=template.id,
        tasks=[TaskState(spec=task) for task in tasks],
    )
    store.add(run)

    workspace = Workspace.for_run(run.id)
    execution = asyncio.create_task(
        execute_run(
            run,
            team,
            workspace=workspace,
            max_rounds=payload.max_repair_rounds,
            parallel=True,
            max_parallel=payload.max_parallel,
        )
    )
    store.track(execution)

    if wait:
        await execution
        response.status_code = 200
    return run
