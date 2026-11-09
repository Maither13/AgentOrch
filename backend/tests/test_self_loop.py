"""Self-Loop：失败 → 修复 → 重测 → 复评，以及测试门和轮次耗尽。"""

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


class ScriptedTester(ScriptedAgent):
    """每次 run 返回一个 test_runner 结果，用来验证测试门与重测。"""

    def __init__(self, exit_codes: list[int]) -> None:
        super().__init__("测试", ["测试完成"])
        self.exit_codes = exit_codes
        self.runs = 0

    async def run(self, task, *, context=None, temperature=None, max_tokens=None, workspace=None):
        result = await super().run(
            task, context=context, temperature=temperature, max_tokens=max_tokens, workspace=workspace
        )
        code = self.exit_codes[min(self.runs, len(self.exit_codes) - 1)]
        self.runs += 1
        result.tool_calls = [
            {
                "name": "test_runner",
                "arguments": {},
                "result": {
                    "exit_code": code,
                    "output": f"pytest exit {code}",
                    "command": "python -m pytest -q",
                },
            }
        ]
        return result


def _team(reviewer_outputs: list[str], tester: ScriptedTester | None = None):
    developer = ScriptedAgent("开发", [CODE])
    tester = tester or ScriptedTester([0])
    reviewer = ScriptedAgent("评审", reviewer_outputs)
    team = Team(
        id="fake",
        name="假团队",
        description="",
        captain=developer,
        members={"developer": developer, "tester": tester, "reviewer": reviewer},
        source=__import__("pathlib").Path("fake.json"),
    )
    return team, developer, tester, reviewer


def _run(with_tester: bool = False) -> RunState:
    tasks = [TaskSpec(id="T1", title="实现", goal="写代码", owner="developer")]
    if with_tester:
        tasks.append(TaskSpec(id="T2", title="测试", goal="跑测试", owner="tester", depends_on=["T1"]))
        tasks.append(TaskSpec(id="T3", title="验收", goal="验收", owner="reviewer", depends_on=["T2"]))
    else:
        tasks.append(TaskSpec(id="T2", title="验收", goal="验收", owner="reviewer", depends_on=["T1"]))
    ordered = validate_task_list(tasks, {"developer", "tester", "reviewer"})
    return RunState(id="run-loop", tasks=[TaskState(spec=task) for task in ordered])


@pytest.mark.asyncio
async def test_self_loop_repairs_and_passes(tmp_path):
    team, developer, tester, reviewer = _team([REJECT, PASS])
    run = _run()

    await execute_run(run, team, workspace=Workspace(tmp_path), max_rounds=3)

    assert run.status == RunStatus.completed
    assert run.acceptance.status is AcceptanceStatus.passed
    assert run.rounds == 1
    assert [state.spec.id for state in run.tasks] == [
        "T1",
        "T2",
        "R1-fix",
        "R1-test",
        "R1-review",
    ]
    assert all(state.status is TaskStatus.completed for state in run.tasks)
    fix = run.tasks[2]
    assert "tasks/T2.md" in (fix.spec.goal or "")
    assert len(developer.calls) == 2
    assert len(tester.calls) == 1
    assert len(reviewer.calls) == 2


@pytest.mark.asyncio
async def test_self_loop_exhausted_needs_human(tmp_path):
    team, developer, tester, reviewer = _team([REJECT])
    run = _run()

    await execute_run(run, team, workspace=Workspace(tmp_path), max_rounds=2)

    assert run.status == RunStatus.rejected
    assert run.acceptance.status is AcceptanceStatus.rejected
    assert run.rounds == 2
    assert run.needs_human is True
    assert [state.spec.id for state in run.tasks] == [
        "T1",
        "T2",
        "R1-fix",
        "R1-test",
        "R1-review",
        "R2-fix",
        "R2-test",
        "R2-review",
    ]
    assert len(tester.calls) == 2
    assert len(reviewer.calls) == 3


@pytest.mark.asyncio
async def test_failing_test_overrides_review_and_marks_human(tmp_path):
    """评审说通过，但 pytest 失败：测试门必须把 run 判为 rejected。"""
    team, _, tester, reviewer = _team([PASS], tester=ScriptedTester([1]))
    run = _run(with_tester=True)

    await execute_run(run, team, workspace=Workspace(tmp_path), max_rounds=0)

    assert run.execution_status.value == "completed"
    assert run.acceptance.status is AcceptanceStatus.rejected
    assert run.acceptance.verdict == "测试未通过"
    assert run.status == RunStatus.rejected
    assert run.needs_human is True
    assert run.tasks[1].test_result is not None
    assert run.tasks[1].test_result.exit_code == 1


@pytest.mark.asyncio
async def test_failing_test_triggers_repair_then_passes(tmp_path):
    """首轮测试失败触发 Self-Loop，重测通过后 run 完成。"""
    team, developer, tester, reviewer = _team([PASS], tester=ScriptedTester([1, 0]))
    run = _run(with_tester=True)

    await execute_run(run, team, workspace=Workspace(tmp_path), max_rounds=1)

    assert run.rounds == 1
    assert run.status == RunStatus.completed
    assert run.acceptance.status is AcceptanceStatus.passed
    assert tester.runs == 2
    assert [state.spec.id for state in run.tasks][-3:] == ["R1-fix", "R1-test", "R1-review"]
    assert run.tasks[-2].test_result is not None
    assert run.tasks[-2].test_result.exit_code == 0


@pytest.mark.asyncio
async def test_review_without_conclusion_needs_revision(tmp_path):
    """评审存在但没给「总体结论」：必须转人工，绝不能算 completed。"""
    team, _, _, _ = _team(["整体还行，暂时没发现问题。"])
    run = _run()

    await execute_run(run, team, workspace=Workspace(tmp_path), max_rounds=3)

    assert run.status == RunStatus.needs_revision
    assert run.acceptance.status is AcceptanceStatus.needs_revision
    assert run.needs_human is True
    assert run.rounds == 0


@pytest.mark.asyncio
async def test_tool_calls_are_traced(tmp_path):
    team, _, _, _ = _team([PASS], tester=ScriptedTester([0]))
    run = _run(with_tester=True)

    await execute_run(run, team, workspace=Workspace(tmp_path), max_rounds=0)

    tester_state = next(state for state in run.tasks if state.spec.owner == "tester")
    assert tester_state.test_result is not None
    assert tester_state.test_result.exit_code == 0
    assert [call.name for call in tester_state.tool_calls] == ["test_runner"]
    assert tester_state.tool_calls[0].ok is True


@pytest.mark.asyncio
async def test_without_reviewer_acceptance_pending(tmp_path):
    team, _, _, _ = _team([REJECT])
    tasks = [TaskSpec(id="T1", title="实现", goal="写代码", owner="developer")]
    run = RunState(
        id="run-noreview",
        tasks=[TaskState(spec=task) for task in validate_task_list(tasks, {"developer", "reviewer"})],
    )

    await execute_run(run, team, workspace=Workspace(tmp_path), max_rounds=3)

    assert run.acceptance.status is AcceptanceStatus.pending
    assert run.status == RunStatus.completed
    assert run.rounds == 0
