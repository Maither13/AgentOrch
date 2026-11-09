"""DSML 文本工具调用兜底解析。"""

from __future__ import annotations

from app.llm.dsml import parse_dsml_calls, strip_dsml

SAMPLE = """先写文件，再说明。

<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="file_write">
<｜｜DSML｜｜ parameter name="path" string="true">app/main.py</｜｜DSML｜｜ parameter>
<｜｜DSML｜｜ parameter name="content" string="true">print("hi")
</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
<｜｜DSML｜｜ invoke name="file_read">
<｜｜DSML｜｜ parameter name="path" string="true">app/main.py</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>

结束。
"""


def test_parse_multiple_calls():
    calls = parse_dsml_calls(SAMPLE)
    assert [name for name, _ in calls] == ["file_write", "file_read"]
    path, content = calls[0][1]["path"], calls[0][1]["content"]
    assert path == "app/main.py"
    assert content.startswith('print("hi")')


def test_strip_dsml():
    cleaned = strip_dsml(SAMPLE)
    assert "DSML" not in cleaned
    assert "先写文件" in cleaned
    assert "结束。" in cleaned


def test_plain_text_returns_empty():
    assert parse_dsml_calls("普通回复，没有任何工具调用") == []
    assert strip_dsml("普通回复") == "普通回复"
