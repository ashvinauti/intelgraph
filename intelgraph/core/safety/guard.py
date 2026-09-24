from __future__ import annotations

import math
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

SAFETY_SCHEMA_VERSION = "1.0"


class Severity(Enum):
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


@dataclass
class SafetyViolation:
    rule_name: str
    severity: Severity
    message: str
    current_value: float
    threshold_value: float
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "severity": self.severity.name.lower(),
            "message": self.message,
            "current_value": round(self.current_value, 4),
            "threshold_value": round(self.threshold_value, 4),
            "timestamp": self.timestamp or time.time(),
        }


@dataclass
class SafetyReport:
    report_id: str
    passed: bool
    violations: list[SafetyViolation]
    fallback_used: bool
    fallback_value: float | None = None
    timestamp: float = 0.0
    schema_version: str = SAFETY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "fallback_used": self.fallback_used,
            "fallback_value": (
                round(self.fallback_value, 4) if self.fallback_value is not None else None
            ),
            "timestamp": self.timestamp or time.time(),
            "schema_version": self.schema_version,
        }


class ConstraintValidator:
    def __init__(self, constraints: dict[str, dict[str, float]] | None = None) -> None:
        self._constraints = constraints or {}

    def set_constraint(self, rule_name: str, min_val: float, max_val: float) -> None:
        self._constraints[rule_name] = {"min": min_val, "max": max_val}

    def validate(self, name: str, value: float) -> SafetyViolation | None:
        constraint = self._constraints.get(name)
        if constraint is None:
            return None
        if value < constraint["min"]:
            return SafetyViolation(
                rule_name=f"{name}_min",
                severity=Severity.WARNING,
                message=f"Value {value:.4f} below minimum {constraint['min']}",
                current_value=value,
                threshold_value=constraint["min"],
            )
        if value > constraint["max"]:
            return SafetyViolation(
                rule_name=f"{name}_max",
                severity=Severity.WARNING,
                message=f"Value {value:.4f} above maximum {constraint['max']}",
                current_value=value,
                threshold_value=constraint["max"],
            )
        return None


class BoundsChecker:
    def __init__(self, global_min: float = 0.0, global_max: float = 1.0) -> None:
        self._global_min = global_min
        self._global_max = global_max
        self._per_type: dict[str, tuple[float, float]] = {}

    def set_bounds(self, prediction_type: str, min_val: float, max_val: float) -> None:
        self._per_type[prediction_type] = (min_val, max_val)

    def check(self, prediction_type: str, value: float) -> SafetyViolation | None:
        min_val, max_val = self._per_type.get(prediction_type, (self._global_min, self._global_max))
        if value < min_val:
            return SafetyViolation(
                rule_name=f"bounds_{prediction_type}_min",
                severity=Severity.ERROR,
                message=f"Prediction {value:.4f} below bound {min_val}",
                current_value=value,
                threshold_value=min_val,
            )
        if value > max_val:
            return SafetyViolation(
                rule_name=f"bounds_{prediction_type}_max",
                severity=Severity.ERROR,
                message=f"Prediction {value:.4f} above bound {max_val}",
                current_value=value,
                threshold_value=max_val,
            )
        return None


class FallbackHandler:
    def __init__(self, default_value: float = 0.0, strategy: str = "constant") -> None:
        self._default = default_value
        self._strategy = strategy
        self._fallbacks: dict[str, float] = {}

    def set_fallback(self, prediction_type: str, value: float) -> None:
        self._fallbacks[prediction_type] = value

    def apply(self, prediction_type: str, current_value: float) -> tuple[float, bool]:
        if math.isnan(current_value) or math.isinf(current_value):
            return self._fallbacks.get(prediction_type, self._default), True
        if prediction_type in self._fallbacks:
            fb = self._fallbacks[prediction_type]
            if current_value > fb:
                return fb, True
        return current_value, False


class SafetyGuard:
    def __init__(
        self,
        constraints: dict[str, dict[str, float]] | None = None,
        bounds: dict[str, tuple[float, float]] | None = None,
        fallbacks: dict[str, float] | None = None,
        callbacks: list[Callable[[SafetyReport], None]] | None = None,
    ) -> None:
        self._validator = ConstraintValidator(constraints)
        self._bounds_checker = BoundsChecker()
        self._fallback = FallbackHandler()
        self._callbacks = callbacks or []
        if bounds:
            for ptype, (mn, mx) in bounds.items():
                self._bounds_checker.set_bounds(ptype, mn, mx)
        if fallbacks:
            for ptype, val in fallbacks.items():
                self._fallback.set_fallback(ptype, val)

    def check_prediction(
        self,
        prediction_type: str,
        value: float,
        extra_constraints: dict[str, float] | None = None,
    ) -> SafetyReport:
        violations: list[SafetyViolation] = []
        bounds_v = self._bounds_checker.check(prediction_type, value)
        if bounds_v:
            violations.append(bounds_v)
        if extra_constraints:
            for name, val in extra_constraints.items():
                cv = self._validator.validate(name, val)
                if cv:
                    violations.append(cv)
        fallback_value, fallback_used = self._fallback.apply(prediction_type, value)
        passed = len(violations) == 0
        report = SafetyReport(
            report_id=f"sr_{uuid.uuid4().hex[:12]}",
            passed=passed,
            violations=violations,
            fallback_used=fallback_used,
            fallback_value=fallback_value if fallback_used else None,
        )
        for cb in self._callbacks:
            cb(report)
        return report

    def add_callback(self, cb: Callable[[SafetyReport], None]) -> None:
        self._callbacks.append(cb)
