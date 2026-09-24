from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class OptimizationProposal:
    proposal_id: str
    target: str
    description: str
    expected_gain: float
    risk: float
    status: str
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "target": self.target,
            "description": self.description,
            "expected_gain": round(self.expected_gain, 4),
            "risk": round(self.risk, 4),
            "status": self.status,
        }


class SelfImprovementController:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._proposals: list[OptimizationProposal] = []
        self._learning_rates: dict[str, float] = defaultdict(lambda: 0.1)
        self._performance_history: list[dict[str, Any]] = []
        self._allocations: dict[str, float] = {}

    def propose_optimization(
        self, target: str, description: str, expected_gain: float, risk: float
    ) -> OptimizationProposal:
        proposal = OptimizationProposal(
            proposal_id=f"opt_{uuid.uuid4().hex[:12]}",
            target=target,
            description=description,
            expected_gain=expected_gain,
            risk=risk,
            status="pending",
            created_at=time.time(),
        )
        self._proposals.append(proposal)
        return proposal

    def approve_optimization(self, proposal_id: str) -> bool:
        proposal = next((p for p in self._proposals if p.proposal_id == proposal_id), None)
        if not proposal:
            return False
        proposal.status = "approved"
        return True

    def reject_optimization(self, proposal_id: str) -> bool:
        proposal = next((p for p in self._proposals if p.proposal_id == proposal_id), None)
        if not proposal:
            return False
        proposal.status = "rejected"
        return True

    def optimize_resource_allocation(
        self, current_allocation: dict[str, float], performance: dict[str, float]
    ) -> dict[str, float]:
        total = sum(current_allocation.values()) or 1.0
        normalized = {k: v / total for k, v in current_allocation.items()}
        for key, perf in performance.items():
            if perf < 0.5 and key in normalized:
                normalized[key] = max(0.05, normalized[key] * 0.9)
            elif perf > 0.8 and key in normalized:
                normalized[key] = min(0.5, normalized[key] * 1.1)
        total_norm = sum(normalized.values()) or 1.0
        self._allocations = {k: v / total_norm for k, v in normalized.items()}
        return dict(self._allocations)

    def tune_learning_rate(self, layer: str, performance: float) -> float:
        current = self._learning_rates[layer]
        if performance < 0.3:
            new_rate = current * 0.5
        elif performance > 0.8:
            new_rate = min(0.5, current * 1.2)
        else:
            new_rate = current
        self._learning_rates[layer] = max(0.001, min(0.5, new_rate))
        return self._learning_rates[layer]

    def record_performance(self, metrics: dict[str, Any]) -> None:
        entry = {"timestamp": time.time(), "metrics": metrics}
        self._performance_history.append(entry)
        if len(self._performance_history) > 1000:
            self._performance_history = self._performance_history[-1000:]

    def get_proposals(self, status: str | None = None) -> list[OptimizationProposal]:
        if status:
            return [p for p in self._proposals if p.status == status]
        return list(self._proposals)

    def get_optimization_velocity(self) -> float:
        if len(self._proposals) < 2:
            return 0.0
        recent = self._proposals[-10:]
        approved = sum(1 for p in recent if p.status == "approved")
        return approved / len(recent)
