"""运行记录存储（内存版）。

当前阶段不做持久化：进程重启后历史运行丢失，属于已知限制；
后续接 SQLite 时只需替换本文件的读写实现，接口保持不变。
"""

from __future__ import annotations

import asyncio
import uuid

from app.core.errors import AppError
from app.orchestration.models import RunState, RunStatus


class RunStore:
    def __init__(self, max_runs: int = 50) -> None:
        self._runs: dict[str, RunState] = {}
        self._max_runs = max_runs
        self._background: set[asyncio.Task] = set()

    def new_id(self) -> str:
        return f"run-{uuid.uuid4().hex[:10]}"

    def add(self, run: RunState) -> None:
        self._evict_if_needed()
        self._runs[run.id] = run

    def get(self, run_id: str) -> RunState:
        run = self._runs.get(run_id)
        if run is None:
            raise AppError(f"运行记录不存在：{run_id}", status_code=404, code="run_not_found")
        return run

    def list(self, limit: int = 20) -> list[RunState]:
        return list(reversed(list(self._runs.values())))[:limit]

    def track(self, task: asyncio.Task) -> None:
        """持有后台执行任务的引用，避免被 GC 回收。"""
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    def _evict_if_needed(self) -> None:
        if len(self._runs) < self._max_runs:
            return
        for run_id, run in list(self._runs.items()):
            if run.status in {
                RunStatus.completed,
                RunStatus.failed,
                RunStatus.rejected,
                RunStatus.needs_revision,
            }:
                self._runs.pop(run_id, None)
                return
