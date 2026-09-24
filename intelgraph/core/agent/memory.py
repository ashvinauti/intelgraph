from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryRecord:
    memory_id: str
    entity_id: str
    key: str
    value: Any
    outcome: str
    created_at: float = 0.0
    ttl: float = 0.0

    def is_expired(self) -> bool:
        if self.ttl == 0:
            return False
        if self.ttl < 0:
            return True
        return time.time() > self.created_at + self.ttl


@dataclass
class BehaviorRecord:
    record_id: str
    agent_id: str
    action: str
    outcome: str
    duration_ms: float
    context: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "outcome": self.outcome,
            "duration_ms": round(self.duration_ms, 2),
        }


class ExecutionMemory:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        default_ttl = self._cfg.get("memory_ttl", 86400 * 30)
        self._default_ttl = default_ttl
        self._records: dict[str, list[MemoryRecord]] = defaultdict(list)
        self._behaviors: list[BehaviorRecord] = []
        self._knowledge: dict[str, float] = {}
        self._patterns: list[dict[str, Any]] = []
        self._optimal_params: dict[str, dict[str, Any]] = {}
        self._max_records = 100000

    def store(
        self, entity_id: str, key: str, value: Any, outcome: str, ttl: float | None = None
    ) -> MemoryRecord:
        rec = MemoryRecord(
            memory_id=f"mem_{uuid.uuid4().hex[:12]}",
            entity_id=entity_id,
            key=key,
            value=value,
            outcome=outcome,
            created_at=time.time(),
            ttl=ttl if ttl is not None else self._default_ttl,
        )
        self._records[entity_id].append(rec)
        self._trim(entity_id)
        return rec

    def recall(self, entity_id: str, key: str | None = None) -> list[MemoryRecord]:
        records = self._records.get(entity_id, [])
        if key:
            records = [r for r in records if r.key == key]
        return [r for r in records if not r.is_expired()]

    def forget(self, entity_id: str, key: str | None = None) -> int:
        if key:
            before = len(self._records.get(entity_id, []))
            self._records[entity_id] = [r for r in self._records.get(entity_id, []) if r.key != key]
            return before - len(self._records[entity_id])
        count = len(self._records.get(entity_id, []))
        self._records[entity_id] = []
        return count

    def record_behavior(
        self,
        agent_id: str,
        action: str,
        outcome: str,
        duration_ms: float,
        context: dict[str, Any] | None = None,
    ) -> BehaviorRecord:
        rec = BehaviorRecord(
            record_id=f"beh_{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            action=action,
            outcome=outcome,
            duration_ms=duration_ms,
            context=context or {},
            created_at=time.time(),
        )
        self._behaviors.append(rec)
        return rec

    def know(self, key: str, value: float | None = None) -> float | None:
        if value is not None:
            self._knowledge[key] = value
        return self._knowledge.get(key)

    def learn_pattern(self, action_sequence: list[str], success_probability: float) -> None:
        pattern_key = "->".join(action_sequence)
        self._knowledge[pattern_key] = success_probability
        self._patterns.append({"pattern": action_sequence, "probability": success_probability})

    def get_best_params(self, task_type: str) -> dict[str, Any]:
        return self._optimal_params.get(task_type, {})

    def store_best_params(self, task_type: str, params: dict[str, Any]) -> None:
        self._optimal_params[task_type] = params

    def replay_failures(self, failure_type: str | None = None) -> list[BehaviorRecord]:
        failed = [b for b in self._behaviors if b.outcome == "failure"]
        if failure_type:
            failed = [b for b in failed if b.action == failure_type]
        return failed

    def get_memory(self, limit: int = 100) -> list[MemoryRecord]:
        all_recs = [r for records in self._records.values() for r in records]
        [r for r in all_recs if r.is_expired()]
        return all_recs[:limit]

    def get_behaviors(self, limit: int = 100) -> list[BehaviorRecord]:
        return self._behaviors[-limit:]

    def _trim(self, entity_id: str) -> None:
        if len(self._records[entity_id]) > self._max_records:
            self._records[entity_id] = self._records[entity_id][-self._max_records :]
