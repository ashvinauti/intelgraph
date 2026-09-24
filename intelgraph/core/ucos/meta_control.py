from __future__ import annotations

import time
import uuid
from typing import Any


class SelfStabilizingMetaControl:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._approval_gate = self._cfg.get("approval_gate_required", True)
        self._pending_changes: list[dict[str, Any]] = []
        self._approved_changes: list[dict[str, Any]] = []
        self._rejected_changes: list[dict[str, Any]] = []

    def propose_change(
        self, description: str, target: str, change_type: str, risk: float = 0.5
    ) -> dict[str, Any]:
        proposal = {
            "proposal_id": f"sc_{uuid.uuid4().hex[:12]}",
            "description": description,
            "target": target,
            "change_type": change_type,
            "risk": risk,
            "status": "pending",
            "created_at": time.time(),
            "requires_human_approval": self._approval_gate and risk > 0.3,
        }
        self._pending_changes.append(proposal)
        return proposal

    def approve_change(self, proposal_id: str, reviewer: str = "system") -> bool:
        for prop in self._pending_changes:
            if prop["proposal_id"] == proposal_id:
                prop["status"] = "approved"
                prop["reviewed_by"] = reviewer
                prop["approved_at"] = time.time()
                self._approved_changes.append(prop)
                self._pending_changes.remove(prop)
                return True
        return False

    def reject_change(self, proposal_id: str, reason: str = "") -> bool:
        for prop in self._pending_changes:
            if prop["proposal_id"] == proposal_id:
                prop["status"] = "rejected"
                prop["rejection_reason"] = reason
                prop["rejected_at"] = time.time()
                self._rejected_changes.append(prop)
                self._pending_changes.remove(prop)
                return True
        return False

    def validate_regression(
        self, before_metrics: dict[str, Any], after_metrics: dict[str, Any]
    ) -> dict[str, Any]:
        regressions = []
        for key in set(before_metrics.keys()) & set(after_metrics.keys()):
            if isinstance(before_metrics[key], (int, float)) and isinstance(
                after_metrics[key], (int, float)
            ):
                if after_metrics[key] < before_metrics[key] * 0.8:
                    regressions.append(
                        {"metric": key, "before": before_metrics[key], "after": after_metrics[key]}
                    )
        return {"has_regression": len(regressions) > 0, "regressions": regressions}

    def get_pending_changes(self) -> list[dict[str, Any]]:
        return list(self._pending_changes)

    def get_approved_changes(self) -> list[dict[str, Any]]:
        return list(self._approved_changes)

    def get_rejected_changes(self) -> list[dict[str, Any]]:
        return list(self._rejected_changes)
