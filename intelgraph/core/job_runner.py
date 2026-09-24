import queue
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class JobStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class Job:
    job_id: str
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    result: Any = None
    error: str | None = None


class JobHandler(ABC):
    @abstractmethod
    def handle(self, job: Job) -> Any: ...


class JobRunner:
    def __init__(self, max_workers: int = 4, queue_size: int = 100) -> None:
        self._queue: queue.Queue[Job] = queue.Queue(maxsize=queue_size)
        self._handlers: dict[str, JobHandler] = {}
        self._workers: list[threading.Thread] = []
        self._max_workers = max_workers
        self._stop_event = threading.Event()

    def register(self, name: str, handler: JobHandler) -> None:
        self._handlers[name] = handler

    def submit(self, job: Job) -> None:
        self._queue.put(job)
        logger.debug("job submitted", job_id=job.job_id, name=job.name)

    def start(self) -> None:
        self._stop_event.clear()
        for _ in range(self._max_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            self._workers.append(t)
        logger.info("job runner started", workers=self._max_workers)

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        for t in self._workers:
            t.join(timeout=timeout)
        logger.info("job runner stopped")

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            handler = self._handlers.get(job.name)
            if handler is None:
                job.status = JobStatus.FAILED
                job.error = f"no handler registered for '{job.name}'"
                logger.warning("no handler for job", job_id=job.job_id, name=job.name)
                continue

            job.status = JobStatus.RUNNING
            try:
                job.result = handler.handle(job)
                job.status = JobStatus.COMPLETED
                logger.debug("job completed", job_id=job.job_id, name=job.name)
            except Exception as e:
                job.status = JobStatus.FAILED
                job.error = str(e)
                logger.error("job failed", job_id=job.job_id, name=job.name, error=str(e))
