"""pytest 公共夹具：默认走 mock，不产生真实请求。"""

from __future__ import annotations

import os

# 必须在 import app 之前设置
os.environ["LLM_MOCK"] = "true"
os.environ["DEEPSEEK_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
