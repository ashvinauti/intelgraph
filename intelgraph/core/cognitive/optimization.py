from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OptimizationMetrics:
    extraction_accuracy: float
    model_routing_efficiency: float
    reasoning_cost: float
    throughput: float
    drift_score: float
    threshold_sensitivity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "extraction_accuracy": round(self.extraction_accuracy, 4),
            "model_routing_efficiency": round(self.model_routing_efficiency, 4),
            "reasoning_cost": round(self.reasoning_cost, 4),
            "throughput": round(self.throughput, 4),
            "drift_score": round(self.drift_score, 4),
            "threshold_sensitivity": round(self.threshold_sensitivity, 4),
        }


class ContinuousOptimizer:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._history: list[OptimizationMetrics] = []
        self._drift_baseline: dict[str, float] = {}
        self._thresholds: dict[str, float] = {
            "anomaly_zscore": 3.0,
            "confidence_min": 0.1,
            "similarity_match": 0.7,
            "extraction_quality": 0.5,
        }

    def update_accuracy(self, correct: int, total: int) -> float:
        accuracy = correct / max(total, 1)
        self._set_drift_baseline("extraction_accuracy", accuracy)
        return accuracy

    def optimize_routing(self, model_stats: list[dict[str, Any]]) -> dict[str, str]:
        routing: dict[str, str] = {}
        for stat in model_stats:
            task = stat.get("task", "unknown")
            accuracy = stat.get("accuracy", 0.5)
            cost = stat.get("cost", 1.0)
            if len(self._history) > 10:
                trend = self._detect_trend("extraction_accuracy")
                if trend < 0:
                    accuracy *= 1.1
            efficiency = accuracy / max(cost, 0.001)
            if efficiency > 0.5:
                routing[task] = stat.get("model_id", "default")
        return routing

    def detect_drift(self) -> float:
        if len(self._history) < 10:
            return 0.0
        recent = self._history[-10:]
        values = [m.extraction_accuracy for m in recent]
        mean = sum(values) / len(values)
        drift = sum(abs(v - mean) for v in values) / len(values)
        return drift

    def auto_tune_threshold(self, metric_name: str, current_value: float) -> float:
        if metric_name not in self._thresholds:
            return current_value
        if len(self._history) < 5:
            return self._thresholds[metric_name]
        baseline = self._drift_baseline.get(metric_name, 0.5)
        if current_value < baseline * 0.8:
            self._thresholds[metric_name] *= 0.95
        elif current_value > baseline * 1.2:
            self._thresholds[metric_name] *= 1.05
        return self._thresholds[metric_name]

    def record_optimization(self, metrics: OptimizationMetrics) -> None:
        self._history.append(metrics)
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

    def get_drift_report(self) -> dict[str, Any]:
        drift = self.detect_drift()
        return {
            "drift_score": round(drift, 4),
            "drift_detected": drift > 0.1,
            "history_length": len(self._history),
            "thresholds": dict(self._thresholds),
        }

    def _detect_trend(self, metric: str) -> float:
        if len(self._history) < 5:
            return 0.0
        values = [getattr(m, metric, 0.5) for m in self._history[-5:]]
        if all(values[i] <= values[i + 1] for i in range(len(values) - 1)):
            return 1.0
        if all(values[i] >= values[i + 1] for i in range(len(values) - 1)):
            return -1.0
        return 0.0

    def _set_drift_baseline(self, key: str, value: float) -> None:
        if key not in self._drift_baseline:
            self._drift_baseline[key] = value
        else:
            self._drift_baseline[key] = 0.9 * self._drift_baseline[key] + 0.1 * value
