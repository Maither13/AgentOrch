"""验收结论解析：执行状态之外的第二维度。"""

from __future__ import annotations

from app.orchestration.acceptance import parse_review
from app.orchestration.models import AcceptanceStatus


def test_parse_reject():
    status, verdict, summary, blockers = parse_review(
        "# 评审记录\n\n## 总体结论\n\n**驳回。** 存在 P0 问题。\n\n"
        "## 阻断项清单\n1. 缺少输入校验\n2. 未处理数据库异常\n"
    )
    assert status is AcceptanceStatus.rejected
    assert verdict == "驳回"
    assert "驳回" in summary
    assert blockers
    assert "缺少输入校验" in blockers[0]


def test_parse_pass():
    status, verdict, _, _ = parse_review("## 总体结论\n\n**通过**。所有验收标准均有证据。")
    assert status is AcceptanceStatus.passed
    assert verdict == "通过"


def test_parse_conditional_pass():
    status, verdict, _, _ = parse_review("总体结论：有条件通过，需补充 P1 用例。")
    assert status is AcceptanceStatus.passed
    assert verdict == "有条件通过"


def test_parse_missing_conclusion():
    status, verdict, _, _ = parse_review("这是一段没有结论的评审。")
    assert status is AcceptanceStatus.pending
    assert verdict is None


def test_parse_empty():
    status, verdict, _, _ = parse_review("")
    assert status is AcceptanceStatus.pending
    assert verdict is None
