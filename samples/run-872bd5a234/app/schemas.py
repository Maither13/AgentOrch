"""请求/响应实体定义。

设计决策 R2：请求体不使用 pydantic 模型做校验（pydantic 会把 "1" 强转为 1.0、
把 true 转成 1.0，违反 AC8/AC9），请求体在 routes 层用 Request 手动取 JSON 并
自定义校验；本模块只承载**响应**模型与实体字段的文档化定义。
追溯：需求 5 节实体表。
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.errors import ErrorCode


class AddRequest(BaseModel):
    """实体：AddRequest（仅作文档/类型参考，不用于请求校验）。

    字段约束：a、b 均为必填 JSON 数值，不接受字符串/布尔/null。
    """

    a: float = Field(..., description="加数 a，必须是 JSON 数值")
    b: float = Field(..., description="加数 b，必须是 JSON 数值")


class AddResponse(BaseModel):
    """实体：AddResponse（AC1/AC2/AC3）。"""

    result: float = Field(..., description="a + b 的结果")
    a: float = Field(..., description="回显请求中的 a")
    b: float = Field(..., description="回显请求中的 b")


class ErrorResponse(BaseModel):
    """实体：ErrorResponse（AC13）。

    field / index 为可选键，未使用时省略（设计 5.5）。
    """

    error_code: str = Field(..., description="错误码，取值见 ErrorCode")
    message: str = Field(..., description="非空可读说明")
    field: Optional[str] = Field(None, description="参数校验失败时的字段名")
    index: Optional[int] = Field(None, description="批量接口中出错元素下标")


class HealthResponse(BaseModel):
    """实体：HealthResponse（AC16）。"""

    status: str = Field(default="ok", description='固定为 "ok"')


class BatchRequest(BaseModel):
    """实体：BatchRequest（仅作文档/类型参考，不用于请求校验）。

    约束：items 为 array<object>，长度 1–100，每个元素含 a、b。
    """

    items: List[AddRequest] = Field(..., description="待计算的元素数组，长度 1–100")


class BatchResponse(BaseModel):
    """实体：BatchResponse（AC17）。"""

    results: List[float] = Field(..., description="与 items 等长、同序的结果数组")


__all__ = [
    "AddRequest",
    "AddResponse",
    "ErrorResponse",
    "HealthResponse",
    "BatchRequest",
    "BatchResponse",
    "ErrorCode",
]
