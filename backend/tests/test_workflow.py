"""固定工作流：模板校验、拓扑分层、并行执行。"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.agents.base import AgentRunResult
from app.agents.registry import Team
from app.core.errors import AppError
from app.llm.client import Usage
from app.orchestration.models import RunState, TaskSpec, TaskState, TaskStatus
from app.orchestration.scheduler import execute_run
from app.orchestration.workflow import (
    SOFTWARE_DEVELOPMENT,
    WorkflowStep,
    WorkflowTemplate,
    build_task_specs,
    topological_layers,
    validate_workflow,
)
from app.orchestration.workspace import Workspace


# --------------------------------------------------------------------------- #
# 模板与拓扑
# --------------------------------------------------------------------------- #
def test_software_workflow_layers():
    layers = topological_layers(SOFTWARE_DEVELOPMENT.steps)
    assert layers == [
        ["需求分析"],
        ["技术设计"],
        ["接口实现", "测试设计"],
        ["测试执行"],
        ["代码评审"],
        ["交付汇总"],
    ]


def test_build_task_specs():
    tasks = build_task_specs(SOFTWARE_DEVELOPMENT, "做一个学生成绩管理系统")
    assert [task.id for task in tasks] == [f"S{i}" for i in range(1, 8)]
    assert [task.owner for task in tasks] == [
        "product_manager",
        "architect",
        "developer",
        "tester",
        "tester",
        "reviewer",
        "captain",
    ]
    by_id = {task.id: task for task in tasks}
    assert by_id["S2"].depends_on == ["S1"]
    assert by_id["S3"].depends_on == ["S2"]
    assert by_id["S4"].depends_on == ["S2"]
    assert by_id["S5"].depends_on == ["S3", "S4"]
    assert "学生成绩管理系统" in by_id["S1"].goal


def test_cycle_rejected():
    template = WorkflowTemplate(
        id="bad",
        name="环",
        steps=[
            WorkflowStep(step_name="A", agent="developer", depends_on=["B"]),
            WorkflowStep(step_name="B", agent="developer", depends_on=["A"]),
        ],
    )
    with pytest.raises(AppError) as exc:
        validate_workflow(template)
    assert exc.value.code == "workflow_cycle"


def test_unknown_agent_rejected():
    template = WorkflowTemplate(
        id="bad",
        name="未知角色",
        steps=[WorkflowStep(step_name="A", agent="wizard")],
    )
    with pytest.raises(AppError) as exc:
        validate_workflow(template)
    assert exc.value.code == "workflow_invalid"


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_list_and_detail(client):
    items = client.get("/api/v1/workflows").json()
    assert len(items) == 1
    workflow = items[0]
    assert workflow["id"] == "software_development"
    assert workflow["layers"][2] == ["接口实现", "测试设计"]

    detail = client.get("/api/v1/workflows/software_development").json()
    assert len(detail["steps"]) == 7

    missing = client.get("/api/v1/workflows/nope")
    assert missing.status_code == 404


def test_run_workflow_mock(client):
    resp = client.post(
        "/api/v1/workflows/software_development/runs?wait=true",
        json={"goal": "做一个学生成绩管理系统"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow"] == "software_development"
    assert body["plan_source"] == "workflow"
    assert body["status"] == "completed"
    assert len(body["tasks"]) == 7
    assert all(task["status"] == "completed" for task in body["tasks"])
    # mock 模式也返回验收结论和工具留痕
    assert body["acceptance"]["status"] == "passed"
    tester_task = next(task for task in body["tasks"] if task["spec"]["owner"] == "tester")
    assert tester_task["test_result"]["exit_code"] == 0
    assert tester_task["tool_calls"]


# --------------------------------------------------------------------------- #
# 并行执行
# --------------------------------------------------------------------------- #
class SlowAgent:
    def __init__(self, delay: float = 0.15) -> None:
        self.delay = delay
        self.starts: list[float] = []
        self.ends: list[float] = []

    async def run(self, task, *, context=None, temperature=None, max_tokens=None, workspace=None):
        self.starts.append(time.perf_counter())
        await asyncio.sleep(self.delay)
        self.ends.append(time.perf_counter())
        return AgentRunResult(
            agent_id="slow",
            role="developer",
            display_name="慢 Agent",
            model="fake",
            content="ok",
            usage=Usage(1, 1, 2),
            latency_ms=int(self.delay * 1000),
            mode="mock",
            allowed_tools=(),
        )


class WritingAgent:
    async def run(self, task, *, context=None, temperature=None, max_tokens=None, workspace=None):
        path = task.strip()
        return AgentRunResult(
            agent_id="writer",
            role="developer",
            display_name="写文件 Agent",
            model="fake",
            content=f"wrote {path}",
            usage=Usage(1, 1, 2),
            latency_ms=1,
            mode="mock",
            allowed_tools=(),
            tool_calls=[
                {
                    "name": "file_write",
                    "arguments": {"path": path, "content": "x"},
                    "result": {"path": path, "size": 1},
                }
            ],
        )


@pytest.mark.asyncio
async def test_parallel_tasks_only_claim_their_own_files(tmp_path):
    agent = WritingAgent()
    team = Team(
        id="t", name="t", description="", captain=agent,
        members={"developer": agent}, source=tmp_path / "team.json",
    )
    run = RunState(
        id="run-files",
        tasks=[
            TaskState(spec=TaskSpec(id="A", title="A", goal="a.py", owner="developer")),
            TaskState(spec=TaskSpec(id="B", title="B", goal="b.py", owner="developer")),
        ],
    )

    await execute_run(run, team, workspace=Workspace(tmp_path), parallel=True, max_parallel=2)

    files = {task.spec.id: task.files for task in run.tasks}
    assert files == {"A": ["a.py"], "B": ["b.py"]}


@pytest.mark.asyncio
async def test_independent_tasks_run_in_parallel(tmp_path):
    agent = SlowAgent(delay=0.15)
    team = Team(
        id="t",
        name="t",
        description="",
        captain=agent,
        members={"developer": agent},
        source=tmp_path / "team.json",
    )
    run = RunState(
        id="run-parallel",
        tasks=[
            TaskState(spec=TaskSpec(id="A", title="A", goal="a", owner="developer")),
            TaskState(spec=TaskSpec(id="B", title="B", goal="b", owner="developer")),
        ],
    )

    started = time.perf_counter()
    await execute_run(run, team, workspace=Workspace(tmp_path), parallel=True, max_parallel=2)
    elapsed = time.perf_counter() - started

    assert all(task.status is TaskStatus.completed for task in run.tasks)
    assert len(agent.starts) == 2
    # 两个任务几乎同时开始，总耗时接近单个任务的耗时
    assert abs(agent.starts[0] - agent.starts[1]) < 0.1
    assert elapsed < 0.28


@pytest.mark.asyncio
async def test_dependency_is_a_layer_barrier(tmp_path):
    agent = SlowAgent(delay=0.05)
    team = Team(
        id="t",
        name="t",
        description="",
        captain=agent,
        members={"developer": agent},
        source=tmp_path / "team.json",
    )
    run = RunState(
        id="run-layers",
        tasks=[
            TaskState(spec=TaskSpec(id="A", title="A", goal="a", owner="developer")),
            TaskState(spec=TaskSpec(id="B", title="B", goal="b", owner="developer")),
            TaskState(spec=TaskSpec(id="C", title="C", goal="c", owner="developer", depends_on=["A"])),
        ],
    )

    await execute_run(run, team, workspace=Workspace(tmp_path), parallel=True, max_parallel=3)

    # A 与 B 并行，C 必须等 A 结束才开始
    assert agent.starts[1] < agent.ends[0] or agent.starts[0] < agent.ends[1]
    c_state = next(task for task in run.tasks if task.spec.id == "C")
    assert c_state.started_at >= max(
        task.finished_at for task in run.tasks if task.spec.id == "A"
    )
