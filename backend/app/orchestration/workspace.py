"""运行工作区：代码与产出落盘，Agent 通过文件工具读写，不再靠 prompt 传全文。

目录结构（backend/data/workspaces/<run_id>/）：
    app/...              开发 Agent 写出的代码
    tests/...            测试 Agent 写出的用例
    artifacts/<task>.md  每个任务的完整产出（需求、设计、评审记录）
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import AppError

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE_ROOT = BACKEND_DIR / "data" / "workspaces"

# 匹配 ```python path=app/main.py 代码块
CODE_BLOCK_RE = re.compile(
    r"```[A-Za-z0-9_+.-]*[ \t]+path=(?P<path>[^\s`]+)[ \t]*\n(?P<code>.*?)```",
    re.DOTALL,
)

MAX_FILE_CHARS = 200_000
MAX_READ_CHARS = 40_000


@dataclass(frozen=True, slots=True)
class FileInfo:
    path: str
    size: int
    sha256: str


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


class Workspace:
    """单个 run 的沙箱目录，所有路径都被限制在根目录内。"""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_run(cls, run_id: str) -> "Workspace":
        return cls(DEFAULT_WORKSPACE_ROOT / run_id)

    # ---------------- 路径安全 ----------------
    def resolve(self, relative: str) -> Path:
        raw = (relative or "").strip().replace("\\", "/").lstrip("/")
        if not raw:
            raise AppError("文件路径不能为空", status_code=400, code="invalid_path")
        target = (self.root / raw).resolve()
        if target != self.root and self.root not in target.parents:
            raise AppError(f"非法路径（越出工作区）：{relative}", status_code=400, code="invalid_path")
        if target == self.root:
            raise AppError("路径必须指向文件", status_code=400, code="invalid_path")
        return target

    # ---------------- 读写 ----------------
    def write_text(self, relative: str, content: str) -> FileInfo:
        if len(content) > MAX_FILE_CHARS:
            raise AppError(
                f"文件过大（{len(content)} 字，上限 {MAX_FILE_CHARS}）",
                status_code=400,
                code="file_too_large",
            )
        target = self.resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        # newline="" 避免 Windows 把 \n 改写成 \r\n，影响字节大小与哈希
        with target.open("w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        return self._file_info(target)

    def read_text(self, relative: str, *, max_chars: int = MAX_READ_CHARS) -> str:
        target = self.resolve(relative)
        if not target.is_file():
            raise AppError(f"文件不存在：{relative}", status_code=404, code="file_not_found")
        text = target.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n…（已截断，原始 {len(text)} 字）"
        return text

    def save_artifact(self, task_id: str, content: str) -> FileInfo:
        """任务完整回复留档。用 tasks/ 命名空间，避免覆盖 Agent 自己写的 artifacts/。"""
        return self.write_text(f"tasks/{task_id}.md", content)

    def write_code_blocks(self, content: str) -> list[FileInfo]:
        """从 Agent 输出里提取 ```lang path=...``` 代码块并落盘。"""
        files: list[FileInfo] = []
        for match in CODE_BLOCK_RE.finditer(content):
            code = match.group("code")
            if not code.strip():
                continue
            body = code if code.endswith("\n") else code + "\n"
            try:
                files.append(self.write_text(match.group("path").strip(), body))
            except AppError:
                continue
        return files

    # ---------------- 查询 ----------------
    def list_files(self) -> list[FileInfo]:
        return [
            self._file_info(path)
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        ]

    def manifest(self, *, max_entries: int = 40) -> str:
        files = self.list_files()
        if not files:
            return f"工作区：{self.root.name}（空）"
        total = sum(item.size for item in files)
        lines = [f"工作区：{self.root.name}，{len(files)} 个文件，共 {_human_size(total)}"]
        for item in files[:max_entries]:
            lines.append(f"- {item.path} ({_human_size(item.size)})")
        if len(files) > max_entries:
            lines.append(f"… 其余 {len(files) - max_entries} 个文件略")
        return "\n".join(lines)

    def _file_info(self, path: Path) -> FileInfo:
        data = path.read_bytes()
        return FileInfo(
            path=path.relative_to(self.root).as_posix(),
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest()[:12],
        )

    # ---------------- 工具执行 ----------------
    def execute(self, name: str, arguments: dict) -> dict:
        if name == "file_list":
            return {"files": [{"path": item.path, "size": item.size} for item in self.list_files()]}
        if name == "file_read":
            path = str(arguments.get("path", ""))
            return {"path": path, "content": self.read_text(path)}
        if name == "file_write":
            path = str(arguments.get("path", ""))
            content = str(arguments.get("content", ""))
            info = self.write_text(path, content)
            return {"path": info.path, "size": info.size}
        raise AppError(f"未知工具：{name}", status_code=400, code="unknown_tool")
