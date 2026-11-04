"""日志初始化：开发环境输出到控制台，格式统一，便于后续接入文件/ELK。"""

from __future__ import annotations

import logging
import sys

from app.core.config import Settings

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"
_DATEFMT = "%H:%M:%S"


def setup_logging(settings: Settings) -> None:
    level = logging.DEBUG if settings.debug else logging.INFO

    # Windows 控制台/重定向默认可能是 GBK，统一成 UTF-8，避免中文日志乱码
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # 第三方库降噪
    for name in ("httpx", "httpcore", "openai", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(level)
