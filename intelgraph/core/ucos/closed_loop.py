from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class LifecycleEntry:
    entry_id: str
    stage: str
    input_summary: str
    output_summary: str
    reasoning_result_id: str
    execution_result_id: str
    observation_metrics: dict[str, Any]
    learning_outcome: str
    improvement_taken: str
    success: bool
    duration_ms: float
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "stage": self.stage,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "reasoning_id": self.reasoning_result_id,
            "execution_id": self.execution_result_id,
            "metrics": self.observation_metrics,
            "learning_outcome": self.learning_outcome,
            "improvement": self.improvement_taken,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 2),
        }


class ClosedLoopIntelligenceSystem:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._history: list[LifecycleEntry] = []
        self._drift_threshold = self._cfg.get("drift_threshold", 0.2)
        self._performance_baseline: dict[str, float] = {}

    def run_cycle(
        self,
        input_data: dict[str, Any],
        reasoning_result: dict[str, Any],
        execution_result: dict[str, Any],
        observation: dict[str, Any] | None = None,
    ) -> LifecycleEntry:
        start = time.perf_counter()
        observation = observation or {}
        drift = self._detect_drift(observation)
        learning = self._learn(observation, execution_result)
        improvement = self._improve(drift, learning)
        elapsed = (time.perf_counter() - start) * 1000
        entry = LifecycleEntry(
            entry_id=f"lce_{uuid.uuid4().hex[:12]}",
            stage="closed_loop",
            input_summary=str(input_data.get("summary", input_data.get("query", "")))[:100],
            output_summary=str(execution_result.get("summary", ""))[:100],
            reasoning_result_id=reasoning_result.get("result_id", ""),
            execution_result_id=execution_result.get("execution_id", ""),
            observation_metrics=observation,
            learning_outcome=learning,
            improvement_taken=improvement,
            success=drift < self._drift_threshold,
            duration_ms=elapsed,
            created_at=time.time(),
        )
        self._history.append(entry)
        self._update_baseline(observation)
        return entry

    def _detect_drift(self, metrics: dict[str, Any]) -> float:
        if not metrics or not self._performance_baseline:
            return 0.0
        drifts = []
        for key, value in metrics.items():
            if isinstance(value, (int, float)) and key in self._performance_baseline:
                baseline = self._performance_baseline[key]
                if baseline != 0:
                    drifts.append(abs(value - baseline) / abs(baseline))
        return sum(drifts) / max(len(drifts), 1)

    def _learn(self, metrics: dict[str, Any], execution: dict[str, Any]) -> str:
        success = execution.get("success", True)
        if not success:
            return "failure_pattern_recorded"
        if metrics.get("latency_ms", 0) > 1000:
            return "performance_degradation_detected"
        return "nominal"

    def _improve(self, drift: float, learning: str) -> str:
        if drift > self._drift_threshold:
            return "policy_adjustment_applied"
        if learning == "failure_pattern_recorded":
            return "execution_strategy_updated"
        return "no_change_needed"

    def _update_baseline(self, metrics: dict[str, Any]) -> None:
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                if key not in self._performance_baseline:
                    self._performance_baseline[key] = value
                else:
                    self._performance_baseline[key] = (
                        self._performance_baseline[key] * 0.9 + value * 0.1
                    )

    def get_cycles(self, limit: int = 100) -> list[LifecycleEntry]:
        return self._history[-limit:]
