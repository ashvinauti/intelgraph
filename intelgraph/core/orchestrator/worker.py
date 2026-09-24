from __future__ import annotations

import threading
import time

import structlog

from intelgraph.core.orchestrator.dispatcher import TaskDispatcher
from intelgraph.core.orchestrator.queue_interface import TaskQueue
from intelgraph.core.orchestrator.worker_registry import WorkerRegistry

logger = structlog.get_logger(__name__)


class TaskWorker:
    def __init__(
        self,
        queue: TaskQueue,
        dispatcher: TaskDispatcher,
        registry: WorkerRegistry | None = None,
        heartbeat_interval: float = 30.0,
    ) -> None:
        self._queue = queue
        self._dispatcher = dispatcher
        self._registry = registry or WorkerRegistry(heartbeat_interval=heartbeat_interval)
        self._heartbeat_interval = heartbeat_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._hb_thread: threading.Thread | None = None

    @property
    def worker_id(self) -> str:
        return self._registry.local_id

    def start(self) -> None:
        if self._thread is not None:
            return
        self._registry.register()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._hb_thread.start()
        logger.info("task worker started", worker_id=self.worker_id)

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        if self._hb_thread is not None:
            self._hb_thread.join(timeout=min(timeout or 5, 5))
            self._hb_thread = None
        self._registry.unregister()
        logger.info("task worker stopped", worker_id=self.worker_id)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            task = self._queue.dequeue()
            if task is None:
                time.sleep(1)
                continue
            try:
                self._dispatcher.dispatch(task)
                self._queue.complete(task.id)
                logger.debug("task completed", task_id=task.id, task_type=task.type.value)
            except Exception as e:
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    task.status = task.status
                    self._queue.retry(task)
                    logger.warning("task retry", task_id=task.id, retry=task.retry_count)
                else:
                    self._queue.fail(task.id, str(e))
                    logger.error("task failed", task_id=task.id, error=str(e))

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            self._registry.heartbeat()
            time.sleep(self._heartbeat_interval)
