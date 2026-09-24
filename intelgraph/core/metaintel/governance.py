from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

METAINTEL_SCHEMA_VERSION = "1.0"


class SystemHealth(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    FAILED = "failed"


class ConflictSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CrossLayerHealth:
    layer_id: str
    health: SystemHealth
    score: float
    anomalies: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    last_check: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "health": self.health.value,
            "score": round(self.score, 4),
            "anomaly_count": len(self.anomalies),
            "conflict_count": len(self.conflicts),
        }


class GlobalGovernanceEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._layers: dict[str, CrossLayerHealth] = {}
        self._policies: list[dict[str, Any]] = []
        self._global_state: dict[str, Any] = {}
        self._conflicts: list[dict[str, Any]] = []
        self._coherence_scores: dict[str, float] = defaultdict(lambda: 1.0)
        self._register_layers()

    def _register_layers(self) -> None:
        for layer in ["nlp", "reasoning", "execution", "governance", "metaintel"]:
            self._layers[layer] = CrossLayerHealth(
                layer_id=layer, health=SystemHealth.HEALTHY, score=1.0, last_check=time.time()
            )

    def record_layer_health(
        self,
        layer_id: str,
        health: SystemHealth,
        score: float,
        anomalies: list[dict[str, Any]] | None = None,
    ) -> None:
        layer = self._layers.get(layer_id)
        if not layer:
            return
        layer.health = health
        layer.score = max(0.0, min(1.0, score))
        if anomalies:
            layer.anomalies.extend(anomalies)
        layer.last_check = time.time()

    def detect_system_anomalies(self) -> list[dict[str, Any]]:
        anomalies = []
        for layer_id, layer in self._layers.items():
            if layer.score < 0.3:
                anomalies.append(
                    {"layer": layer_id, "type": "critical_degradation", "score": layer.score}
                )
            elif layer.score < 0.6:
                anomalies.append({"layer": layer_id, "type": "degradation", "score": layer.score})
        cross_corr = self._cross_layer_correlation()
        if cross_corr:
            anomalies.append({"type": "cross_layer_correlation", "details": cross_corr})
        return anomalies

    def _cross_layer_correlation(self) -> dict[str, Any]:
        scores = [(lid, l.score) for lid, l in self._layers.items()]
        if len(scores) < 2:
            return {}
        mean = sum(s for _, s in scores) / len(scores)
        variance = sum((s - mean) ** 2 for _, s in scores) / len(scores)
        if variance > 0.1:
            return {"variance": round(variance, 4), "mean": round(mean, 4), "layers": len(scores)}
        return {}

    def enforce_global_policy(self, action: dict[str, Any]) -> dict[str, Any]:
        action_type = action.get("type", "")
        risk = action.get("risk", 0.0)
        affected_layers = action.get("layers", [])
        if risk > 0.8:
            return {"allowed": False, "reason": "Risk above 0.8 threshold", "action": action_type}
        for al in affected_layers:
            layer = self._layers.get(al)
            if layer and layer.score < 0.3:
                return {
                    "allowed": False,
                    "reason": f"Layer {al} is critical",
                    "action": action_type,
                }
        return {"allowed": True, "reason": "Policy check passed", "action": action_type}

    def detect_conflicts(self) -> list[dict[str, Any]]:
        conflicts = []
        for _lid, layer in self._layers.items():
            if layer.conflicts:
                conflicts.extend(layer.conflicts)
        return conflicts

    def resolve_conflict(self, conflict_id: str, resolution: str) -> bool:
        for c in self._conflicts:
            if c.get("conflict_id") == conflict_id:
                c["resolution"] = resolution
                c["resolved_at"] = time.time()
                return True
        return False

    def get_system_health(self) -> dict[str, Any]:
        scores = {lid: l.score for lid, l in self._layers.items()}
        overall = sum(scores.values()) / max(len(scores), 1)
        return {
            "overall_health_score": round(overall, 4),
            "layers": {lid: l.to_dict() for lid, l in self._layers.items()},
            "active_conflicts": len(self._conflicts),
            "anomaly_count": sum(len(l.anomalies) for l in self._layers.values()),
        }

    def set_global_state(self, key: str, value: Any) -> None:
        self._global_state[key] = value

    def get_global_state(self, key: str) -> Any:
        return self._global_state.get(key)
