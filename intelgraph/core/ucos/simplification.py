from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


class SimplificationEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._modules: dict[str, dict[str, Any]] = {}
        self._violations: list[dict[str, Any]] = []
        self._complexity_trend: list[float] = []

    def register_module(self, module_id: str, function: str, owner: str) -> None:
        self._modules[module_id] = {
            "module_id": module_id,
            "function": function,
            "owner": owner,
            "status": "active",
            "registered_at": time.time(),
        }

    def check_no_duplicates(self) -> list[dict[str, Any]]:
        by_function: dict[str, list[str]] = defaultdict(list)
        for mid, mod in self._modules.items():
            by_function[mod["function"]].append(mid)
        violations = []
        for fn, mids in by_function.items():
            if len(mids) > 1:
                violations.append(
                    {
                        "rule": "no_duplicate_modules",
                        "function": fn,
                        "modules": mids,
                        "count": len(mids),
                        "severity": "high",
                    }
                )
        self._violations.extend(violations)
        return violations

    def check_single_owner(self) -> list[dict[str, Any]]:
        by_owner: dict[str, list[str]] = defaultdict(list)
        for mid, mod in self._modules.items():
            by_owner[mod["owner"]].append(mid)
        violations = []
        for owner, mids in by_owner.items():
            if len(mids) > 5:
                violations.append(
                    {
                        "rule": "single_responsibility",
                        "owner": owner,
                        "module_count": len(mids),
                        "severity": "medium",
                    }
                )
        return violations

    def compute_system_complexity(self) -> float:
        active = [m for m in self._modules.values() if m.get("status") == "active"]
        dups = len(self.check_no_duplicates())
        complexity = len(active) * 0.1 + dups * 0.3
        self._complexity_trend.append(complexity)
        if len(self._complexity_trend) > 100:
            self._complexity_trend = self._complexity_trend[-100:]
        return complexity

    def is_complexity_decreasing(self) -> bool:
        if len(self._complexity_trend) < 2:
            return True
        return self._complexity_trend[-1] < self._complexity_trend[-2]

    def get_violations(self) -> list[dict[str, Any]]:
        return list(self._violations)

    def get_modules(self) -> dict[str, dict[str, Any]]:
        return dict(self._modules)
