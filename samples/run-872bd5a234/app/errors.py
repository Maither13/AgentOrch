"""错误码常量、统一异常类型与错误响应构造器。

本模块不依赖 FastAPI，可被纯函数层（service.py）安全引用。
追溯：F2, AC13。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ErrorCode:
    """错误码常量（取值与需求 4.1 错误码表一致）。"""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    INVALID_JSON = "INVALID_JSON"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    RESULT_NOT_FINITE = "RESULT_NOT_FINITE"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    #: 错误码 -> HTTP 状态码映射
    HTTP_STATUS: Dict[str, int] = {
        INVALID_ARGUMENT: 400,
        INVALID_JSON: 400,
        UNSUPPORTED_MEDIA_TYPE: 415,
        RESULT_NOT_FINITE: 422,
        INTERNAL_ERROR: 500,
    }


class ApiError(Exception):
    """业务异常：携带错误码、可读消息与可选的 field / index 定位信息。

    routes 层抛出，main 层的异常处理器统一转换为 JSON 响应。
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        field: Optional[str] = None,
        index: Optional[int] = None,
        status_code: Optional[int] = None,
    ) -> None:
        if not isinstance(error_code, str) or not error_code:
            raise ValueError("error_code must be a non-empty string")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string")
        if field is not None and not isinstance(field, str):
            raise ValueError("field must be a string when provided")
        if index is not None and (isinstance(index, bool) or not isinstance(index, int)):
            raise ValueError("index must be an integer when provided")

        super().__init__(message)
        self.error_code: str = error_code
        self.message: str = message
        self.field: Optional[str] = field
        self.index: Optional[int] = index
        self.status_code: int = (
            status_code
            if status_code is not None
            else ErrorCode.HTTP_STATUS.get(error_code, 400)
        )

    def to_payload(self) -> Dict[str, Any]:
        """转换为响应体字典；未使用的可选键省略（设计 5.5）。"""
        payload: Dict[str, Any] = {
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.field is not None:
            payload["field"] = self.field
        if self.index is not None:
            payload["index"] = self.index
        return payload

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return (
            f"ApiError(error_code={self.error_code!r}, message={self.message!r}, "
            f"field={self.field!r}, index={self.index!r}, "
            f"status_code={self.status_code!r})"
        )


def error_response(
    error_code: str,
    message: str,
    *,
    field: Optional[str] = None,
    index: Optional[int] = None,
) -> Dict[str, Any]:
    """构造统一形状的错误响应体（AC13）。

    保证返回的字典至少包含非空的 ``error_code`` 与 ``message``。
    """
    if not isinstance(error_code, str) or not error_code:
        logger.error("error_response called with invalid error_code: %r", error_code)
        error_code = ErrorCode.INTERNAL_ERROR
    if not isinstance(message, str) or not message.strip():
        logger.error("error_response called with empty message for %s", error_code)
        message = "unexpected error"

    payload: Dict[str, Any] = {"error_code": error_code, "message": message}
    if field is not None:
        payload["field"] = field
    if index is not None:
        payload["index"] = index
    return payload
