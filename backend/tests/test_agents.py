"""模块 1：Agent 定义、团队配置与单 Agent 试跑。"""

from __future__ import annotations

import json

import pytest

from app.agents.registry import load_team, load_team_file
from app.agents.tools import ToolPermissionError
from app.core.config import Settings
from app.core.errors import AppError
from app.llm.client import DeepSeekClient

EXPECTED_ROLES = ["captain", "product_manager", "architect", "developer", "tester", "reviewer"]


# --------------------------------------------------------------------------- #
# HTTP 接口
# --------------------------------------------------------------------------- #
def test_team_config(client):
    body = client.get("/api/v1/team").json()
    assert body["captain"] == "captain"
    assert [member["role"] for member in body["members"]] == EXPECTED_ROLES
    assert body["source"] == "software_team.json"


def test_list_roles(client):
    roles = client.get("/api/v1/agents/roles").json()
    assert [role["role"] for role in roles] == EXPECTED_ROLES
    assert all(role["allowed_tools"] for role in roles)


def test_list_tools(client):
    tools = client.get("/api/v1/agents/tools").json()
    names = {tool["name"] for tool in tools}
    assert {"task_plan", "file_write", "python_exec", "test_runner"} <= names
    by_name = {tool["name"]: tool for tool in tools}
    assert by_name["file_read"]["implemented"] is True
    assert by_name["python_exec"]["implemented"] is True
    assert by_name["shell_exec"]["implemented"] is False


def test_agent_detail(client):
    developer = client.get("/api/v1/agents/developer").json()
    tools = {tool["name"] for tool in developer["allowed_tools"]}
    assert {"file_write", "shell_exec"} <= tools
    assert len(developer["system_prompt"]) > 200


def test_captain_cannot_exec(client):
    captain = client.get("/api/v1/agents/captain").json()
    names = {tool["name"] for tool in captain["allowed_tools"]}
    assert "task_plan" in names
    assert "shell_exec" not in names


def test_unknown_agent(client):
    resp = client.get("/api/v1/agents/nobody")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "agent_not_found"


@pytest.mark.parametrize("role", EXPECTED_ROLES)
def test_run_each_agent(client, role):
    resp = client.post(f"/api/v1/agents/{role}/run", json={"task": "这是一次接口冒烟测试"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == role
    assert body["mode"] == "mock"
    assert "MOCK" in body["content"]


def test_run_with_context(client):
    resp = client.post(
        "/api/v1/agents/architect/run",
        json={"task": "设计表结构", "context": "需求文档 v1：学生成绩管理"},
    )
    assert resp.status_code == 200


def test_run_rejects_empty_task(client):
    resp = client.post("/api/v1/agents/captain/run", json={"task": ""})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# 团队配置校验
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def mock_llm() -> DeepSeekClient:
    return DeepSeekClient(Settings(llm_mock=True))


def _team_payload(**overrides):
    payload = {
        "id": "demo",
        "name": "演示团队",
        "captain": "captain",
        "members": [
            {"id": "captain", "role": "captain"},
            {"id": "developer", "role": "developer"},
        ],
    }
    payload.update(overrides)
    return payload


def _write_team(tmp_path, payload):
    path = tmp_path / "team.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_team_config_valid(mock_llm, tmp_path):
    team = load_team_file(mock_llm, _write_team(tmp_path, _team_payload()))
    assert team.captain.id == "captain"
    assert [agent.id for agent in team.ordered()] == ["captain", "developer"]


def test_team_config_unknown_role(mock_llm, tmp_path):
    payload = _team_payload(
        members=[{"id": "captain", "role": "captain"}, {"id": "dev", "role": "wizard"}]
    )
    with pytest.raises(AppError) as exc:
        load_team_file(mock_llm, _write_team(tmp_path, payload))
    assert exc.value.code == "team_config_invalid"


def test_team_config_captain_must_exist(mock_llm, tmp_path):
    payload = _team_payload(captain="ghost")
    with pytest.raises(AppError) as exc:
        load_team_file(mock_llm, _write_team(tmp_path, payload))
    assert exc.value.code == "team_config_invalid"


def test_team_config_captain_role_mismatch(mock_llm, tmp_path):
    payload = _team_payload(
        captain="developer",
        members=[{"id": "developer", "role": "developer"}],
    )
    with pytest.raises(AppError) as exc:
        load_team_file(mock_llm, _write_team(tmp_path, payload))
    assert exc.value.code == "team_config_invalid"


# --------------------------------------------------------------------------- #
# 角色本身
# --------------------------------------------------------------------------- #
def test_roles_have_distinct_prompts(mock_llm):
    team = load_team(mock_llm, "software_team")
    prompts = [agent.system_prompt for agent in team.ordered()]
    assert len(set(prompts)) == len(EXPECTED_ROLES)
    for agent in team.ordered():
        assert agent.allowed_tools
        assert len(agent.system_prompt) > 150


def test_tool_permission_guard(mock_llm):
    team = load_team(mock_llm, "software_team")
    captain = team.captain
    assert captain.can_use("task_plan")
    assert not captain.can_use("shell_exec")
    with pytest.raises(ToolPermissionError):
        captain.ensure_tools(["task_plan", "shell_exec"])
