from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class TelemetrySnapshot:
    snapshot_id: str
    health_index: float
    reasoning_quality: float
    execution_success_rate: float
    avg_latency_ms: float
    throughput: float
    drift_score: float
    active_pipelines: int
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "health_index": round(self.health_index, 4),
            "reasoning_quality": round(self.reasoning_quality, 4),
            "execution_success_rate": round(self.execution_success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "throughput": round(self.throughput, 4),
            "drift_score": round(self.drift_score, 4),
            "active_pipelines": self.active_pipelines,
        }


class UnifiedTelemetryCore:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._snapshots: list[TelemetrySnapshot] = []
        self._latency_history: list[float] = []
        self._success_history: list[bool] = []
        self._metric_history: dict[str, list[float]] = defaultdict(list)

    def record(
        self,
        reasoning_quality: float = 0.5,
        execution_success: bool = True,
        latency_ms: float = 0.0,
        drift: float = 0.0,
        active_pipelines: int = 0,
    ) -> TelemetrySnapshot:
        self._latency_history.append(latency_ms)
        self._success_history.append(execution_success)
        if len(self._latency_history) > 1000:
            self._latency_history = self._latency_history[-1000:]
        if len(self._success_history) > 1000:
            self._success_history = self._success_history[-1000:]
        avg_latency = sum(self._latency_history[-100:]) / max(len(self._latency_history[-100:]), 1)
        success_rate = sum(1 for s in self._success_history[-100:] if s) / max(
            len(self._success_history[-100:]), 1
        )
        throughput = len(self._latency_history[-60:]) / 60.0 if self._latency_history else 0.0
        health = self._compute_health(reasoning_quality, success_rate, drift)
        snapshot = TelemetrySnapshot(
            snapshot_id=f"tel_{uuid.uuid4().hex[:12]}",
            health_index=health,
            reasoning_quality=reasoning_quality,
            execution_success_rate=success_rate,
            avg_latency_ms=avg_latency,
            throughput=throughput,
            drift_score=drift,
            active_pipelines=active_pipelines,
            timestamp=time.time(),
        )
        self._snapshots.append(snapshot)
        self._metric_history["reasoning_quality"].append(reasoning_quality)
        self._metric_history["execution_success_rate"].append(success_rate)
        self._metric_history["drift_score"].append(drift)
        return snapshot

    def _compute_health(self, reasoning: float, execution: float, drift: float) -> float:
        return max(0.0, min(1.0, (reasoning * 0.4 + execution * 0.4 + (1.0 - drift) * 0.2)))

    def get_latest(self) -> TelemetrySnapshot | None:
        return self._snapshots[-1] if self._snapshots else None

    def get_trend(self, metric: str, window: int = 10) -> list[float]:
        return self._metric_history.get(metric, [])[-window:]

    def get_snapshots(self, limit: int = 100) -> list[TelemetrySnapshot]:
        return self._snapshots[-limit:]
