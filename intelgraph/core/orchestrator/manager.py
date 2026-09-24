from __future__ import annotations

from typing import Any

import structlog

from intelgraph.core.orchestrator.dispatcher import TaskDispatcher
from intelgraph.core.orchestrator.queue import InMemoryTaskQueue
from intelgraph.core.orchestrator.queue_interface import TaskQueue
from intelgraph.core.orchestrator.task import Task, TaskType
from intelgraph.core.orchestrator.worker import TaskWorker
from intelgraph.core.orchestrator.worker_registry import WorkerRegistry

logger = structlog.get_logger(__name__)


class TaskManager:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._queue = _create_queue(cfg)
        self._dispatcher = TaskDispatcher()
        hb_interval = float(cfg.get("worker", {}).get("heartbeat_interval", 30))
        registry = WorkerRegistry(heartbeat_interval=hb_interval)
        self._worker = TaskWorker(
            self._queue, self._dispatcher, registry=registry, heartbeat_interval=hb_interval
        )
        self._registry = registry

    @property
    def queue(self) -> TaskQueue:
        return self._queue

    @property
    def dispatcher(self) -> TaskDispatcher:
        return self._dispatcher

    @property
    def registry(self) -> WorkerRegistry:
        return self._registry

    @property
    def worker_id(self) -> str:
        return self._worker.worker_id

    def initialize(self) -> None:
        self._worker.start()

    def shutdown(self) -> None:
        self._worker.stop()

    def enqueue(self, task_type: str, payload: bytes = b"") -> Task:
        try:
            tt = TaskType(task_type)
        except ValueError:
            msg = f"Unknown task type: {task_type}"
            raise ValueError(msg)
        task = Task(type=tt, payload=payload)
        self._queue.enqueue(task)
        logger.debug("task enqueued", task_id=task.id, task_type=task_type)
        return task

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        t = self._queue.get(task_id)
        return t.to_dict() if t else None

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        return self._queue.list(status=status)


def _create_queue(config: dict[str, Any]) -> TaskQueue:
    tq = config.get("task_queue", {})
    backend = tq.get("backend", "in_memory")
    if backend == "redis":
        host = tq.get("host", "localhost")
        port = int(tq.get("port", 6379))
        db = int(tq.get("db", 0))
        password = tq.get("password", "")
        from intelgraph.core.orchestrator.redis_queue import RedisTaskQueue

        return RedisTaskQueue(host=host, port=port, db=db, password=password)
    return InMemoryTaskQueue()
