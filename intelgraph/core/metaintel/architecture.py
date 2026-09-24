from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class ArchitectureModule:
    module_id: str
    name: str
    module_type: str
    status: str
    dependencies: list[str]
    version: int
    health_score: float
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "name": self.name,
            "module_type": self.module_type,
            "status": self.status,
            "dependencies": self.dependencies,
            "version": self.version,
            "health_score": round(self.health_score, 4),
        }


@dataclass
class ArchitectureProposal:
    proposal_id: str
    description: str
    action: str
    target_module: str
    new_dependencies: list[str]
    risk_score: float
    expected_benefit: str
    status: str
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "description": self.description,
            "action": self.action,
            "target_module": self.target_module,
            "new_dependencies": self.new_dependencies,
            "risk_score": round(self.risk_score, 4),
            "expected_benefit": self.expected_benefit,
            "status": self.status,
        }


class ArchitectureEvolutionEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._modules: dict[str, ArchitectureModule] = {}
        self._proposals: list[ArchitectureProposal] = []
        self._dependency_graph: dict[str, list[str]] = {}
        self._topology_history: list[dict[str, Any]] = []
        self._register_default_modules()

    def _register_default_modules(self) -> None:
        defaults = [
            ("nlp", "knowledge_extraction"),
            ("reasoning", "cognitive_reasoning"),
            ("execution", "agent_orchestration"),
            ("governance", "policy_enforcement"),
            ("metaintel", "meta_intelligence"),
            ("storage", "data_persistence"),
            ("api", "api_gateway"),
        ]
        for mid, mtype in defaults:
            self._modules[mid] = ArchitectureModule(
                module_id=mid,
                name=mid,
                module_type=mtype,
                status="active",
                dependencies=[],
                version=1,
                health_score=1.0,
                created_at=time.time(),
            )
            self._dependency_graph[mid] = []

    def propose_architecture_change(
        self,
        description: str,
        action: str,
        target_module: str,
        new_dependencies: list[str] | None = None,
        risk_score: float = 0.5,
    ) -> ArchitectureProposal:
        proposal = ArchitectureProposal(
            proposal_id=f"arch_{uuid.uuid4().hex[:12]}",
            description=description,
            action=action,
            target_module=target_module,
            new_dependencies=new_dependencies or [],
            risk_score=risk_score,
            expected_benefit=self._estimate_benefit(action, target_module),
            status="pending",
            created_at=time.time(),
        )
        self._proposals.append(proposal)
        return proposal

    def _estimate_benefit(self, action: str, target: str) -> str:
        if action == "add_module":
            return f"Extends system capability in {target}"
        if action == "remove_module":
            return f"Reduces complexity in {target}"
        if action == "modify_dependencies":
            return f"Optimizes data flow for {target}"
        if action == "merge_modules":
            return "Consolidates overlapping functionality"
        return "General architecture improvement"

    def apply_change(self, proposal_id: str) -> bool:
        proposal = next((p for p in self._proposals if p.proposal_id == proposal_id), None)
        if not proposal or proposal.status != "pending":
            return False
        if proposal.action == "add_module":
            old_graph = {k: list(v) for k, v in self._dependency_graph.items()}
            self._modules[proposal.target_module] = ArchitectureModule(
                module_id=proposal.target_module,
                name=proposal.target_module,
                module_type="custom",
                status="active",
                dependencies=proposal.new_dependencies,
                version=1,
                health_score=0.8,
                created_at=time.time(),
            )
            self._dependency_graph[proposal.target_module] = list(proposal.new_dependencies)
            if self.detect_cycles():
                del self._modules[proposal.target_module]
                self._dependency_graph = old_graph
                return False
        elif proposal.action == "remove_module":
            self._modules.pop(proposal.target_module, None)
            self._dependency_graph.pop(proposal.target_module, None)
            for deps in self._dependency_graph.values():
                if proposal.target_module in deps:
                    deps.remove(proposal.target_module)
        elif proposal.action == "modify_dependencies":
            old_graph = {k: list(v) for k, v in self._dependency_graph.items()}
            if proposal.target_module in self._dependency_graph:
                self._dependency_graph[proposal.target_module] = list(proposal.new_dependencies)
            if self.detect_cycles():
                self._dependency_graph = old_graph
                return False
            if proposal.target_module in self._modules:
                self._modules[proposal.target_module].dependencies = list(proposal.new_dependencies)
        elif proposal.action == "merge_modules":
            self._modules[proposal.target_module] = ArchitectureModule(
                module_id=proposal.target_module,
                name=proposal.target_module,
                module_type=proposal.target_module,
                status="active",
                dependencies=proposal.new_dependencies,
                version=1,
                health_score=0.8,
                created_at=time.time(),
            )
            self._dependency_graph[proposal.target_module] = list(proposal.new_dependencies)
        proposal.status = "applied"
        self._topology_history.append(
            {
                "proposal_id": proposal_id,
                "timestamp": time.time(),
                "action": proposal.action,
                "target": proposal.target_module,
            }
        )
        return True

    def detect_cycles(self) -> list[list[str]]:
        visited: set[str] = set()
        in_stack: set[str] = set()
        cycles: list[list[str]] = []
        path: list[str] = []

        def _dfs(node: str) -> None:
            visited.add(node)
            in_stack.add(node)
            path.append(node)
            for dep in self._dependency_graph.get(node, []):
                if dep not in visited:
                    _dfs(dep)
                elif dep in in_stack:
                    cycle_start = path.index(dep)
                    cycles.append(path[cycle_start:] + [dep])
            path.pop()
            in_stack.discard(node)

        for node in self._dependency_graph:
            if node not in visited:
                _dfs(node)
        return cycles

    def get_topology(self) -> dict[str, list[str]]:
        return dict(self._dependency_graph)

    def get_modules(self) -> list[ArchitectureModule]:
        return list(self._modules.values())

    def get_proposals(self, status: str | None = None) -> list[ArchitectureProposal]:
        if status:
            return [p for p in self._proposals if p.status == status]
        return list(self._proposals)
