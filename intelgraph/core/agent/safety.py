from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ApprovalLevel(Enum):
    AUTO = "auto"
    REVIEW = "review"
    ESCALATE = "escalate"
    DENY = "deny"


@dataclass
class SafetyCheckResult:
    result_id: str
    approved: bool
    approval_level: ApprovalLevel
    risk_score: float
    action_type: str
    action_description: str
    violations: list[str] = field(default_factory=list)
    anomaly_detected: bool = False
    requires_human: bool = False
    kill_switch_engaged: bool = False
    rollback_suggested: bool = False
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "approved": self.approved,
            "approval_level": self.approval_level.value,
            "risk_score": round(self.risk_score, 4),
            "action_type": self.action_type,
            "action_description": self.action_description,
            "violations": self.violations,
            "anomaly_detected": self.anomaly_detected,
            "requires_human": self.requires_human,
            "kill_switch_engaged": self.kill_switch_engaged,
            "rollback_suggested": self.rollback_suggested,
        }


class SafetyGovernor:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._kill_switch_global = False
        self._kill_switch_agents: dict[str, bool] = {}
        self._kill_switch_tasks: dict[str, bool] = {}
        self._forbidden_actions: list[str] = self._cfg.get(
            "forbidden_actions", ["shutdown", "destroy", "nuke"]
        )
        self._human_in_loop = self._cfg.get("human_in_loop", True)
        self._anomaly_baseline: dict[str, float] = {}
        self._check_callbacks: list[Callable] = []
        self._anomalies: list[dict[str, Any]] = []
        self._rollbacks: list[dict[str, Any]] = []
        self._self_protection = self._cfg.get("self_protection", True)

    def register_check_callback(self, cb: Callable) -> None:
        self._check_callbacks.append(cb)

    def check_action(
        self, action_type: str, description: str, risk_score: float
    ) -> SafetyCheckResult:
        for cmd in self._forbidden_actions:
            if cmd in description.lower():
                return SafetyCheckResult(
                    result_id=f"sr_{uuid.uuid4().hex[:12]}",
                    approved=False,
                    approval_level=ApprovalLevel.DENY,
                    risk_score=risk_score,
                    action_type=action_type,
                    action_description=description,
                    violations=[f"Forbidden action: {cmd}"],
                    timestamp=time.time(),
                )
        if self._kill_switch_global:
            return SafetyCheckResult(
                result_id=f"sr_{uuid.uuid4().hex[:12]}",
                approved=False,
                approval_level=ApprovalLevel.DENY,
                risk_score=risk_score,
                action_type=action_type,
                action_description=description,
                violations=["Global kill switch engaged"],
                kill_switch_engaged=True,
                timestamp=time.time(),
            )
        anomaly = self._detect_anomaly(action_type, risk_score)
        level = self._determine_approval(risk_score, anomaly)
        approved = level in (ApprovalLevel.AUTO, ApprovalLevel.REVIEW)
        result = SafetyCheckResult(
            result_id=f"sr_{uuid.uuid4().hex[:12]}",
            approved=approved,
            approval_level=level,
            risk_score=risk_score,
            action_type=action_type,
            action_description=description,
            anomaly_detected=anomaly,
            requires_human=level == ApprovalLevel.ESCALATE,
            kill_switch_engaged=self._kill_switch_global,
            rollback_suggested=risk_score > 0.7,
            timestamp=time.time(),
        )
        for cb in self._check_callbacks:
            cb(result)
        return result

    def _detect_anomaly(self, action_type: str, risk_score: float) -> bool:
        baseline = self._anomaly_baseline.get(action_type, 0.3)
        deviation = abs(risk_score - baseline)
        if deviation > 0.4:
            self._anomalies.append(
                {
                    "action_type": action_type,
                    "expected": baseline,
                    "actual": risk_score,
                    "deviation": deviation,
                    "time": time.time(),
                }
            )
            return True
        return False

    def _determine_approval(self, risk_score: float, anomaly: bool) -> ApprovalLevel:
        if risk_score >= 0.9 or anomaly:
            return ApprovalLevel.ESCALATE
        if risk_score >= 0.7:
            return ApprovalLevel.REVIEW
        return ApprovalLevel.AUTO

    def engage_kill_switch(self, scope: str = "global", target_id: str = "") -> bool:
        if scope == "global":
            self._kill_switch_global = True
        elif scope == "agent" and target_id:
            self._kill_switch_agents[target_id] = True
        elif scope == "task" and target_id:
            self._kill_switch_tasks[target_id] = True
        else:
            return False
        return True

    def disengage_kill_switch(self, scope: str = "global", target_id: str = "") -> bool:
        if scope == "global":
            self._kill_switch_global = False
        elif scope == "agent" and target_id:
            self._kill_switch_agents.pop(target_id, None)
        elif scope == "task" and target_id:
            self._kill_switch_tasks.pop(target_id, None)
        else:
            return False
        return True

    def is_killed(self, agent_id: str = "", task_id: str = "") -> bool:
        if self._kill_switch_global:
            return True
        if agent_id and self._kill_switch_agents.get(agent_id, False):
            return True
        if task_id and self._kill_switch_tasks.get(task_id, False):
            return True
        return False

    def set_baseline(self, action_type: str, baseline_risk: float) -> None:
        self._anomaly_baseline[action_type] = baseline_risk

    def get_anomalies(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._anomalies[-limit:]

    def suggest_rollback(self, action_id: str, reason: str) -> dict[str, Any]:
        entry = {"action_id": action_id, "reason": reason, "time": time.time()}
        self._rollbacks.append(entry)
        return entry

    def get_rollback_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._rollbacks[-limit:]
