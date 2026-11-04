"""本地开发启动脚本：python run.py"""

import uvicorn

from app.core.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "dev",
        reload_dirs=["app"],
        log_level="info",
    )
