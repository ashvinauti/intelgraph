from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostProfile:
    model_id: str
    inference_cost: float = 0.001
    memory_mb: float = 100.0
    accuracy: float = 0.8
    avg_latency_ms: float = 50.0
    cost_per_token: float = 0.00001


@dataclass
class QueryROI:
    query_id: str
    estimated_value: float
    estimated_cost: float
    roi: float
    net_value: float
    decision: str
    alternatives: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "estimated_value": round(self.estimated_value, 4),
            "estimated_cost": round(self.estimated_cost, 6),
            "roi": round(self.roi, 4),
            "net_value": round(self.net_value, 4),
            "decision": self.decision,
            "alternatives": self.alternatives,
        }


class EconomicGovernor:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._budget_used: float = 0.0
        self._budget_limit: float = self._cfg.get("budget_limit", 1000.0)
        self._min_roi: float = self._cfg.get("min_roi", 0.5)
        self._cost_log: list[dict[str, Any]] = []

    def compute_roi(self, query_id: str, value: float, cost: float) -> QueryROI:
        roi = value / cost if cost > 0 else float("inf")
        net = value - cost
        decision: str = ""
        alternatives: list[dict[str, Any]] = []
        if self._budget_used + cost > self._budget_limit:
            decision = "reject_budget_exhausted"
        elif roi < self._min_roi:
            decision = "reject_insufficient_roi"
        else:
            decision = "approve"
        result = QueryROI(
            query_id=query_id,
            estimated_value=value,
            estimated_cost=cost,
            roi=roi,
            net_value=net,
            decision=decision,
            alternatives=alternatives,
        )
        if decision == "approve":
            self._budget_used += cost
        self._cost_log.append(
            {"query_id": query_id, "decision": decision, "cost": cost, "value": value, "roi": roi}
        )
        return result

    def should_analyze(self, text_length: int, complexity: str = "medium") -> bool:
        cost = text_length * 0.0001
        if complexity == "high":
            cost *= 2.0
        value = (
            text_length * 0.001
            if "critical" in text_length or "cve" in str(text_length).lower()
            else text_length * 0.0005
        )
        roi = self.compute_roi(f"analysis_{time.time()}", value, cost)
        return roi.decision == "approve"

    def get_budget_status(self) -> dict[str, Any]:
        return {
            "budget_limit": self._budget_limit,
            "budget_used": round(self._budget_used, 4),
            "budget_remaining": round(self._budget_limit - self._budget_used, 4),
            "utilization_pct": round(
                self._budget_used / self._budget_limit * 100 if self._budget_limit else 0, 2
            ),
        }

    def predict_budget_exhaustion(self, avg_cost_per_query: float) -> float:
        remaining = self._budget_limit - self._budget_used
        if avg_cost_per_query <= 0:
            return float("inf")
        return remaining / avg_cost_per_query


class CostAwareInferenceRouter:
    def __init__(self, governor: EconomicGovernor, registry: Any) -> None:
        self._governor = governor
        self._registry = registry

    def select_model(
        self, task: str, text_length: int, accuracy_requirement: float = 0.7
    ) -> dict[str, Any]:
        models = self._registry.list() if hasattr(self._registry, "list") else []
        candidates: list[tuple[float, Any]] = []
        for m in models:
            if m.metadata.get("task") == task and m.accuracy >= accuracy_requirement:
                efficiency = m.accuracy / max(m.latency_ms, 1)
                candidates.append((efficiency, m))
        if not candidates:
            return {"selected": None, "reason": "No suitable model found"}
        candidates.sort(key=lambda x: -x[0])
        best = candidates[0][1]
        cost = best.metadata.get("cost_per_inference", 0.001)
        roi = self._governor.compute_roi(f"inference_{best.model_id}", text_length * 0.001, cost)
        if roi.decision != "approve":
            if len(candidates) > 1:
                alt = candidates[1][1]
                return {
                    "selected": alt.model_id,
                    "original": best.model_id,
                    "reason": f"Budget-aware routing: {alt.model_id} chosen over {best.model_id}",
                    "roi": roi.to_dict(),
                }
            return {"selected": None, "reason": "Budget exceeded for all models"}
        return {"selected": best.model_id, "reason": "Optimal model selected", "roi": roi.to_dict()}
