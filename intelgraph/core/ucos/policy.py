from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class UnifiedPolicyDecision:
    decision_id: str
    action_type: str
    action_risk: float
    allowed: bool
    policy_sources: list[str]
    reason: str
    requires_override: bool
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "action_type": self.action_type,
            "action_risk": round(self.action_risk, 4),
            "allowed": self.allowed,
            "policy_sources": self.policy_sources,
            "reason": self.reason,
            "requires_override": self.requires_override,
        }


class UnifiedPolicyControlPlane:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._decisions: list[UnifiedPolicyDecision] = []
        self._rules: list[dict[str, Any]] = [
            {"id": "r1", "name": "max_risk", "max_risk": 0.8, "action": "deny"},
            {
                "id": "r2",
                "name": "forbidden_actions",
                "actions": ["shutdown", "destroy", "nuke"],
                "action": "deny",
            },
            {
                "id": "r3",
                "name": "admin_only",
                "required_role": "admin",
                "actions": ["kill_switch", "arch_change"],
                "action": "deny",
            },
        ]
        self._overrides: list[dict[str, Any]] = []

    def evaluate(self, action_type: str, risk: float, role: str = "user") -> UnifiedPolicyDecision:
        policy_sources = []
        reason = ""
        allowed = True
        requires_override = False

        for rule in self._rules:
            if rule.get("action") == "deny":
                max_risk = rule.get("max_risk")
                if max_risk is not None and risk > max_risk:
                    allowed = False
                    policy_sources.append(rule["name"])
                    reason = f"Risk {risk:.2f} exceeds max {max_risk}"
                forbidden = rule.get("actions", [])
                if any(a in action_type.lower() for a in forbidden):
                    allowed = False
                    policy_sources.append(rule["name"])
                    reason = f"Action '{action_type}' is forbidden"
                req_role = rule.get("required_role")
                if req_role and action_type in rule.get("actions", []):
                    role_hierarchy = {"user": 0, "analyst": 1, "reviewer": 2, "admin": 3}
                    if role_hierarchy.get(role, 0) < role_hierarchy.get(req_role, 0):
                        allowed = False
                        policy_sources.append(rule["name"])
                        reason = f"Role '{role}' insufficient, requires '{req_role}'"

        if not allowed and role == "admin":
            requires_override = True

        decision = UnifiedPolicyDecision(
            decision_id=f"upd_{uuid.uuid4().hex[:12]}",
            action_type=action_type,
            action_risk=risk,
            allowed=allowed,
            policy_sources=policy_sources or ["default"],
            reason=reason or "No rule matched",
            requires_override=requires_override,
            timestamp=time.time(),
        )
        self._decisions.append(decision)
        return decision

    def add_rule(self, rule: dict[str, Any]) -> None:
        if "id" not in rule:
            rule["id"] = f"r_{uuid.uuid4().hex[:8]}"
        self._rules.append(rule)

    def override_decision(self, decision_id: str, reason: str) -> bool:
        for d in self._decisions:
            if d.decision_id == decision_id:
                d.allowed = True
                d.reason = f"OVERRIDE: {reason}"
                self._overrides.append(
                    {"decision_id": decision_id, "reason": reason, "time": time.time()}
                )
                return True
        return False

    def get_decisions(self, limit: int = 100) -> list[UnifiedPolicyDecision]:
        return self._decisions[-limit:]

    def get_rules(self) -> list[dict[str, Any]]:
        return list(self._rules)

    def get_overrides(self) -> list[dict[str, Any]]:
        return list(self._overrides)
