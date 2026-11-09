"""单 Agent 试跑 CLI。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\run_agent.py --agent captain --task "帮我做一个学生成绩管理系统的后端 API"
    .\\.venv\\Scripts\\python.exe scripts\\run_agent.py --agent architect --task "设计表结构" --context "需求文档……"
    .\\.venv\\Scripts\\python.exe scripts\\run_agent.py --list

默认读取 software_team 团队配置；--mock 可离线运行。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.registry import load_team  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.llm.client import DeepSeekClient  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单独试跑一个内置 Agent")
    parser.add_argument("--agent", help="成员 id，例如 captain / architect / developer")
    parser.add_argument("--task", help="交给 Agent 的任务")
    parser.add_argument("--context", default=None, help="上游产物（需求文档、设计文档、失败日志等）")
    parser.add_argument("--team", default="software_team", help="团队配置 id")
    parser.add_argument("--mock", action="store_true", help="本地模拟，不调用真实模型")
    parser.add_argument("--list", action="store_true", help="列出团队成员")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    settings = Settings(llm_mock=args.mock)
    llm = DeepSeekClient(settings)
    try:
        team = load_team(llm, args.team)
        if args.list:
            print(f"团队：{team.name}（队长 {team.captain.id}）")
            for agent in team.ordered():
                tools = ", ".join(agent.allowed_tools)
                print(f"  - {agent.id:<16} {agent.name:<4} 工具：{tools}")
            return 0

        if not args.agent or not args.task:
            print("缺少参数：--agent 与 --task（或用 --list 查看成员）")
            return 2

        agent = team.get(args.agent)
        print(f"[{agent.name}/{agent.id}] 执行中……\n")
        result = await agent.run(args.task, context=args.context)
        print(result.content)
        print(
            f"\n--- model={result.model} latency={result.latency_ms}ms "
            f"tokens={result.usage.total_tokens} mode={result.mode}"
        )
        return 0
    finally:
        await llm.aclose()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parse_args()
    if len(sys.argv) == 1:
        print("示例：python scripts/run_agent.py --agent captain --task \"做一个学生成绩管理系统\"")
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
