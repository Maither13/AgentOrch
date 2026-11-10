"""纯计算逻辑层：不含任何 HTTP 概念，不 import FastAPI。

设计决策：AC1–AC5 的算术语义（尤其 AC5 的 IEEE 754 严格相等）可脱离 HTTP 单测；
F7 的有限性检查只有一处实现。
追溯：F1, F3, F6, F7。
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Sequence

from app.errors import ApiError, ErrorCode

logger = logging.getLogger(__name__)

#: 批量接口 items 长度上限（需求 4.3）
MAX_BATCH_SIZE = 100


def is_number(value: Any) -> bool:
    """判断是否为合法 JSON 数值。

    陷阱（C5 / AC9）：Python 中 ``isinstance(True, int)`` 为 True，
    因此必须**先**排除 bool，再判断 int/float。
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))


def ensure_finite(result: float, *, index: int | None = None) -> float:
    """校验计算结果为有限数（AC19 / F7）。

    ``math.isfinite`` 对 NaN 与 ±Infinity 均返回 False。
    非有限时抛 ``ApiError(RESULT_NOT_FINITE)``，HTTP 状态 422。
    """
    if not math.isfinite(result):
        logger.warning("non-finite result detected: %r (index=%r)", result, index)
        raise ApiError(
            ErrorCode.RESULT_NOT_FINITE,
            "result is not a finite number (NaN or Infinity)",
            index=index,
        )
    return result


def add(a: float, b: float) -> float:
    """返回 a + b。

    严格 IEEE 754 双精度语义（C2 / AC5）：**禁止** round()、Decimal、
    math.isclose，直接相加。
    """
    if not is_number(a):
        raise ApiError(
            ErrorCode.INVALID_ARGUMENT,
            "field 'a' must be a JSON number",
            field="a",
        )
    if not is_number(b):
        raise ApiError(
            ErrorCode.INVALID_ARGUMENT,
            "field 'b' must be a JSON number",
            field="b",
        )
    return a + b


def add_checked(a: float, b: float) -> float:
    """add + 有限性检查的组合，供 routes 层直接使用。"""
    return ensure_finite(add(a, b))


def validate_pair(payload: Any, *, index: int | None = None) -> tuple[float, float]:
    """校验一个 {a, b} 对象并返回 (a, b)。

    校验顺序：对象类型 → 字段存在性/非 null（a 先于 b）→ 数值类型（排除 bool）。
    缺失字段与 null 走同一分支，field 取首个问题字段（AC6/AC7/AC10）。
    """
    if not isinstance(payload, dict):
        raise ApiError(
            ErrorCode.INVALID_ARGUMENT,
            "request body must be a JSON object with fields 'a' and 'b'",
            index=index,
        )

    values: Dict[str, float] = {}
    for name in ("a", "b"):
        if name not in payload:
            raise ApiError(
                ErrorCode.INVALID_ARGUMENT,
                f"field '{name}' is required",
                field=name,
                index=index,
            )
        value = payload[name]
        if value is None:
            raise ApiError(
                ErrorCode.INVALID_ARGUMENT,
                f"field '{name}' must not be null",
                field=name,
                index=index,
            )
        if not is_number(value):
            raise ApiError(
                ErrorCode.INVALID_ARGUMENT,
                f"field '{name}' must be a JSON number",
                field=name,
                index=index,
            )
        values[name] = value

    return values["a"], values["b"]


def add_batch(items: Sequence[Any]) -> List[float]:
    """批量加法（AC17/AC18）。

    逐元素复用同一套校验与 add，保持顺序；首个出错元素即返回，
    index 为 0-based。
    """
    if not isinstance(items, (list, tuple)):
        raise ApiError(
            ErrorCode.INVALID_ARGUMENT,
            "field 'items' must be an array",
            field="items",
        )
    if len(items) < 1 or len(items) > MAX_BATCH_SIZE:
        raise ApiError(
            ErrorCode.INVALID_ARGUMENT,
            f"field 'items' must contain between 1 and {MAX_BATCH_SIZE} elements",
            field="items",
        )

    results: List[float] = []
    for position, item in enumerate(items):
        a, b = validate_pair(item, index=position)
        results.append(ensure_finite(add(a, b), index=position))
    return results


__all__ = [
    "MAX_BATCH_SIZE",
    "is_number",
    "ensure_finite",
    "add",
    "add_checked",
    "validate_pair",
    "add_batch",
]
