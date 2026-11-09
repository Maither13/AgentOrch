"""兼容 DeepSeek 偶发的 DSML 文本工具调用。

正常情况下 function calling 走标准 `message.tool_calls`，但上游网关在部分场景
（一轮里要求调用多个工具、或工具调用后又追加调用）会把工具调用写成 DSML 文本：

    <｜｜DSML｜｜ calls>
    <｜｜DSML｜｜ invoke name="file_write">
    <｜｜DSML｜｜ parameter name="path" string="true">app/main.py</｜｜DSML｜｜ parameter>
    ...
    </｜｜DSML｜｜ invoke>
    </｜｜DSML｜｜ calls>

这里做一层兜底解析，把 DSML 文本还原成 (工具名, 参数) 列表，交给同一套执行器。
"""

from __future__ import annotations

import re

TOKEN = "｜｜DSML｜｜"

_CALLS_RE = re.compile(rf"<{TOKEN}\s*calls>(.*?)</{TOKEN}\s*calls>", re.DOTALL)
_INVOKE_RE = re.compile(
    rf"<{TOKEN}\s*invoke\s+name=\"([^\"]+)\"\s*>(.*?)</{TOKEN}\s*invoke>", re.DOTALL
)
_PARAM_RE = re.compile(
    rf"<{TOKEN}\s*parameter\s+name=\"([^\"]+)\"[^>]*>(.*?)</{TOKEN}\s*parameter>",
    re.DOTALL,
)


def parse_dsml_calls(content: str) -> list[tuple[str, dict]]:
    """返回 [(tool_name, arguments), ...]；不是 DSML 就返回空列表。"""
    if not content or TOKEN not in content:
        return []

    calls: list[tuple[str, dict]] = []
    for block in _CALLS_RE.findall(content):
        for name, body in _INVOKE_RE.findall(block):
            calls.append((name, {key: value for key, value in _PARAM_RE.findall(body)}))
    return calls


def strip_dsml(content: str) -> str:
    """去掉 DSML 调用块，避免把内部标记当成正文返回给调用方。"""
    if not content or TOKEN not in content:
        return content
    cleaned = _CALLS_RE.sub("", content)
    return re.sub(rf"</?{TOKEN}[^>]*>", "", cleaned).strip()
