from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import ulid


class TaskType(Enum):
    COLLECT_ENTITY = "collect_entity"
    VERIFY_ENTITY = "verify_entity"
    GENERATE_REPORT = "generate_report"
    BULK_IMPORT = "bulk_import"


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.FAILED},
    TaskStatus.RUNNING: {TaskStatus.PENDING, TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
}


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(ulid.new()))
    type: TaskType = TaskType.COLLECT_ENTITY
    payload: bytes = b""
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def transition(self, new_status: TaskStatus) -> None:
        allowed = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            msg = f"Invalid transition: {self.status.value} -> {new_status.value}"
            raise ValueError(msg)
        self.status = new_status
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
