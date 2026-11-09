"""工作流：固定步骤模板 + 拓扑分层。

和「队长自由拆解」不同，工作流是事先定义好的编排：步骤、负责人、依赖都写死，
调度器只负责按拓扑层并行执行。适合演示稳定的标准流程。
"""

from __future__ import annotations

import re
from typing import Iterable

from pydantic import BaseModel, Field

from app.agents.roles import AGENT_CLASSES
from app.core.errors import AppError
from app.orchestration.models import TaskSpec

_ASCII_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class WorkflowStep(BaseModel):
    """一个工作流步骤：步骤名 + 负责 Agent + 依赖的步骤名。"""

    step_name: str = Field(min_length=1, max_length=60)
    agent: str = Field(min_length=1, max_length=40)
    depends_on: list[str] = Field(default_factory=list)


class WorkflowTemplate(BaseModel):
    id: str
    name: str
    description: str = ""
    steps: list[WorkflowStep]


# --------------------------------------------------------------------------- #
# 固定模板：软件需求工程
# --------------------------------------------------------------------------- #
# 每个步骤的指令；{goal} 会替换成用户需求。
STEP_INSTRUCTIONS: dict[str, str] = {
    "需求分析": (
        "对用户需求做产品分析：输出功能列表（含优先级）、接口定义、数据字段，"
        "以及可被自动化测试验证的验收标准（AC 编号）。\n\n## 用户需求\n{goal}"
    ),
    "技术设计": (
        "基于工作区中的需求文档，输出技术方案、模块划分、表结构与接口契约，"
        "逐条对应需求编号。\n\n## 用户需求\n{goal}"
    ),
    "接口实现": (
        "按工作区中的需求与设计，实现后端接口代码，把完整文件写入工作区。\n\n"
        "## 用户需求\n{goal}"
    ),
    "测试设计": (
        "基于工作区中的需求与设计，编写 pytest 用例并写入工作区（不需要等实现完成），"
        "用例要对应验收标准。\n\n## 用户需求\n{goal}"
    ),
    "测试执行": (
        "读取工作区中的代码与测试用例，核对实现是否符合需求与设计，输出测试报告："
        "覆盖了哪些验收标准、发现的问题、未覆盖的缺口。"
    ),
    "代码评审": (
        "对工作区中的交付逐条验收：每条验收标准给出 passed/failed 与证据，"
        "最后在「总体结论」中明确给出 通过 / 有条件通过 / 驳回。"
    ),
    "交付汇总": (
        "汇总本次交付：需求、设计、实现、测试与评审结论，输出最终交付说明与遗留风险，"
        "不要修改代码。"
    ),
}

SOFTWARE_DEVELOPMENT = WorkflowTemplate(
    id="software_development",
    name="软件需求工程（固定模板）",
    description="需求 → 设计 → 接口实现 ∥ 测试设计 → 测试执行 → 评审 → 交付汇总",
    steps=[
        WorkflowStep(step_name="需求分析", agent="product_manager"),
        WorkflowStep(step_name="技术设计", agent="architect", depends_on=["需求分析"]),
        WorkflowStep(step_name="接口实现", agent="developer", depends_on=["技术设计"]),
        WorkflowStep(step_name="测试设计", agent="tester", depends_on=["技术设计"]),
        WorkflowStep(step_name="测试执行", agent="tester", depends_on=["接口实现", "测试设计"]),
        WorkflowStep(step_name="代码评审", agent="reviewer", depends_on=["测试执行"]),
        WorkflowStep(step_name="交付汇总", agent="captain", depends_on=["代码评审"]),
    ],
)

WORKFLOWS: dict[str, WorkflowTemplate] = {SOFTWARE_DEVELOPMENT.id: SOFTWARE_DEVELOPMENT}


# --------------------------------------------------------------------------- #
# 校验与拓扑分层
# --------------------------------------------------------------------------- #
def validate_workflow(template: WorkflowTemplate) -> None:
    if not template.steps:
        raise AppError(f"工作流 {template.id} 没有任何步骤", status_code=400, code="workflow_invalid")

    names = [step.step_name for step in template.steps]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise AppError(f"工作流步骤名重复：{duplicates}", status_code=400, code="workflow_invalid")

    name_set = set(names)
    for step in template.steps:
        if step.agent not in AGENT_CLASSES:
            raise AppError(
                f"步骤「{step.step_name}」的 Agent 不存在：{step.agent}",
                status_code=400,
                code="workflow_invalid",
            )
        for dependency in step.depends_on:
            if dependency == step.step_name:
                raise AppError(
                    f"步骤「{step.step_name}」不能依赖自己",
                    status_code=400,
                    code="workflow_invalid",
                )
            if dependency not in name_set:
                raise AppError(
                    f"步骤「{step.step_name}」依赖了不存在的步骤：{dependency}",
                    status_code=400,
                    code="workflow_invalid",
                )

    topological_layers(template.steps)  # 有环会在这里抛错


def topological_layers(steps: Iterable[WorkflowStep]) -> list[list[str]]:
    """Kahn 分层：同一层的步骤之间没有依赖，可以并行执行。"""
    ordered = list(steps)
    by_name = {step.step_name: step for step in ordered}
    indegree = {step.step_name: len(step.depends_on) for step in ordered}
    children: dict[str, list[str]] = {step.step_name: [] for step in ordered}
    for step in ordered:
        for dependency in step.depends_on:
            children[dependency].append(step.step_name)

    ready = [step.step_name for step in ordered if indegree[step.step_name] == 0]
    layers: list[list[str]] = []
    while ready:
        layers.append(ready)
        next_ready: list[str] = []
        for name in ready:
            for child in children[name]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    next_ready.append(child)
        ready = next_ready

    if sum(len(layer) for layer in layers) != len(by_name):
        stuck = [name for name in by_name if name not in {n for layer in layers for n in layer}]
        raise AppError(f"工作流依赖存在环：{stuck}", status_code=400, code="workflow_cycle")

    return layers


def build_task_specs(template: WorkflowTemplate, goal: str) -> list[TaskSpec]:
    """把模板步骤转成可交给调度器的任务清单（保持模板顺序）。"""
    goal = (goal or "").strip()
    if not goal:
        raise AppError("goal 不能为空", status_code=400, code="empty_goal")

    validate_workflow(template)

    ids: dict[str, str] = {}
    used: set[str] = set()
    for index, step in enumerate(template.steps, start=1):
        candidate = step.step_name if _ASCII_ID.match(step.step_name) else f"S{index}"
        while candidate in used:
            candidate = f"S{index}-{len(used)}"
        ids[step.step_name] = candidate
        used.add(candidate)

    tasks: list[TaskSpec] = []
    for step in template.steps:
        instruction = STEP_INSTRUCTIONS.get(step.step_name, f"完成「{step.step_name}」阶段的工作。")
        tasks.append(
            TaskSpec(
                id=ids[step.step_name],
                title=step.step_name,
                goal=instruction.format(goal=goal),
                owner=step.agent,
                depends_on=[ids[name] for name in step.depends_on],
                deliverable=step.step_name,
            )
        )
    return tasks
