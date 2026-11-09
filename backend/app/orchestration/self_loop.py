"""Self-Loop：验收驳回后追加「修复 + 复评」任务并重跑。"""

from __future__ import annotations

from app.orchestration.models import RunState, TaskSpec, TaskState, TaskStatus


def append_repair_tasks(run: RunState, round_no: int) -> list[TaskState]:
    """在当前任务列表末尾追加一轮修复与复评任务。"""
    reviewer = next(
        (
            state
            for state in reversed(run.tasks)
            if state.spec.owner == "reviewer" and state.status is TaskStatus.completed
        ),
        None,
    )
    base_id = reviewer.spec.id if reviewer else run.tasks[-1].spec.id
    summary = (run.acceptance.summary or "评审未通过，请根据评审记录修复").strip()

    fix_id = f"R{round_no}-fix"
    review_id = f"R{round_no}-review"

    fix = TaskSpec(
        id=fix_id,
        title=f"第{round_no}轮修复",
        goal=(
            f"评审未通过（第 {round_no} 轮）。先 file_read 读取 tasks/{base_id}.md 查看完整评审记录，"
            f"再 file_list / file_read 检查工作区现有代码，定位问题并修复。\n\n"
            f"评审结论摘要：\n{summary[:1500]}\n\n"
            "要求：修复后把完整文件写回工作区（file_write），不要只给 diff；"
            "回复中说明改了哪些文件、根因是什么、如何验证。"
        ),
        owner="developer",
        depends_on=[base_id],
        deliverable="修复后的代码文件",
    )
    review = TaskSpec(
        id=review_id,
        title=f"第{round_no}轮复评",
        goal=(
            "对修复后的工作区重新验收。先用 file_list / file_read 读取最新代码与修复说明，"
            "逐条核对验收标准，输出与首轮相同的验收记录格式，并在「总体结论」中明确给出"
            "通过 / 有条件通过 / 驳回。"
        ),
        owner="reviewer",
        depends_on=[fix_id],
        deliverable="复评记录",
    )

    states = [TaskState(spec=fix), TaskState(spec=review)]
    run.tasks.extend(states)
    return states
