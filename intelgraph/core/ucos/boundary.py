from __future__ import annotations

from typing import Any


class DependencyValidator:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._dependencies: dict[str, list[str]] = {}
        self._violations: list[dict[str, Any]] = []

    def register_module(self, module_id: str, dependencies: list[str]) -> None:
        self._dependencies[module_id] = list(dependencies)

    def validate_no_circular(self) -> list[str]:
        visited: set[str] = set()
        in_stack: set[str] = set()
        cycles: list[list[str]] = []

        def _dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            in_stack.add(node)
            path.append(node)
            for dep in self._dependencies.get(node, []):
                if dep not in visited:
                    _dfs(dep, path)
                elif dep in in_stack:
                    cycle_start = path.index(dep)
                    cycles.append(path[cycle_start:] + [dep])
            path.pop()
            in_stack.discard(node)

        for node in self._dependencies:
            if node not in visited:
                _dfs(node, [])
        cycle_ids = [c[0] for c in cycles] if cycles else []
        if cycles:
            self._violations.append(
                {
                    "type": "circular_dependency",
                    "cycles": cycles,
                    "severity": "critical",
                }
            )
        return cycle_ids

    def validate_all_registered(self, registered_modules: set[str]) -> list[str]:
        unregistered = []
        for module_id, deps in self._dependencies.items():
            for dep in deps:
                if dep not in registered_modules:
                    unregistered.append(f"{module_id} depends on unregistered {dep}")
        if unregistered:
            self._violations.append(
                {
                    "type": "unregistered_dependency",
                    "details": unregistered,
                    "severity": "high",
                }
            )
        return unregistered

    def validate_no_unsafe_injection(self, module_id: str, proposed_dep: str) -> bool:
        if module_id == proposed_dep:
            self._violations.append(
                {
                    "type": "self_dependency",
                    "module": module_id,
                    "severity": "critical",
                }
            )
            return False
        temp = dict(self._dependencies)
        temp.setdefault(module_id, [])
        temp[module_id].append(proposed_dep)
        checker = DependencyValidator()
        checker._dependencies = temp
        cycles = checker.validate_no_circular()
        if cycles:
            self._violations.append(
                {
                    "type": "unsafe_dependency_injection",
                    "module": module_id,
                    "proposed_dep": proposed_dep,
                    "severity": "critical",
                }
            )
            return False
        return True

    def get_violations(self) -> list[dict[str, Any]]:
        return list(self._violations)
