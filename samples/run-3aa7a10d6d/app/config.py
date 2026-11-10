"""应用配置（横切模块，不依赖任何业务模块）。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

DEFAULT_AUTH_TOKENS: Dict[str, Dict[str, Optional[str]]] = {
    "token-admin": {"role": "admin", "student_id": None},
    "token-teacher": {"role": "teacher", "student_id": None},
    "token-student-1": {"role": "student", "student_id": "stu-1"},
    "token-student-2": {"role": "student", "student_id": "stu-2"},
}


@dataclass(frozen=True)
class Settings:
    """运行期配置。"""

    database_url: str = "sqlite:///./school.db"
    auth_tokens: Dict[str, Dict[str, Optional[str]]] = field(
        default_factory=lambda: dict(DEFAULT_AUTH_TOKENS)
    )
    pass_line_ratio: float = 0.6
    api_prefix: str = "/api/v1"
    echo_sql: bool = False


def _parse_tokens(raw: Optional[str]) -> Dict[str, Dict[str, Optional[str]]]:
    """解析 AUTH_TOKENS 环境变量（JSON 对象：token -> {role, student_id}）。"""
    if not raw:
        return dict(DEFAULT_AUTH_TOKENS)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AUTH_TOKENS 不是合法 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("AUTH_TOKENS 必须是 JSON 对象")
    tokens: Dict[str, Dict[str, Optional[str]]] = {}
    for token, payload in parsed.items():
        if not isinstance(payload, dict) or "role" not in payload:
            raise ValueError(f"AUTH_TOKENS[{token!r}] 必须包含 role 字段")
        role = payload["role"]
        if role not in ("admin", "teacher", "student"):
            raise ValueError(f"AUTH_TOKENS[{token!r}].role 非法: {role!r}")
        student_id = payload.get("student_id")
        if role == "student" and not student_id:
            raise ValueError(f"AUTH_TOKENS[{token!r}] 学生角色必须绑定 student_id")
        tokens[str(token)] = {"role": role, "student_id": student_id}
    return tokens


def load_settings() -> Settings:
    """从环境变量加载配置。"""
    raw_tokens = os.getenv("AUTH_TOKENS")
    ratio_raw = os.getenv("PASS_LINE_RATIO", "0.6")
    try:
        ratio = float(ratio_raw)
    except ValueError as exc:
        raise ValueError(f"PASS_LINE_RATIO 非法: {ratio_raw!r}") from exc
    if not 0 < ratio <= 1:
        raise ValueError("PASS_LINE_RATIO 必须在 (0, 1] 区间")
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./school.db"),
        auth_tokens=_parse_tokens(raw_tokens),
        pass_line_ratio=ratio,
        api_prefix=os.getenv("API_PREFIX", "/api/v1"),
        echo_sql=os.getenv("SQL_ECHO", "0") == "1",
    )


settings = load_settings()
