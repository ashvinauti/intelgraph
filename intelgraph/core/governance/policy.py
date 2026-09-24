from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

GOVERNANCE_SCHEMA_VERSION = "1.0"


class ComplianceStatus(Enum):
    COMPLIANT = auto()
    NON_COMPLIANT = auto()
    PENDING_REVIEW = auto()


class ApprovalStatus(Enum):
    PENDING = auto()
    APPROVED = auto()
    REJECTED = auto()
    ESCALATED = auto()


@dataclass
class AuditEntry:
    entry_id: str
    action: str
    entity_id: str
    prediction_type: str
    value: float
    actor: str
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "action": self.action,
            "entity_id": self.entity_id,
            "prediction_type": self.prediction_type,
            "value": round(self.value, 4),
            "actor": self.actor,
            "timestamp": self.timestamp or time.time(),
            "metadata": self.metadata,
        }


@dataclass
class ComplianceViolation:
    rule_name: str
    severity: str
    message: str
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp or time.time(),
        }


@dataclass
class ComplianceReport:
    report_id: str
    status: ComplianceStatus
    violations: list[ComplianceViolation]
    passed_rules: list[str]
    timestamp: float = 0.0
    schema_version: str = GOVERNANCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "status": self.status.name.lower(),
            "violations": [v.to_dict() for v in self.violations],
            "passed_rules": self.passed_rules,
            "timestamp": self.timestamp or time.time(),
            "schema_version": self.schema_version,
        }


@dataclass
class ApprovalRequest:
    request_id: str
    prediction_type: str
    entity_id: str
    value: float
    risk_score: float
    justification: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer: str = ""
    review_notes: str = ""
    created_at: float = 0.0
    reviewed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "prediction_type": self.prediction_type,
            "entity_id": self.entity_id,
            "value": round(self.value, 4),
            "risk_score": round(self.risk_score, 4),
            "justification": self.justification,
            "status": self.status.name.lower(),
            "reviewer": self.reviewer,
            "review_notes": self.review_notes,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
        }


class AuditTrail:
    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries

    def record(
        self,
        action: str,
        entity_id: str,
        prediction_type: str,
        value: float,
        actor: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            entry_id=f"ae_{uuid.uuid4().hex[:12]}",
            action=action,
            entity_id=entity_id,
            prediction_type=prediction_type,
            value=value,
            actor=actor,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]
        return entry

    def query(
        self,
        entity_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        results = self._entries[:]
        if entity_id:
            results = [e for e in results if e.entity_id == entity_id]
        if action:
            results = [e for e in results if e.action == action]
        return results[-limit:]

    def summary(self) -> dict[str, Any]:
        action_counts: dict[str, int] = {}
        for e in self._entries:
            action_counts[e.action] = action_counts.get(e.action, 0) + 1
        return {
            "total_entries": len(self._entries),
            "action_counts": action_counts,
            "max_entries": self._max_entries,
        }


class ComplianceChecker:
    def __init__(self, rules: dict[str, dict[str, Any]] | None = None) -> None:
        self._rules = rules or {}

    def add_rule(self, name: str, rule_config: dict[str, Any]) -> None:
        self._rules[name] = rule_config

    def check(
        self,
        prediction_type: str,
        value: float,
        entity_risk: float = 0.0,
    ) -> ComplianceReport:
        violations: list[ComplianceViolation] = []
        passed: list[str] = []
        now = time.time()
        for rule_name, rule in self._rules.items():
            enabled = rule.get("enabled", True)
            if not enabled:
                continue
            rule_type = rule.get("type", "max_value")
            threshold = rule.get("threshold", 0.8)
            applicable_types = rule.get("prediction_types", [prediction_type])
            if prediction_type not in applicable_types and "*" not in applicable_types:
                passed.append(rule_name)
                continue
            if rule_type == "max_value" and value > threshold:
                violations.append(
                    ComplianceViolation(
                        rule_name=rule_name,
                        severity=rule.get("severity", "warning"),
                        message=f"Value {value:.4f} exceeds threshold {threshold}",
                        timestamp=now,
                    )
                )
            elif rule_type == "min_value" and value < threshold:
                violations.append(
                    ComplianceViolation(
                        rule_name=rule_name,
                        severity=rule.get("severity", "warning"),
                        message=f"Value {value:.4f} below threshold {threshold}",
                        timestamp=now,
                    )
                )
            elif rule_type == "risk_based" and entity_risk > threshold:
                violations.append(
                    ComplianceViolation(
                        rule_name=rule_name,
                        severity=rule.get("severity", "critical"),
                        message=f"Entity risk {entity_risk:.4f} exceeds threshold {threshold}",
                        timestamp=now,
                    )
                )
            else:
                passed.append(rule_name)
        status = ComplianceStatus.COMPLIANT if not violations else ComplianceStatus.NON_COMPLIANT
        return ComplianceReport(
            report_id=f"cr_{uuid.uuid4().hex[:12]}",
            status=status,
            violations=violations,
            passed_rules=passed,
        )


class PolicyEvaluator:
    def __init__(self, policies: dict[str, Callable[..., bool]] | None = None) -> None:
        self._policies: dict[str, Callable[..., bool]] = policies or {}

    def add_policy(self, name: str, fn: Callable[..., bool]) -> None:
        self._policies[name] = fn

    def evaluate(self, context: dict[str, Any]) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name, fn in self._policies.items():
            try:
                results[name] = bool(fn(**context))
            except Exception:
                results[name] = False
        return results

    def all_pass(self, context: dict[str, Any]) -> bool:
        return all(self.evaluate(context).values())


class ApprovalWorkflow:
    def __init__(self, risk_threshold: float = 0.7, auto_approve_low_risk: bool = True) -> None:
        self._risk_threshold = risk_threshold
        self._auto_approve = auto_approve_low_risk
        self._requests: dict[str, ApprovalRequest] = {}
        self._callbacks: list[Callable[[ApprovalRequest], None]] = []

    def request_approval(
        self,
        prediction_type: str,
        entity_id: str,
        value: float,
        risk_score: float,
        justification: str = "",
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            request_id=f"apr_{uuid.uuid4().hex[:12]}",
            prediction_type=prediction_type,
            entity_id=entity_id,
            value=value,
            risk_score=risk_score,
            justification=justification,
            created_at=time.time(),
        )
        if self._auto_approve and risk_score < self._risk_threshold:
            req.status = ApprovalStatus.APPROVED
            req.reviewed_at = time.time()
        self._requests[req.request_id] = req
        for cb in self._callbacks:
            cb(req)
        return req

    def review(self, request_id: str, approved: bool, reviewer: str = "", notes: str = "") -> bool:
        req = self._requests.get(request_id)
        if req is None or req.status != ApprovalStatus.PENDING:
            return False
        req.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        req.reviewer = reviewer
        req.review_notes = notes
        req.reviewed_at = time.time()
        return True

    def escalate(self, request_id: str) -> bool:
        req = self._requests.get(request_id)
        if req is None:
            return False
        req.status = ApprovalStatus.ESCALATED
        return True

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        return self._requests.get(request_id)

    def list_pending(self) -> list[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status == ApprovalStatus.PENDING]

    def add_callback(self, cb: Callable[[ApprovalRequest], None]) -> None:
        self._callbacks.append(cb)
