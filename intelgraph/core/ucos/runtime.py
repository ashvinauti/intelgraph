from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class UnifiedExecutionResult:
    execution_id: str
    goal: str
    steps: list[dict[str, Any]]
    success: bool
    outputs: dict[str, Any]
    duration_ms: float
    error: str
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "goal": self.goal,
            "step_count": len(self.steps),
            "success": self.success,
            "output_summary": str(list(self.outputs.keys()))[:200],
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
        }


class UnifiedExecutionRuntime:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._history: list[UnifiedExecutionResult] = []
        self._task_queue: list[dict[str, Any]] = []
        self._audit: list[dict[str, Any]] = []

    def execute(
        self, goal: str, steps: list[dict[str, Any]] | None = None
    ) -> UnifiedExecutionResult:
        start = time.perf_counter()
        steps = steps or [{"action": "default", "params": {"goal": goal}}]
        success = True
        error = ""
        outputs: dict[str, Any] = {}

        for step in steps:
            action = step.get("action", "analyze")
            params = step.get("params", {})
            self._audit.append(
                {
                    "action": action,
                    "params": params,
                    "timestamp": time.time(),
                    "status": "executing",
                }
            )
            result = self._simulate_step(action, params)
            outputs[action] = result
            self._audit[-1]["status"] = "completed" if result.get("success") else "failed"
            if not result.get("success"):
                error = result.get("error", "")
                if self._cfg.get("stop_on_failure", True):
                    success = False
                    break

        elapsed = (time.perf_counter() - start) * 1000
        result = UnifiedExecutionResult(
            execution_id=f"ue_{uuid.uuid4().hex[:12]}",
            goal=goal,
            steps=steps,
            success=success,
            outputs=outputs,
            duration_ms=elapsed,
            error=error,
            created_at=time.time(),
        )
        self._history.append(result)
        return result

    def _simulate_step(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "tool_call":
            return {"success": True, "output": f"Executed {params.get('tool', 'unknown')}"}
        if action == "database_query":
            return {"success": True, "rows": 1}
        if action == "file_operation":
            return {"success": True, "path": params.get("path", "/tmp")}
        return {"success": True, "output": f"Completed {action}"}

    def rollback(self, execution_id: str) -> bool:
        for result in self._history:
            if result.execution_id == execution_id and result.success:
                result.success = False
                result.error = "ROLLED_BACK"
                return True
        return False

    def enqueue(self, task: dict[str, Any]) -> str:
        task_id = f"tq_{uuid.uuid4().hex[:12]}"
        task["task_id"] = task_id
        task["enqueued_at"] = time.time()
        task["status"] = "pending"
        self._task_queue.append(task)
        return task_id

    def dequeue(self) -> dict[str, Any] | None:
        for task in self._task_queue:
            if task.get("status") == "pending":
                task["status"] = "running"
                task["started_at"] = time.time()
                return task
        return None

    def complete_task(self, task_id: str, success: bool) -> bool:
        for task in self._task_queue:
            if task.get("task_id") == task_id:
                task["status"] = "completed" if success else "failed"
                task["completed_at"] = time.time()
                return True
        return False

    def get_task_queue(self) -> list[dict[str, Any]]:
        return list(self._task_queue)

    def get_history(self, limit: int = 100) -> list[UnifiedExecutionResult]:
        return self._history[-limit:]

    def get_audit(self) -> list[dict[str, Any]]:
        return list(self._audit)
