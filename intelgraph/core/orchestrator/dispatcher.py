from __future__ import annotations

from collections.abc import Callable
from typing import Any

from intelgraph.core.orchestrator.task import Task, TaskType


class TaskDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[TaskType, Callable[[Task], Any]] = {}

    def register(self, task_type: TaskType, handler: Callable[[Task], Any]) -> None:
        self._handlers[task_type] = handler

    def dispatch(self, task: Task) -> Any:
        handler = self._handlers.get(task.type)
        if handler is None:
            msg = f"No handler registered for task type: {task.type.value}"
            raise ValueError(msg)
        return handler(task)
