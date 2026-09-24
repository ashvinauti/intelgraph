from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionOutcome:
    outcome_id: str
    task_id: str
    success: bool
    confidence: float
    duration_ms: float
    error: str
    outcome_type: str
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "task_id": self.task_id,
            "success": self.success,
            "confidence": round(self.confidence, 4),
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "outcome_type": self.outcome_type,
        }


class ExecutionFeedbackLoop:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._outcomes: list[ExecutionOutcome] = []
        self._performance: dict[str, list[float]] = defaultdict(list)
        self._policy_weights: dict[str, float] = {}
        self._weak_signals: list[dict[str, Any]] = []

    def record_outcome(
        self,
        task_id: str,
        success: bool,
        confidence: float,
        duration_ms: float,
        error: str = "",
        outcome_type: str = "execution",
    ) -> ExecutionOutcome:
        outcome = ExecutionOutcome(
            outcome_id=f"oc_{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            success=success,
            confidence=confidence,
            duration_ms=duration_ms,
            error=error,
            outcome_type=outcome_type,
            created_at=time.time(),
        )
        self._outcomes.append(outcome)
        self._update_performance(task_id, success)
        if confidence > 0.3 and not success:
            self._learn_weak_signal(task_id, error)
        return outcome

    def _update_performance(self, task_id: str, success: bool) -> None:
        self._performance[task_id].append(1.0 if success else 0.0)
        if len(self._performance[task_id]) > 100:
            self._performance[task_id] = self._performance[task_id][-100:]

    def _learn_weak_signal(self, task_id: str, error: str) -> None:
        self._weak_signals.append({"task_id": task_id, "error": error, "time": time.time()})

    def execution_performance_score(self, task_id: str) -> float:
        scores = self._performance.get(task_id, [])
        if not scores:
            return 0.5
        return sum(scores) / len(scores)

    def overall_success_rate(self, window: int = 100) -> float:
        recent = self._outcomes[-window:]
        if not recent:
            return 0.0
        return sum(1 for o in recent if o.success) / len(recent)

    def adaptive_policy_tune(self, policy_name: str, outcome_value: float) -> float:
        current = self._policy_weights.get(policy_name, 0.5)
        new_weight = current * 0.9 + outcome_value * 0.1
        self._policy_weights[policy_name] = max(0.0, min(1.0, new_weight))
        return self._policy_weights[policy_name]

    def get_weak_signals(self, min_frequency: int = 2) -> list[dict[str, Any]]:
        freq: dict[str, int] = defaultdict(int)
        for s in self._weak_signals:
            freq[s.get("error", "unknown")] += 1
        return [
            {"error": err, "frequency": cnt} for err, cnt in freq.items() if cnt >= min_frequency
        ]

    def get_outcomes(self, limit: int = 100) -> list[ExecutionOutcome]:
        return self._outcomes[-limit:]
