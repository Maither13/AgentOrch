"""工作区：文件落盘、清单、路径安全与代码块提取。"""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.orchestration.workspace import Workspace


def test_write_read_list_and_manifest(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.write_text("app/main.py", "print('hi')\n")
    workspace.save_artifact("T1", "# 需求文档")

    assert workspace.read_text("app/main.py") == "print('hi')\n"
    paths = [item.path for item in workspace.list_files()]
    assert paths == ["app/main.py", "tasks/T1.md"]

    manifest = workspace.manifest()
    assert "app/main.py" in manifest
    assert "tasks/T1.md" in manifest
    assert "2 个文件" in manifest


def test_path_traversal_blocked(tmp_path):
    workspace = Workspace(tmp_path)
    with pytest.raises(AppError) as exc:
        workspace.write_text("../outside.txt", "x")
    assert exc.value.code == "invalid_path"

    with pytest.raises(AppError):
        workspace.read_text("../../etc/passwd")


def test_code_blocks_written(tmp_path):
    workspace = Workspace(tmp_path)
    content = (
        "说明\n\n```python path=app/a.py\nprint(1)\n```\n\n"
        "```python path=tests/test_a.py\nimport app\n```\n"
    )
    files = workspace.write_code_blocks(content)
    assert [item.path for item in files] == ["app/a.py", "tests/test_a.py"]
    assert workspace.read_text("tests/test_a.py").startswith("import app")


def test_tool_execute(tmp_path):
    workspace = Workspace(tmp_path)
    result = workspace.execute("file_write", {"path": "app/x.py", "content": "x = 1\n"})
    assert result == {"path": "app/x.py", "size": 6}

    listing = workspace.execute("file_list", {})
    assert listing["files"][0]["path"] == "app/x.py"

    read = workspace.execute("file_read", {"path": "app/x.py"})
    assert read["content"] == "x = 1\n"


def test_read_missing_file(tmp_path):
    workspace = Workspace(tmp_path)
    with pytest.raises(AppError) as exc:
        workspace.read_text("nope.py")
    assert exc.value.code == "file_not_found"
