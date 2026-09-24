from __future__ import annotations

import threading
from typing import Any

from intelgraph.core.orchestrator.queue_interface import TaskQueue
from intelgraph.core.orchestrator.task import Task, TaskStatus


class InMemoryTaskQueue(TaskQueue):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._pending: list[str] = []

    def enqueue(self, task: Task) -> None:
        with self._lock:
            self._tasks[task.id] = task
            self._pending.append(task.id)

    def dequeue(self) -> Task | None:
        with self._lock:
            while self._pending:
                tid = self._pending.pop(0)
                t = self._tasks.get(tid)
                if t is not None and t.status == TaskStatus.PENDING:
                    t.transition(TaskStatus.RUNNING)
                    return t
        return None

    def complete(self, task_id: str) -> None:
        with self._lock:
            t = self._tasks.get(task_id)
            if t is not None:
                t.transition(TaskStatus.COMPLETED)

    def fail(self, task_id: str, error: str) -> None:
        with self._lock:
            t = self._tasks.get(task_id)
            if t is not None:
                t.error = error
                t.transition(TaskStatus.FAILED)

    def retry(self, task: Task) -> None:
        with self._lock:
            task.transition(TaskStatus.PENDING)
            self._tasks[task.id] = task
            self._pending.append(task.id)

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status.value == status]
        return [t.to_dict() for t in sorted(tasks, key=lambda x: x.created_at)]

    def metrics(self) -> dict[str, int]:
        with self._lock:
            pending = sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING)
            running = sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING)
            completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
            failed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)
        return {
            "queue_pending": pending,
            "queue_running": running,
            "queue_completed": completed,
            "queue_failed": failed,
        }
