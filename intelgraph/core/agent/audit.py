from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class AuditEntry:
    entry_id: str
    action_id: str
    agent_id: str
    task_id: str
    action_type: str
    description: str
    status: str
    risk_score: float
    duration_ms: float
    trace_id: str = ""
    error: str = ""
    timestamp: float = 0.0
    immutable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "action_id": self.action_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "action_type": self.action_type,
            "description": self.description,
            "status": self.status,
            "risk_score": round(self.risk_score, 4),
            "duration_ms": round(self.duration_ms, 2),
            "trace_id": self.trace_id,
            "error": self.error,
            "timestamp": self.timestamp,
            "immutable": self.immutable,
        }


class ExecutionAudit:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._max_entries = 100000

    def record(
        self,
        action_id: str,
        agent_id: str,
        task_id: str,
        action_type: str,
        description: str,
        status: str,
        risk_score: float,
        duration_ms: float,
        trace_id: str = "",
        error: str = "",
    ) -> AuditEntry:
        entry = AuditEntry(
            entry_id=f"aud_{uuid.uuid4().hex[:12]}",
            action_id=action_id,
            agent_id=agent_id,
            task_id=task_id,
            action_type=action_type,
            description=description,
            status=status,
            risk_score=risk_score,
            duration_ms=duration_ms,
            trace_id=trace_id,
            error=error,
            timestamp=time.time(),
            immutable=True,
        )
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]
        return entry

    def get(self, entry_id: str) -> AuditEntry | None:
        for e in self._entries:
            if e.entry_id == entry_id:
                return e
        return None

    def query(
        self,
        action_id: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        results = list(self._entries)
        if action_id:
            results = [e for e in results if e.action_id == action_id]
        if agent_id:
            results = [e for e in results if e.agent_id == agent_id]
        if task_id:
            results = [e for e in results if e.task_id == task_id]
        return results[-limit:]

    def reconstruct_execution_graph(self, task_id: str) -> list[dict[str, Any]]:
        entries = self.query(task_id=task_id)
        return [
            {
                "step": i,
                "action": e.action_type,
                "agent": e.agent_id,
                "status": e.status,
                "duration": e.duration_ms,
                "trace_id": e.trace_id,
            }
            for i, e in enumerate(entries)
        ]

    def failure_root_cause(self, task_id: str) -> dict[str, Any]:
        entries = self.query(task_id=task_id)
        failed = [e for e in entries if e.status == "failed"]
        if not failed:
            return {"task_id": task_id, "root_cause": "none", "failure_count": 0}
        return {
            "task_id": task_id,
            "root_cause": failed[0].error,
            "failure_count": len(failed),
            "first_failure": failed[0].to_dict(),
        }
