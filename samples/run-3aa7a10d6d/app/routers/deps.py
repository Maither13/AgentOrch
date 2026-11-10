"""路由层公共依赖：分页参数校验（AC28）。"""

from __future__ import annotations

from fastapi import Query

from app.errors import validation_error

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class Pagination:
    """分页参数容器，构造时完成范围校验。"""

    __slots__ = ("page", "page_size")

    def __init__(self, page: int, page_size: int) -> None:
        if page < 1:
            raise validation_error("page", "必须 >= 1")
        if page_size < 1 or page_size > MAX_PAGE_SIZE:
            raise validation_error("page_size", f"必须在 1 至 {MAX_PAGE_SIZE} 之间")
        self.page = page
        self.page_size = page_size


def pagination(
    page: int = Query(default=1, description="页码，最小 1"),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, description="每页条数，1-100"),
) -> Pagination:
    return Pagination(page=page, page_size=page_size)
