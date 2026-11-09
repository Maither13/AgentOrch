"""Self-Loop：验收/测试失败后追加「修复 → 重测 → 复评」任务并重跑。"""

from __future__ import annotations

from app.orchestration.acceptance import latest_test_result
from app.orchestration.models import RunState, TaskSpec, TaskState, TaskStatus


def append_repair_tasks(run: RunState, round_no: int) -> list[TaskState]:
    """在当前任务列表末尾追加一轮修复、重测与复评任务。"""
    reviewer = next(
        (
            state
            for state in reversed(run.tasks)
            if state.spec.owner == "reviewer" and state.status is TaskStatus.completed
        ),
        None,
    )
    base_id = reviewer.spec.id if reviewer else run.tasks[-1].spec.id
    test_result = latest_test_result(run)

    sections: list[str] = []
    if test_result is not None and test_result.exit_code != 0:
        output = test_result.output.strip()
        if len(output) > 3_000:
            output = "…（只保留末尾）\n" + output[-3_000:]
        sections.append(f"## 失败测试日志（pytest 退出码 {test_result.exit_code}）\n{output}")
    summary = (run.acceptance.summary or "评审未通过，请根据评审记录修复").strip()
    sections.append(f"## 评审结论\n{summary[:1_200]}")
    failure_context = "\n\n".join(sections)

    fix_id = f"R{round_no}-fix"
    test_id = f"R{round_no}-test"
    review_id = f"R{round_no}-review"

    fix = TaskSpec(
        id=fix_id,
        title=f"第{round_no}轮修复",
        goal=(
            f"上一轮未通过（第 {round_no} 轮）。先 file_read 读取 tasks/{base_id}.md 查看完整评审记录，"
            f"再 file_list / file_read 检查工作区代码，定位失败原因并修复。\n\n"
            f"{failure_context}\n\n"
            "要求：修复后把完整文件写回工作区（file_write），不要只给 diff；"
            "回复中说明根因、改了哪些文件。"
        ),
        owner="developer",
        depends_on=[base_id],
        deliverable="修复后的代码文件",
    )
    test = TaskSpec(
        id=test_id,
        title=f"第{round_no}轮重测",
        goal=(
            "重新运行 pytest（必须调用 test_runner），确认修复是否生效。"
            "报告退出码、通过/失败数量与失败用例日志；如果仍然失败，把完整失败信息写进回复。"
            "不要修改业务代码。"
        ),
        owner="tester",
        depends_on=[fix_id],
        deliverable="重测报告",
    )
    review = TaskSpec(
        id=review_id,
        title=f"第{round_no}轮复评",
        goal=(
            "对修复后的工作区重新验收。先用 file_list / file_read 读取最新代码与重测报告，"
            "逐条核对验收标准，输出与首轮相同的验收记录格式，并在「总体结论」中明确给出"
            "通过 / 有条件通过 / 驳回。"
        ),
        owner="reviewer",
        depends_on=[test_id],
        deliverable="复评记录",
    )

    states = [TaskState(spec=fix), TaskState(spec=test), TaskState(spec=review)]
    run.tasks.extend(states)
    return states
