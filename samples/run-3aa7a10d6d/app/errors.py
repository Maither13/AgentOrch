"""统一错误码与异常（横切模块）。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    STUDENT_NOT_FOUND = "STUDENT_NOT_FOUND"
    COURSE_NOT_FOUND = "COURSE_NOT_FOUND"
    SCORE_NOT_FOUND = "SCORE_NOT_FOUND"
    STUDENT_NO_DUPLICATED = "STUDENT_NO_DUPLICATED"
    COURSE_CODE_DUPLICATED = "COURSE_CODE_DUPLICATED"
    SCORE_DUPLICATED = "SCORE_DUPLICATED"
    SCORE_OUT_OF_RANGE = "SCORE_OUT_OF_RANGE"
    STUDENT_HAS_SCORES = "STUDENT_HAS_SCORES"
    COURSE_HAS_SCORES = "COURSE_HAS_SCORES"


# 错误码 -> HTTP 状态（§4.6 全量硬编码）
ERROR_HTTP_STATUS: Dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.STUDENT_NOT_FOUND: 404,
    ErrorCode.COURSE_NOT_FOUND: 404,
    ErrorCode.SCORE_NOT_FOUND: 404,
    ErrorCode.STUDENT_NO_DUPLICATED: 409,
    ErrorCode.COURSE_CODE_DUPLICATED: 409,
    ErrorCode.SCORE_DUPLICATED: 409,
    ErrorCode.SCORE_OUT_OF_RANGE: 400,
    ErrorCode.STUDENT_HAS_SCORES: 409,
    ErrorCode.COURSE_HAS_SCORES: 409,
}

DEFAULT_MESSAGES: Dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "请求字段校验失败",
    ErrorCode.UNAUTHORIZED: "未提供或无效凭证",
    ErrorCode.FORBIDDEN: "角色无权访问该资源",
    ErrorCode.STUDENT_NOT_FOUND: "学生不存在或已删除",
    ErrorCode.COURSE_NOT_FOUND: "课程不存在或已删除",
    ErrorCode.SCORE_NOT_FOUND: "成绩不存在或已删除",
    ErrorCode.STUDENT_NO_DUPLICATED: "学号重复",
    ErrorCode.COURSE_CODE_DUPLICATED: "课程编号重复",
    ErrorCode.SCORE_DUPLICATED: "同一学生同一课程同一学期已有成绩",
    ErrorCode.SCORE_OUT_OF_RANGE: "成绩超出 0 至课程满分范围",
    ErrorCode.STUDENT_HAS_SCORES: "学生仍有成绩记录，禁止删除",
    ErrorCode.COURSE_HAS_SCORES: "课程仍有成绩记录，禁止删除",
}


class AppError(Exception):
    """业务异常，由 main.py 的异常处理器转换为统一错误响应。"""

    def __init__(
        self,
        code: ErrorCode,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        http_status: Optional[int] = None,
    ) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGES[code]
        self.details = details
        self.http_status = http_status or ERROR_HTTP_STATUS[code]
        super().__init__(f"{self.code.value}: {self.message}")


def validation_error(field: str, reason: str) -> AppError:
    """构造字段级校验错误。"""
    return AppError(
        ErrorCode.VALIDATION_ERROR,
        message=f"字段 {field} 校验失败: {reason}",
        details={"field": field, "reason": reason},
    )
