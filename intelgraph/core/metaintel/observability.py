from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class DashboardSnapshot:
    snapshot_id: str
    reasoning_quality: float
    execution_reliability: float
    knowledge_consistency: float
    system_drift: float
    cross_phase_alignment: float
    stability_index: float
    governance_conflict_rate: float
    improvement_velocity: float
    architecture_mutation_rate: float
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "reasoning_quality": round(self.reasoning_quality, 4),
            "execution_reliability": round(self.execution_reliability, 4),
            "knowledge_consistency": round(self.knowledge_consistency, 4),
            "system_drift": round(self.system_drift, 4),
            "cross_phase_alignment": round(self.cross_phase_alignment, 4),
            "stability_index": round(self.stability_index, 4),
            "governance_conflict_rate": round(self.governance_conflict_rate, 4),
            "improvement_velocity": round(self.improvement_velocity, 4),
            "architecture_mutation_rate": round(self.architecture_mutation_rate, 4),
        }


class GlobalObservabilityDashboard:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._snapshots: list[DashboardSnapshot] = []
        self._metrics_history: dict[str, list[float]] = defaultdict(list)

    def record_snapshot(self, metrics: dict[str, float]) -> DashboardSnapshot:
        snapshot = DashboardSnapshot(
            snapshot_id=f"dash_{uuid.uuid4().hex[:12]}",
            reasoning_quality=metrics.get("reasoning_quality", 0.5),
            execution_reliability=metrics.get("execution_reliability", 0.5),
            knowledge_consistency=metrics.get("knowledge_consistency", 0.5),
            system_drift=metrics.get("system_drift", 0.0),
            cross_phase_alignment=metrics.get("cross_phase_alignment", 0.5),
            stability_index=metrics.get("stability_index", 0.5),
            governance_conflict_rate=metrics.get("governance_conflict_rate", 0.0),
            improvement_velocity=metrics.get("improvement_velocity", 0.0),
            architecture_mutation_rate=metrics.get("architecture_mutation_rate", 0.0),
            timestamp=time.time(),
        )
        self._snapshots.append(snapshot)
        for key, value in metrics.items():
            self._metrics_history[key].append(value)
        return snapshot

    def get_latest(self) -> DashboardSnapshot | None:
        return self._snapshots[-1] if self._snapshots else None

    def get_trend(self, metric: str, window: int = 10) -> list[float]:
        history = self._metrics_history.get(metric, [])
        return history[-window:]

    def compute_global_health_index(self) -> float:
        latest = self.get_latest()
        if not latest:
            return 0.5
        scores = [
            latest.reasoning_quality,
            latest.execution_reliability,
            latest.knowledge_consistency,
            1.0 - latest.system_drift,
            latest.cross_phase_alignment,
            latest.stability_index,
        ]
        return sum(scores) / len(scores)

    def get_snapshots(self, limit: int = 100) -> list[DashboardSnapshot]:
        return self._snapshots[-limit:]
