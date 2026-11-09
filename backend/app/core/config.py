"""应用配置。

所有可调参数集中在这里，通过 backend/.env 或环境变量覆盖。
字段名即环境变量名（不区分大小写），例如 DEEPSEEK_API_KEY。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录，用于定位 .env
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- 应用 ----------
    app_name: str = "AgentOrch"
    app_version: str = "0.1.0"
    environment: str = "dev"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8000
    api_prefix: str = "/api/v1"
    # 逗号分隔，预留给后续 Vue 前端开发服务器
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # 启动时装配的团队配置（app/agents/teams/<id>.json）
    default_team: str = "software_team"

    # ---------- 大模型 ----------
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_reasoner_model: str = "deepseek-reasoner"
    llm_temperature: float = 0.7
    llm_max_tokens: int | None = None
    llm_timeout: float = 120.0
    llm_max_retries: int = 2
    # 离线演示/单测开关：不发起真实请求
    llm_mock: bool = False
    # Mock 模式下让评审固定驳回，用于演示 Self-Loop 轮次
    mock_review_reject: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def llm_mode(self) -> str:
        """live（真实调用） / mock（本地模拟） / unconfigured（缺 Key）"""
        if self.llm_mock:
            return "mock"
        if self.deepseek_api_key:
            return "live"
        return "unconfigured"


@lru_cache
def get_settings() -> Settings:
    return Settings()
