"""验收结论解析：从评审 Agent 的输出里提取「通过 / 驳回」。

执行状态由调度器负责（有没有异常），验收状态由评审 Agent 负责（内容合不合格），
两者互不覆盖——这就是工程上常说的「执行 ≠ 验收」。
"""

from __future__ import annotations

import re

from app.orchestration.models import (
    AcceptanceState,
    AcceptanceStatus,
    RunState,
    TaskStatus,
    TestResult,
    utcnow,
)

_CONCLUSION_KEYS = ("总体结论", "最终结论", "验收结论")
_VERDICT_RE = re.compile(r"(有条件通过|驳回|通过)")


def parse_review(text: str) -> tuple[AcceptanceStatus, str | None, str, list[str]]:
    """返回 (验收状态, 结论原文, 结论摘要, 阻断项)。"""
    if not text:
        return AcceptanceStatus.pending, None, "", []

    index = -1
    for key in _CONCLUSION_KEYS:
        index = text.find(key)
        if index != -1:
            break
    if index == -1:
        return AcceptanceStatus.pending, None, "", []

    section = text[index : index + 600].strip()
    match = _VERDICT_RE.search(section)
    if match is None:
        return AcceptanceStatus.pending, None, section, []

    verdict = match.group(1)
    status = AcceptanceStatus.rejected if verdict == "驳回" else AcceptanceStatus.passed
    blockers = _extract_blockers(text) if status is AcceptanceStatus.rejected else []
    return status, verdict, section, blockers


def _extract_blockers(text: str) -> list[str]:
    """从「阻断项清单」里提取 P0 条目，过滤掉复现/修复这类续行与表格分隔线。"""
    index = text.find("阻断项")
    if index == -1:
        return []

    blockers: list[str] = []
    for raw in text[index : index + 1_200].splitlines()[1:]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if set(line) <= set("|-: "):
            continue
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            line = next((cell for cell in cells if cell), "")
        line = line.lstrip("-*0123456789. 、")
        line = line.replace("**", "").strip()
        if not line or line.startswith(("复现", "修复", "期望", "实际", "证据", "说明", "建议")):
            continue
        blockers.append(line[:160])
        if len(blockers) >= 5:
            break
    return blockers


def evaluate_acceptance(run: RunState) -> AcceptanceState:
    """取最近一次完成的评审任务输出，更新 run.acceptance。"""
    reviewers = [
        state
        for state in run.tasks
        if state.spec.owner == "reviewer"
        and state.status is TaskStatus.completed
        and state.output
    ]
    if not reviewers:
        run.acceptance = AcceptanceState()
        return run.acceptance

    latest = reviewers[-1]
    status, verdict, summary, blockers = parse_review(latest.output or "")
    if status is AcceptanceStatus.pending:
        # 有评审任务却没有「总体结论」：信息不足，绝不能算通过
        status = AcceptanceStatus.needs_revision
        summary = "评审未给出「总体结论」，无法判定验收结果。\n" + (summary or "")

    run.acceptance = AcceptanceState(
        status=status,
        verdict=verdict,
        summary=summary,
        blockers=blockers,
        reviewer_task=latest.spec.id,
        reviewed_at=utcnow(),
    )
    return run.acceptance


def latest_test_result(run: RunState) -> TestResult | None:
    """取最近一次 test_runner 的执行结果。"""
    for state in reversed(run.tasks):
        if state.test_result is not None:
            return state.test_result
    return None


def apply_test_gate(run: RunState) -> None:
    """自动化测试门：pytest 失败时，验收结论强制为 rejected。

    评审 Agent 可以给「通过」，但只要测试退出码非 0，就不能算验收通过。
    """
    result = latest_test_result(run)
    if result is None or result.exit_code == 0:
        return

    detail = result.output.strip()
    if len(detail) > 1_500:
        detail = detail[-1_500:]
    reviewer_verdict = run.acceptance.verdict
    prefix = f"评审结论：{reviewer_verdict}，但" if reviewer_verdict else ""
    run.acceptance = AcceptanceState(
        status=AcceptanceStatus.rejected,
        verdict="测试未通过",
        summary=f"{prefix}自动化测试门未通过（pytest 退出码 {result.exit_code}）。\n{detail}",
        blockers=run.acceptance.blockers,
        reviewer_task=run.acceptance.reviewer_task,
        reviewed_at=utcnow(),
    )
