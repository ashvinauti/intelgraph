from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class DiagnosticReport:
    report_id: str
    pipeline_stage: str
    health_score: float
    drift_scores: dict[str, float]
    anomalies: list[dict[str, Any]]
    root_causes: list[dict[str, Any]]
    bottlenecks: list[dict[str, Any]]
    regression_flags: list[str]
    generated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "pipeline_stage": self.pipeline_stage,
            "health_score": round(self.health_score, 4),
            "drift_scores": {k: round(v, 4) for k, v in self.drift_scores.items()},
            "anomaly_count": len(self.anomalies),
            "root_cause_count": len(self.root_causes),
            "bottleneck_count": len(self.bottlenecks),
            "regression_flags": self.regression_flags,
        }


class SystemDiagnostics:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._reports: list[DiagnosticReport] = []
        self._drift_history: dict[str, list[float]] = defaultdict(list)
        self._regression_baselines: dict[str, float] = {}
        self._bottlenecks: list[dict[str, Any]] = []
        self._correlation_events: list[dict[str, Any]] = []

    def run_diagnostics(self, pipeline_stage: str, metrics: dict[str, Any]) -> DiagnosticReport:
        drift_scores = self._compute_drift(pipeline_stage, metrics)
        anomalies = self._detect_anomalies(pipeline_stage, metrics, drift_scores)
        root_causes = self._root_cause_analysis(pipeline_stage, anomalies)
        bottlenecks = self._map_bottlenecks(pipeline_stage, metrics)
        regression_flags = self._detect_regressions(pipeline_stage, metrics)
        report = DiagnosticReport(
            report_id=f"diag_{uuid.uuid4().hex[:12]}",
            pipeline_stage=pipeline_stage,
            health_score=self._compute_health(drift_scores, anomalies),
            drift_scores=drift_scores,
            anomalies=anomalies,
            root_causes=root_causes,
            bottlenecks=bottlenecks,
            regression_flags=regression_flags,
            generated_at=time.time(),
        )
        self._reports.append(report)
        return report

    def _compute_drift(self, stage: str, metrics: dict[str, Any]) -> dict[str, float]:
        drifts = {}
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                history = self._drift_history[f"{stage}_{key}"]
                if history:
                    mean = sum(history) / len(history)
                    drift = abs(value - mean) / max(mean, 0.001)
                    drifts[key] = min(drift, 10.0)
                else:
                    drifts[key] = 0.0
                history.append(value)
                if len(history) > 100:
                    self._drift_history[f"{stage}_{key}"] = history[-100:]
        return drifts

    def _detect_anomalies(
        self, stage: str, metrics: dict[str, Any], drifts: dict[str, float]
    ) -> list[dict[str, Any]]:
        anomalies = []
        for key, drift in drifts.items():
            if drift > 2.0:
                anomalies.append({"key": key, "drift": round(drift, 4), "severity": "high"})
            elif drift > 1.0:
                anomalies.append({"key": key, "drift": round(drift, 4), "severity": "medium"})
        return anomalies

    def _root_cause_analysis(
        self, stage: str, anomalies: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        causes = []
        for a in anomalies:
            cause = self._trace_root_cause(stage, a)
            if cause:
                causes.append(cause)
        return causes

    def _trace_root_cause(self, stage: str, anomaly: dict[str, Any]) -> dict[str, Any]:
        layer_map = {
            "nlp": ["reasoning", "execution"],
            "reasoning": ["execution", "governance"],
            "execution": ["governance", "metaintel"],
            "governance": ["metaintel"],
            "metaintel": [],
        }
        downstream = layer_map.get(stage, [])
        return {
            "source_layer": stage,
            "anomaly_key": anomaly.get("key", ""),
            "drift": anomaly.get("drift", 0.0),
            "downstream_impact": downstream,
            "confidence": max(0.3, 1.0 - anomaly.get("drift", 0.0) / 5.0),
        }

    def _map_bottlenecks(self, stage: str, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        bottlenecks = []
        latency = metrics.get("latency_ms", 0)
        if latency > 1000:
            bottlenecks.append(
                {"stage": stage, "type": "latency", "value": latency, "threshold": 1000}
            )
        error_rate = metrics.get("error_rate", 0)
        if error_rate > 0.1:
            bottlenecks.append(
                {"stage": stage, "type": "error_rate", "value": error_rate, "threshold": 0.1}
            )
        return bottlenecks

    def _detect_regressions(self, stage: str, metrics: dict[str, Any]) -> list[str]:
        flags = []
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                baseline = self._regression_baselines.get(f"{stage}_{key}")
                if baseline is not None and value < baseline * 0.8:
                    flags.append(f"{key}_regression")
                self._regression_baselines.setdefault(f"{stage}_{key}", value)
        return flags

    def _compute_health(self, drifts: dict[str, float], anomalies: list[dict[str, Any]]) -> float:
        if not drifts:
            return 1.0
        avg_drift = sum(drifts.values()) / len(drifts)
        anomaly_penalty = len(anomalies) * 0.05
        health = max(0.0, 1.0 - avg_drift * 0.3 - anomaly_penalty)
        return health

    def cross_phase_correlate(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        correlated = []
        for event in events:
            event["correlation_id"] = f"corr_{uuid.uuid4().hex[:12]}"
            self._correlation_events.append(event)
            correlated.append(event)
        return correlated

    def get_reports(self, limit: int = 10) -> list[DiagnosticReport]:
        return self._reports[-limit:]
