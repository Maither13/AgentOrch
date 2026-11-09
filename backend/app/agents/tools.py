"""工具注册表。

当前阶段只描述工具元信息，用来给每个 Agent 声明权限、供前端/接口展示；
真正的工具执行在「工具集成」模块实现，届时按 Agent 的 allowed_tools 做准入校验。

工具名一旦发布不要重命名，它会出现在团队 JSON 和审计日志里。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.core.errors import AppError


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    display_name: str
    description: str
    # False 表示只在注册表里占位（规划/联网/受限命令），不会暴露给模型调用
    implemented: bool = True


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "task_plan": ToolSpec("task_plan", "任务规划", "编排层内部能力：生成或更新任务 DAG", implemented=False),
    "task_dispatch": ToolSpec("task_dispatch", "任务派发", "编排层内部能力：把就绪任务分派给成员", implemented=False),
    "knowledge_search": ToolSpec("knowledge_search", "知识库检索", "在工作区文件中做关键字检索"),
    "web_search": ToolSpec("web_search", "联网搜索", "检索公开资料（待接入搜索 API）", implemented=False),
    "file_read": ToolSpec("file_read", "读取文件", "读取工作区中的代码与文档"),
    "file_write": ToolSpec("file_write", "写入文件", "在工作区创建或修改文件"),
    "file_list": ToolSpec("file_list", "列出文件", "列出运行工作区中的代码与产出文件"),
    "python_exec": ToolSpec("python_exec", "Python 执行", "在工作区独立进程里执行 Python 代码"),
    "shell_exec": ToolSpec("shell_exec", "命令执行", "执行受限 shell 命令（安全原因尚未开放）", implemented=False),
    "test_runner": ToolSpec("test_runner", "测试执行", "在工作区运行 pytest 并收集报告"),
}


class ToolPermissionError(AppError):
    """Agent 尝试使用未授权的工具。"""

    def __init__(self, agent_id: str, tools: Iterable[str]) -> None:
        names = ", ".join(tools)
        super().__init__(
            f"Agent「{agent_id}」无权使用工具：{names}",
            status_code=403,
            code="tool_forbidden",
        )
        self.agent_id = agent_id
        self.tools = list(tools)


def get_tool(name: str) -> ToolSpec | None:
    return TOOL_REGISTRY.get(name)


def tool_infos(names: Iterable[str]) -> tuple[ToolSpec, ...]:
    """按声明顺序返回工具元信息。"""
    return tuple(TOOL_REGISTRY[name] for name in names if name in TOOL_REGISTRY)
