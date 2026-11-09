"""文件类工具的 function-calling 定义（与 TOOL_REGISTRY 中的名字对应）。"""

from __future__ import annotations

from typing import Iterable

FILE_TOOL_SCHEMAS: dict[str, dict] = {
    "file_list": {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": "列出当前运行工作区里的所有文件（路径与大小）",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    "file_read": {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "读取工作区中一个文件的完整内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对工作区根目录的路径，例如 artifacts/T1.md"}
                },
                "required": ["path"],
            },
        },
    },
    "file_write": {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "把完整文件内容写入工作区（自动创建目录，覆盖同名文件）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，例如 app/main.py"},
                    "content": {"type": "string", "description": "完整文件内容，不要省略"},
                },
                "required": ["path", "content"],
            },
        },
    },
}


def schemas_for(allowed_tools: Iterable[str]) -> list[dict]:
    return [FILE_TOOL_SCHEMAS[name] for name in allowed_tools if name in FILE_TOOL_SCHEMAS]
