from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from intelgraph.core.orchestrator.task import Task


class TaskQueue(ABC):
    @abstractmethod
    def enqueue(self, task: Task) -> None: ...

    @abstractmethod
    def dequeue(self) -> Task | None: ...

    @abstractmethod
    def complete(self, task_id: str) -> None: ...

    @abstractmethod
    def fail(self, task_id: str, error: str) -> None: ...

    @abstractmethod
    def retry(self, task: Task) -> None: ...

    @abstractmethod
    def get(self, task_id: str) -> Task | None: ...

    @abstractmethod
    def list(self, status: str | None = None) -> list[dict[str, Any]]: ...

    def metrics(self) -> dict[str, int]:
        return {}
