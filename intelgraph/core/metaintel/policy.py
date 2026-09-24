from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class PolicyRecord:
    policy_id: str
    name: str
    description: str
    rules: list[dict[str, Any]]
    version: int
    risk_level: str
    status: str
    created_at: float = 0.0
    immutable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "rule_count": len(self.rules),
            "version": self.version,
            "risk_level": self.risk_level,
            "status": self.status,
            "created_at": self.created_at,
            "immutable": self.immutable,
        }


class PolicyEvolutionEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._policies: list[PolicyRecord] = []
        self._failure_patterns: list[dict[str, Any]] = []
        self._simulation_results: list[dict[str, Any]] = []
        self._a_b_tests: list[dict[str, Any]] = []

    def generate_policy(
        self, name: str, description: str, rules: list[dict[str, Any]], risk_level: str = "medium"
    ) -> PolicyRecord:
        existing = [p for p in self._policies if p.name == name]
        version = (max(p.version for p in existing) + 1) if existing else 1
        policy = PolicyRecord(
            policy_id=f"pol_{uuid.uuid4().hex[:12]}",
            name=name,
            description=description,
            rules=rules,
            version=version,
            risk_level=risk_level,
            status="active",
            created_at=time.time(),
        )
        self._policies.append(policy)
        return policy

    def refine_from_failures(self, base_policy_id: str) -> PolicyRecord | None:
        base = next((p for p in self._policies if p.policy_id == base_policy_id), None)
        if not base:
            return None
        recent_failures = self._failure_patterns[-50:]
        if not recent_failures:
            return base
        error_types = defaultdict(int)
        for f in recent_failures:
            error_types[f.get("error_type", "unknown")] += 1
        new_rules = list(base.rules)
        for err_type, count in error_types.items():
            if count > 5:
                new_rules.append(
                    {
                        "condition": f"error_type == '{err_type}'",
                        "action": "block",
                        "priority": count,
                    }
                )
        return self.generate_policy(
            f"{base.name}_refined", f"Auto-refined from {base.name}", new_rules, base.risk_level
        )

    def enforce(self, action: dict[str, Any]) -> dict[str, Any]:
        action_type = action.get("type", "")
        action_risk = action.get("risk", 0.0)
        for policy in self._policies:
            if policy.status != "active":
                continue
            for rule in policy.rules:
                if rule.get("action") == "block" and action_risk > 0.7:
                    return {
                        "allowed": False,
                        "policy": policy.name,
                        "rule": rule,
                        "action": action_type,
                    }
        return {"allowed": True, "policy": "default", "action": action_type}

    def simulate_policy(self, policy_id: str, test_actions: list[dict[str, Any]]) -> dict[str, Any]:
        policy = next((p for p in self._policies if p.policy_id == policy_id), None)
        if not policy:
            return {"error": "Policy not found"}
        blocked = 0
        allowed = 0
        for action in test_actions:
            for rule in policy.rules:
                if rule.get("action") == "block" and action.get("risk", 0) > 0.7:
                    blocked += 1
                    break
            else:
                allowed += 1
        result = {
            "policy_id": policy_id,
            "allowed": allowed,
            "blocked": blocked,
            "total": len(test_actions),
        }
        self._simulation_results.append(result)
        return result

    def a_b_test(
        self, policy_a_id: str, policy_b_id: str, test_actions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        result_a = self.simulate_policy(policy_a_id, test_actions)
        result_b = self.simulate_policy(policy_b_id, test_actions)
        ab_result = {
            "test_id": f"ab_{uuid.uuid4().hex[:12]}",
            "policy_a": result_a,
            "policy_b": result_b,
            "a_allowed_rate": result_a["allowed"] / max(result_a["total"], 1),
            "b_allowed_rate": result_b["allowed"] / max(result_b["total"], 1),
        }
        self._a_b_tests.append(ab_result)
        return ab_result

    def record_failure(self, error_type: str, details: dict[str, Any]) -> None:
        self._failure_patterns.append(
            {"error_type": error_type, "details": details, "time": time.time()}
        )

    def get_policies(self, status: str | None = None) -> list[PolicyRecord]:
        if status:
            return [p for p in self._policies if p.status == status]
        return list(self._policies)

    def deprecate_policy(self, policy_id: str) -> bool:
        policy = next((p for p in self._policies if p.policy_id == policy_id), None)
        if not policy:
            return False
        policy.status = "deprecated"
        return True
