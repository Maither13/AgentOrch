"""一句话需求 → 队长拆解 → 顺序执行。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\run_pipeline.py --goal "做一个学生成绩管理系统的后端 API"
    .\\.venv\\Scripts\\python.exe scripts\\run_pipeline.py --goal "..." --plan-only
    .\\.venv\\Scripts\\python.exe scripts\\run_pipeline.py --goal "..." --mock
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.registry import load_team  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.llm.client import DeepSeekClient  # noqa: E402
from app.orchestration.models import RunState, TaskState  # noqa: E402
from app.orchestration.planner import plan_tasks  # noqa: E402
from app.orchestration.scheduler import execute_run  # noqa: E402


async def _run(args: argparse.Namespace) -> int:
    settings = Settings(llm_mock=args.mock)
    llm = DeepSeekClient(settings)
    try:
        team = load_team(llm, args.team)
        print(f"需求：{args.goal}")
        print("队长拆解中…")
        plan = await plan_tasks(team, args.goal)

        print(
            f"\n拆出 {len(plan.tasks)} 个任务"
            f"（{plan.latency_ms} ms，{plan.usage.total_tokens} tokens，mode={plan.mode}）："
        )
        for task in plan.tasks:
            dependency = f"  <- {', '.join(task.depends_on)}" if task.depends_on else ""
            print(f"  {task.id:<4} {task.title:<10} {task.owner:<16}{dependency}")

        if args.plan_only:
            print("\n（--plan-only：未执行）")
            return 0

        run = RunState(
            id="cli-run",
            goal=args.goal,
            plan_source="captain",
            tasks=[TaskState(spec=task) for task in plan.tasks],
        )
        print("\n开始顺序执行…")
        started = time.perf_counter()
        await execute_run(run, team)

        print()
        for state in run.tasks:
            print(
                f"  [{state.status:<9}] {state.spec.id:<4} {state.spec.title:<10}"
                f" {state.duration_ms or 0:>6}ms  {state.usage.total_tokens:>5} tokens"
            )
            if state.error:
                print(f"      error: {state.error}")
            if args.show_output and state.output:
                preview = state.output.strip().replace("\n", " ")[:220]
                print(f"      {preview}…")

        print(f"\nrun={run.status}  总耗时 {time.perf_counter() - started:.1f}s")
        return 0 if run.status == "completed" else 1
    finally:
        await llm.aclose()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="队长拆解 + 顺序执行")
    parser.add_argument("--goal", required=True, help="一句话需求")
    parser.add_argument("--team", default="software_team", help="团队配置 id")
    parser.add_argument("--plan-only", action="store_true", help="只拆解不执行")
    parser.add_argument("--show-output", action="store_true", help="打印每个任务输出的前 220 字")
    parser.add_argument("--mock", action="store_true", help="本地模拟，不调用真实模型")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
