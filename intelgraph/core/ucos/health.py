from __future__ import annotations

import time
import uuid
from typing import Any


class GlobalHealthIndex:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._history: list[dict[str, Any]] = []

    def compute(
        self,
        cognitive: float = 0.5,
        execution: float = 0.5,
        knowledge: float = 0.5,
        policy: float = 0.5,
        complexity: float = 0.5,
    ) -> dict[str, Any]:
        raw = {
            "cognitive_health_score": max(0.0, min(1.0, cognitive)),
            "execution_stability_score": max(0.0, min(1.0, execution)),
            "knowledge_consistency_score": max(0.0, min(1.0, knowledge)),
            "policy_coherence_score": max(0.0, min(1.0, policy)),
            "system_complexity_index": max(0.0, min(1.0, complexity)),
        }
        overall = sum(raw.values()) / len(raw)
        result = {
            "timestamp": time.time(),
            "index_id": f"ghi_{uuid.uuid4().hex[:12]}",
            "overall_health": round(overall, 4),
            **raw,
        }
        self._history.append(result)
        return result

    def get_trend(self, metric: str, window: int = 10) -> list[float]:
        return [h.get(metric, 0.0) for h in self._history[-window:]]

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._history[-limit:]
