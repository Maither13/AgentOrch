"""模块 2：任务列表、依赖检查与顺序执行。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.base import AgentRunResult
from app.agents.registry import Team
from app.core.errors import AppError
from app.llm.client import Usage
from app.orchestration.models import RunState, TaskSpec, TaskState, TaskStatus
from app.orchestration.scheduler import execute_run, validate_task_list
from app.orchestration.workspace import Workspace

TASKS = [
    {"id": "T1", "title": "需求规格", "goal": "写需求文档", "owner": "product_manager"},
    {"id": "T2", "title": "技术设计", "goal": "写设计文档", "owner": "architect", "depends_on": ["T1"]},
    {"id": "T3", "title": "编码实现", "goal": "实现接口", "owner": "developer", "depends_on": ["T2"]},
]


# --------------------------------------------------------------------------- #
# 依赖检查
# --------------------------------------------------------------------------- #
def test_validate_returns_topological_order(client):
    body = client.post("/api/v1/runs/validate", json={"tasks": TASKS}).json()
    assert body["valid"] is True
    assert body["order"] == ["T1", "T2", "T3"]


def test_validate_reorders_independent_tasks(client):
    tasks = [
        {"id": "B", "title": "后置", "goal": "依赖 A", "owner": "developer", "depends_on": ["A"]},
        {"id": "A", "title": "前置", "goal": "无依赖", "owner": "product_manager"},
    ]
    body = client.post("/api/v1/runs/validate", json={"tasks": tasks}).json()
    assert body["order"] == ["A", "B"]


@pytest.mark.parametrize(
    ("tasks", "code"),
    [
        (
            [
                {"id": "A", "title": "A", "goal": "a", "owner": "developer", "depends_on": ["B"]},
                {"id": "B", "title": "B", "goal": "b", "owner": "developer", "depends_on": ["A"]},
            ],
            "task_cycle",
        ),
        (
            [{"id": "A", "title": "A", "goal": "a", "owner": "nobody"}],
            "task_unknown_owner",
        ),
        (
            [{"id": "A", "title": "A", "goal": "a", "owner": "developer", "depends_on": ["X"]}],
            "task_unknown_dependency",
        ),
        (
            [
                {"id": "A", "title": "A", "goal": "a", "owner": "developer"},
                {"id": "A", "title": "A2", "goal": "a2", "owner": "developer"},
            ],
            "task_duplicate_id",
        ),
        (
            [{"id": "A", "title": "A", "goal": "a", "owner": "developer", "depends_on": ["A"]}],
            "task_self_dependency",
        ),
    ],
)
def test_validate_rejects_bad_dags(client, tasks, code):
    resp = client.post("/api/v1/runs/validate", json={"tasks": tasks})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == code


# --------------------------------------------------------------------------- #
# 顺序执行（mock 模型）
# --------------------------------------------------------------------------- #
def test_run_sequentially(client):
    resp = client.post("/api/v1/runs?wait=true", json={"goal": "做一个成绩管理系统", "tasks": TASKS})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert [task["spec"]["id"] for task in body["tasks"]] == ["T1", "T2", "T3"]
    assert all(task["status"] == "completed" for task in body["tasks"])
    assert all("MOCK" in task["output"] for task in body["tasks"])
    assert all(task["duration_ms"] is not None for task in body["tasks"])

    run_id = body["id"]
    detail = client.get(f"/api/v1/runs/{run_id}").json()
    assert detail["status"] == "completed"

    listing = client.get("/api/v1/runs").json()
    assert any(item["id"] == run_id for item in listing)
    summary = next(item for item in listing if item["id"] == run_id)
    assert summary["completed"] == 3


def test_get_unknown_run(client):
    resp = client.get("/api/v1/runs/run-not-exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "run_not_found"


def test_run_logs(client):
    resp = client.post("/api/v1/runs?wait=true", json={"tasks": TASKS})
    run_id = resp.json()["id"]

    logs = client.get(f"/api/v1/runs/{run_id}/logs").json()
    assert logs
    assert any("任务" in entry["message"] for entry in logs)
    assert any("运行结束" in entry["message"] for entry in logs)
    assert logs[0]["level"] == "info"

    detail = client.get(f"/api/v1/runs/{run_id}").json()
    assert len(detail["logs"]) == len(logs)


# --------------------------------------------------------------------------- #
# 失败传播（用假 Agent 精确控制失败点）
# --------------------------------------------------------------------------- #
class FakeAgent:
    def __init__(self, name: str, output: str = "ok", fail: bool = False) -> None:
        self.name = name
        self.output = output
        self.fail = fail
        self.calls: list[tuple[str, str | None]] = []

    async def run(self, task, *, context=None, temperature=None, max_tokens=None, workspace=None):
        self.calls.append((task, context))
        if self.fail:
            raise AppError("模拟模型失败", status_code=502, code="llm_error")
        return AgentRunResult(
            agent_id="fake",
            role="developer",
            display_name=self.name,
            model="fake-model",
            content=self.output,
            usage=Usage(1, 1, 2),
            latency_ms=1,
            mode="mock",
            allowed_tools=(),
        )


def _fake_team():
    developer = FakeAgent("开发", output="开发产出")
    tester = FakeAgent("测试", output="测试产出")
    reviewer = FakeAgent("评审", output="评审产出", fail=True)
    team = Team(
        id="fake",
        name="假团队",
        description="",
        captain=developer,
        members={"developer": developer, "tester": tester, "reviewer": reviewer},
        source=Path("fake.json"),
    )
    return team, developer, tester, reviewer


@pytest.mark.asyncio
async def test_failure_skips_downstream_and_keeps_independent_tasks(tmp_path):
    team, developer, tester, reviewer = _fake_team()
    tasks = [
        TaskSpec(id="T1", title="需求", goal="写需求", owner="developer"),
        TaskSpec(id="T2", title="测试", goal="跑测试", owner="tester", depends_on=["T1"]),
        TaskSpec(id="T3", title="验收", goal="做验收", owner="reviewer", depends_on=["T2"]),
        TaskSpec(id="T4", title="补文档", goal="写文档", owner="developer"),
    ]
    ordered = validate_task_list(tasks, set(team.members))
    run = RunState(id="run-fake", tasks=[TaskState(spec=task) for task in ordered])

    await execute_run(run, team, workspace=Workspace(tmp_path))

    statuses = {state.spec.id: state.status for state in run.tasks}
    assert statuses == {
        "T1": TaskStatus.completed,
        "T2": TaskStatus.completed,
        "T3": TaskStatus.failed,
        "T4": TaskStatus.completed,
    }
    assert run.status == "failed"
    # 独立任务不受失败影响，仍然执行；失败任务的下游不会调用模型
    assert len(developer.calls) == 2
    assert len(tester.calls) == 1
    assert len(reviewer.calls) == 1


@pytest.mark.asyncio
async def test_downstream_skipped_when_upstream_fails(tmp_path):
    team, _, _, _ = _fake_team()
    team.members["tester"] = FakeAgent("测试", fail=True)
    tasks = [
        TaskSpec(id="T1", title="A", goal="a", owner="developer"),
        TaskSpec(id="T2", title="B", goal="b", owner="tester", depends_on=["T1"]),
        TaskSpec(id="T3", title="C", goal="c", owner="reviewer", depends_on=["T2"]),
    ]
    ordered = validate_task_list(tasks, set(team.members))
    run = RunState(id="run-skip", tasks=[TaskState(spec=task) for task in ordered])

    await execute_run(run, team, workspace=Workspace(tmp_path))

    statuses = {state.spec.id: state.status for state in run.tasks}
    assert statuses["T2"] == TaskStatus.failed
    assert statuses["T3"] == TaskStatus.skipped
    assert "上游任务未成功" in (run.tasks[2].error or "")


@pytest.mark.asyncio
async def test_upstream_output_injected_as_context(tmp_path):
    team, _, _, _ = _fake_team()
    tasks = [
        TaskSpec(id="T1", title="需求", goal="写需求", owner="developer"),
        TaskSpec(id="T2", title="设计", goal="写设计", owner="tester", depends_on=["T1"]),
    ]
    ordered = validate_task_list(tasks, set(team.members))
    run = RunState(id="run-context", tasks=[TaskState(spec=task) for task in ordered])

    await execute_run(run, team, workspace=Workspace(tmp_path))

    _, context = team.members["tester"].calls[0]
    assert context is not None
    # 交接只给清单：能定位到产出文件，但不贴全文
    assert "tasks/T1.md" in context
    assert "工作区" in context
    assert "开发产出" not in context
