"""领域异常：与 HTTP 解耦，由 main.py 统一转换成响应。"""

from __future__ import annotations


class AppError(Exception):
    """所有业务异常的基类。"""

    def __init__(self, message: str, *, status_code: int = 500, code: str = "internal_error") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class LLMError(AppError):
    """大模型调用失败（鉴权、限流、超时、上游 5xx 等）。"""

    def __init__(self, message: str, *, status_code: int = 502, code: str = "llm_error") -> None:
        super().__init__(message, status_code=status_code, code=code)
