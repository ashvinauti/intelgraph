from __future__ import annotations

import json
from typing import Any

from intelgraph.core.orchestrator.queue_interface import TaskQueue
from intelgraph.core.orchestrator.task import Task, TaskStatus

try:
    import redis as redis_lib

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


class RedisTaskQueue(TaskQueue):
    _PENDING_KEY = "intelgraph:tasks:pending"
    _TASK_KEY_PREFIX = "intelgraph:tasks:data:"

    def __init__(
        self, host: str = "localhost", port: int = 6379, db: int = 0, password: str = ""
    ) -> None:
        if not HAS_REDIS:
            raise ImportError(
                "redis is required for RedisTaskQueue. Install it with: pip install redis"
            )
        self._client = redis_lib.Redis(host=host, port=port, db=db, password=password)

    def enqueue(self, task: Task) -> None:
        key = self._TASK_KEY_PREFIX + task.id
        self._client.hset(key, mapping={"json": self._serialize(task), "status": task.status.value})
        self._client.lpush(self._PENDING_KEY, task.id)

    def dequeue(self) -> Task | None:
        result = self._client.brpoplpush(
            self._PENDING_KEY, self._PENDING_KEY + ":processing", timeout=1
        )
        if result is None:
            return None
        tid = result.decode() if isinstance(result, bytes) else result
        key = self._TASK_KEY_PREFIX + tid
        raw = self._client.hget(key, "json")
        if raw is None:
            self._client.lrem(self._PENDING_KEY + ":processing", 1, tid)
            return None
        task = self._deserialize(raw)
        if task.status == TaskStatus.PENDING:
            task.transition(TaskStatus.RUNNING)
            self._client.hset(key, "status", task.status.value)
            self._client.hset(key, "json", self._serialize(task))
            self._client.lrem(self._PENDING_KEY + ":processing", 1, tid)
            return task
        self._client.lrem(self._PENDING_KEY + ":processing", 1, tid)
        return None

    def complete(self, task_id: str) -> None:
        key = self._TASK_KEY_PREFIX + task_id
        raw = self._client.hget(key, "json")
        if raw:
            task = self._deserialize(raw)
            task.transition(TaskStatus.COMPLETED)
            self._client.hset(key, "status", task.status.value)
            self._client.hset(key, "json", self._serialize(task))

    def fail(self, task_id: str, error: str) -> None:
        key = self._TASK_KEY_PREFIX + task_id
        raw = self._client.hget(key, "json")
        if raw:
            task = self._deserialize(raw)
            task.error = error
            task.transition(TaskStatus.FAILED)
            self._client.hset(key, "status", task.status.value)
            self._client.hset(key, "json", self._serialize(task))
            self._client.hset(key, "error", error)

    def retry(self, task: Task) -> None:
        key = self._TASK_KEY_PREFIX + task.id
        task.transition(TaskStatus.PENDING)
        self._client.hset(key, "json", self._serialize(task))
        self._client.hset(key, "status", task.status.value)
        self._client.hset(key, "error", "")
        self._client.lpush(self._PENDING_KEY, task.id)

    def get(self, task_id: str) -> Task | None:
        key = self._TASK_KEY_PREFIX + task_id
        raw = self._client.hget(key, "json")
        if raw is None:
            return None
        return self._deserialize(raw)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        keys = self._client.keys(self._TASK_KEY_PREFIX + "*")
        tasks: list[Task] = []
        for k in keys:
            raw = self._client.hget(k, "json")
            if raw:
                t = self._deserialize(raw)
                if status is None or t.status.value == status:
                    tasks.append(t)
        return [t.to_dict() for t in sorted(tasks, key=lambda x: x.created_at)]

    def metrics(self) -> dict[str, int]:
        pending = self._client.llen(self._PENDING_KEY) or 0
        keys = self._client.keys(self._TASK_KEY_PREFIX + "*")
        running = 0
        completed = 0
        failed = 0
        for k in keys:
            s = self._client.hget(k, "status")
            if s:
                sv = s.decode() if isinstance(s, bytes) else s
                if sv == TaskStatus.RUNNING.value:
                    running += 1
                elif sv == TaskStatus.COMPLETED.value:
                    completed += 1
                elif sv == TaskStatus.FAILED.value:
                    failed += 1
        return {
            "queue_pending": pending,
            "queue_running": running,
            "queue_completed": completed,
            "queue_failed": failed,
        }

    def _serialize(self, task: Task) -> str:
        return json.dumps(
            {
                "id": task.id,
                "type": task.type.value,
                "payload": task.payload.hex(),
                "status": task.status.value,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "error": task.error,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
        )

    def _deserialize(self, raw: str | bytes) -> Task:
        if isinstance(raw, bytes):
            raw = raw.decode()
        data = json.loads(raw)
        t = Task.__new__(Task)
        t.id = data["id"]
        from intelgraph.core.orchestrator.task import TaskType

        t.type = TaskType(data["type"])
        t.payload = bytes.fromhex(data["payload"]) if data.get("payload") else b""
        t.status = TaskStatus(data["status"])
        t.retry_count = data["retry_count"]
        t.max_retries = data["max_retries"]
        t.error = data.get("error")
        t.created_at = data["created_at"]
        t.updated_at = data["updated_at"]
        return t
