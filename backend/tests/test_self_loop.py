"""Self-Loop：驳回 → 追加修复任务 → 复评，以及轮次耗尽的降级路径。"""

from __future__ import annotations

import pytest

from app.agents.base import AgentRunResult
from app.agents.registry import Team
from app.llm.client import Usage
from app.orchestration.models import (
    AcceptanceStatus,
    RunState,
    RunStatus,
    TaskSpec,
    TaskState,
    TaskStatus,
)
from app.orchestration.scheduler import execute_run, validate_task_list
from app.orchestration.workspace import Workspace

REJECT = "## 总体结论\n\n**驳回**\n\n## 阻断项清单\n1. 缺少输入校验\n"
PASS = "## 总体结论\n\n**通过**\n"

CODE = "```python path=app/main.py\nprint('hello')\n```"


class ScriptedAgent:
    def __init__(self, name: str, outputs: list[str]) -> None:
        self.name = name
        self.outputs = outputs
        self.calls: list[tuple[str, str | None]] = []
        self.index = 0

    async def run(self, task, *, context=None, temperature=None, max_tokens=None, workspace=None):
        self.calls.append((task, context))
        output = self.outputs[min(self.index, len(self.outputs) - 1)]
        self.index += 1
        return AgentRunResult(
            agent_id="fake",
            role="developer",
            display_name=self.name,
            model="fake-model",
            content=output,
            usage=Usage(1, 1, 2),
            latency_ms=1,
            mode="mock",
            allowed_tools=(),
        )


def _team(reviewer_outputs: list[str]):
    developer = ScriptedAgent("开发", [CODE])
    reviewer = ScriptedAgent("评审", reviewer_outputs)
    team = Team(
        id="fake",
        name="假团队",
        description="",
        captain=developer,
        members={"developer": developer, "reviewer": reviewer},
        source=__import__("pathlib").Path("fake.json"),
    )
    return team, developer, reviewer


def _run(tmp_path):
    tasks = [
        TaskSpec(id="T1", title="实现", goal="写代码", owner="developer"),
        TaskSpec(id="T2", title="验收", goal="验收", owner="reviewer", depends_on=["T1"]),
    ]
    ordered = validate_task_list(tasks, {"developer", "reviewer"})
    return RunState(id="run-loop", tasks=[TaskState(spec=task) for task in ordered])


@pytest.mark.asyncio
async def test_self_loop_repairs_and_passes(tmp_path):
    team, developer, reviewer = _team([REJECT, PASS])
    run = _run(tmp_path)

    await execute_run(run, team, workspace=Workspace(tmp_path), max_rounds=2)

    assert run.status == RunStatus.completed
    assert run.acceptance.status is AcceptanceStatus.passed
    assert run.rounds == 1
    assert [state.spec.id for state in run.tasks] == ["T1", "T2", "R1-fix", "R1-review"]
    assert all(state.status is TaskStatus.completed for state in run.tasks)
    # 修复任务确实被执行，且拿到了复评记录的路径
    fix = run.tasks[2]
    assert "tasks/T2.md" in (fix.spec.goal or "")
    assert len(developer.calls) == 2
    assert len(reviewer.calls) == 2


@pytest.mark.asyncio
async def test_self_loop_exhausted_needs_human(tmp_path):
    team, developer, reviewer = _team([REJECT])
    run = _run(tmp_path)

    await execute_run(run, team, workspace=Workspace(tmp_path), max_rounds=2)

    assert run.status == RunStatus.rejected
    assert run.acceptance.status is AcceptanceStatus.rejected
    assert run.rounds == 2
    assert run.needs_human is True
    assert [state.spec.id for state in run.tasks] == [
        "T1",
        "T2",
        "R1-fix",
        "R1-review",
        "R2-fix",
        "R2-review",
    ]
    assert len(reviewer.calls) == 3


@pytest.mark.asyncio
async def test_without_reviewer_acceptance_pending(tmp_path):
    team, _, _ = _team([REJECT])
    tasks = [TaskSpec(id="T1", title="实现", goal="写代码", owner="developer")]
    run = RunState(
        id="run-noreview",
        tasks=[TaskState(spec=task) for task in validate_task_list(tasks, {"developer", "reviewer"})],
    )

    await execute_run(run, team, workspace=Workspace(tmp_path), max_rounds=2)

    assert run.acceptance.status is AcceptanceStatus.pending
    assert run.status == RunStatus.completed
    assert run.rounds == 0
