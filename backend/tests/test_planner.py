"""队长拆解 → 解析校验 → 顺序执行。"""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.orchestration.planner import parse_task_plan

FENCED = """拆解：先需求、再设计、最后实现。

```json
{
  "tasks": [
    {"id": "T1", "title": "需求", "goal": "写需求", "owner": "product_manager"},
    {"id": "T2", "title": "设计", "goal": "写设计", "owner": "architect", "depends_on": ["T1"]}
  ],
  "risks": ["无"]
}
```
"""

RAW = '{"tasks": [{"id": "A", "title": "A", "goal": "a", "owner": "developer"}]}'


def test_parse_fenced_plan():
    tasks = parse_task_plan(FENCED)
    assert [task.id for task in tasks] == ["T1", "T2"]
    assert tasks[1].depends_on == ["T1"]


def test_parse_raw_object():
    tasks = parse_task_plan(RAW)
    assert tasks[0].owner == "developer"


def test_parse_failure():
    with pytest.raises(AppError) as exc:
        parse_task_plan("抱歉，我无法拆解这个需求。")
    assert exc.value.code == "plan_parse_failed"


def test_parse_invalid_task():
    bad = '{"tasks": [{"id": "T1", "title": "缺 owner", "goal": "x"}]}'
    with pytest.raises(AppError) as exc:
        parse_task_plan(bad)
    assert exc.value.code == "plan_invalid_task"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def test_plan_endpoint(client):
    resp = client.post("/api/v1/runs/plan", json={"goal": "做一个学生成绩管理系统"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tasks"]) == 5
    assert body["order"] == ["T1", "T2", "T3", "T4", "T5"]
    assert "MOCK" in body["raw"]
    assert body["usage"]["total_tokens"] > 0


def test_run_from_goal(client):
    resp = client.post("/api/v1/runs?wait=true", json={"goal": "做一个学生成绩管理系统"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["plan_source"] == "captain"
    assert body["planning_ms"] is not None
    assert [task["spec"]["id"] for task in body["tasks"]] == ["T1", "T2", "T3", "T4", "T5"]
    assert all(task["status"] == "completed" for task in body["tasks"])


def test_run_requires_tasks_or_goal(client):
    resp = client.post("/api/v1/runs", json={})
    assert resp.status_code == 422
