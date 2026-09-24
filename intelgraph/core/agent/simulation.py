from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SimulationStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SimulationResult:
    simulation_id: str
    goal: str
    status: SimulationStatus
    success_probability: float
    predicted_outcome: str
    risk_propagation: dict[str, Any]
    chaos_resilience: float
    errors: list[str] = field(default_factory=list)
    what_if_results: list[dict[str, Any]] = field(default_factory=list)
    safe_mode_fallback: bool = False
    duration_ms: float = 0.0
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "goal": self.goal,
            "status": self.status.value,
            "success_probability": round(self.success_probability, 4),
            "predicted_outcome": self.predicted_outcome,
            "risk_propagation": self.risk_propagation,
            "chaos_resilience": round(self.chaos_resilience, 4),
            "error_count": len(self.errors),
            "what_if_scenarios": len(self.what_if_results),
            "safe_mode_fallback": self.safe_mode_fallback,
            "duration_ms": round(self.duration_ms, 2),
        }


class SimulationEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._max_depth = self._cfg.get("propagation_max_depth", 3)
        self._risk_threshold = self._cfg.get("safe_mode_risk_threshold", 0.7)

    def simulate(
        self,
        goal: str,
        plan: dict[str, Any] | None = None,
        what_if: list[dict[str, Any]] | None = None,
    ) -> SimulationResult:
        result = SimulationResult(
            simulation_id=f"sim_{uuid.uuid4().hex[:12]}",
            goal=goal,
            status=SimulationStatus.RUNNING,
            success_probability=self._estimate_success(plan),
            predicted_outcome=self._predict_outcome(plan),
            risk_propagation=self._propagate_risk(plan),
            chaos_resilience=self._chaos_resilience_score(),
            created_at=time.time(),
        )
        if what_if:
            result.what_if_results = [self._run_what_if(w) for w in what_if]
        safe_mode = result.success_probability < self._risk_threshold
        if safe_mode:
            result.safe_mode_fallback = True
            result.status = SimulationStatus.COMPLETED
            return result
        if not self._validate_plan(plan):
            result.status = SimulationStatus.FAILED
            result.errors.append("Plan validation failed")
            return result
        result.status = SimulationStatus.COMPLETED
        return result

    def _estimate_success(self, plan: dict[str, Any] | None) -> float:
        if not plan:
            return random.uniform(0.1, 0.9)
        steps = len(plan.get("sub_tasks", []))
        if steps == 0:
            return 0.5
        base = 0.85**steps
        return max(0.05, min(0.99, base + random.uniform(-0.1, 0.1)))

    def _predict_outcome(self, plan: dict[str, Any] | None) -> str:
        prob = self._estimate_success(plan)
        if prob >= 0.8:
            return "likely_success"
        if prob >= 0.5:
            return "partial_success"
        if prob >= 0.2:
            return "highly_uncertain"
        return "likely_failure"

    def _propagate_risk(self, plan: dict[str, Any] | None) -> dict[str, Any]:
        if not plan:
            return {"max_risk": 0.5, "affected_nodes": 0, "propagation_count": 0}
        sub_tasks = plan.get("sub_tasks", [])
        risks = []
        for st in sub_tasks:
            if isinstance(st, dict):
                risks.append(st.get("risk_score", st.get("risk", 0.5)))
        return {
            "max_risk": max(risks) if risks else 0.5,
            "affected_nodes": len(sub_tasks),
            "propagation_count": min(len(sub_tasks), self._max_depth),
        }

    def _chaos_resilience_score(self) -> float:
        return random.uniform(0.6, 0.95)

    def _run_what_if(self, scenario: dict[str, Any]) -> dict[str, Any]:
        perturbation = scenario.get("perturbation", "default")
        return {
            "scenario": perturbation,
            "simulated_success": random.uniform(0.3, 0.95),
            "impact": random.choice(["low", "medium", "high"]),
        }

    def _validate_plan(self, plan: dict[str, Any] | None) -> bool:
        return plan is not None


class ChaosInjector:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._enabled = self._cfg.get("chaos_enabled", True)
        failure_rates = self._cfg.get("failure_rates", {})
        self._failure_prob: dict[str, float] = {
            "network": failure_rates.get("network", 0.1),
            "timeout": failure_rates.get("timeout", 0.05),
            "malformed": failure_rates.get("malformed", 0.05),
            "crash": failure_rates.get("crash", 0.02),
            "corruption": failure_rates.get("corruption", 0.03),
        }

    def inject_failure(self, plan: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._enabled:
            return {"injected": False, "reason": "Chaos disabled"}
        import random as rnd

        failures = []
        for fail_type, prob in self._failure_prob.items():
            if rnd.random() < prob:
                failures.append(fail_type)
        if failures:
            return {"injected": True, "failures": failures}
        return {"injected": False, "reason": "No failure triggered"}
