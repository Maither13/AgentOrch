"""鉴权依赖：静态 Bearer Token + 角色判定（F12 / AC26）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header

from app.config import settings
from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    token: str
    role: str
    student_id: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_teacher(self) -> bool:
        return self.role == "teacher"

    @property
    def is_student(self) -> bool:
        return self.role == "student"


def get_principal(authorization: Optional[str] = Header(default=None)) -> Principal:
    """解析 Authorization: Bearer <token>，无效则 401 UNAUTHORIZED。"""
    if not authorization:
        raise AppError(ErrorCode.UNAUTHORIZED, message="缺少 Authorization 请求头")
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AppError(ErrorCode.UNAUTHORIZED, message="Authorization 必须为 Bearer 方案")
    token = parts[1].strip()
    if not token:
        raise AppError(ErrorCode.UNAUTHORIZED, message="Bearer Token 为空")
    payload = settings.auth_tokens.get(token)
    if payload is None:
        logger.warning("收到未知 token 的请求")
        raise AppError(ErrorCode.UNAUTHORIZED, message="凭证无效")
    return Principal(token=token, role=str(payload["role"]), student_id=payload.get("student_id"))


def require_roles(*roles: str):
    """角色白名单依赖工厂。"""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise AppError(
                ErrorCode.FORBIDDEN,
                message=f"角色 {principal.role} 无权访问该资源",
                details={"required_roles": list(roles)},
            )
        return principal

    return _dep


require_admin = require_roles("admin")
require_staff = require_roles("admin", "teacher")


def ensure_student_self(principal: Principal, student_id: str) -> None:
    """学生角色只能访问本人数据（AC26）。"""
    if principal.is_student and principal.student_id != student_id:
        raise AppError(
            ErrorCode.FORBIDDEN,
            message="学生只能查询本人成绩",
            details={"student_id": student_id},
        )
