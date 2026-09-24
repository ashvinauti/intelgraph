from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentIdentityRecord:
    identity_id: str
    agent_id: str
    role: str
    capabilities: list[str]
    scope: str
    status: str
    overlaps: list[str] = field(default_factory=list)
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_id": self.identity_id,
            "agent_id": self.agent_id,
            "role": self.role,
            "capabilities": self.capabilities,
            "scope": self.scope,
            "status": self.status,
            "overlap_count": len(self.overlaps),
        }


class IdentityConsistencyLayer:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._identities: dict[str, AgentIdentityRecord] = {}
        self._role_registry: dict[str, list[str]] = defaultdict(list)
        self._conflicts: list[dict[str, Any]] = []
        self._authority_map: dict[str, list[str]] = {}

    def register_agent(
        self, agent_id: str, role: str, capabilities: list[str], scope: str = "global"
    ) -> AgentIdentityRecord:
        identity = AgentIdentityRecord(
            identity_id=f"id_{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            role=role,
            capabilities=capabilities,
            scope=scope,
            status="active",
            created_at=time.time(),
        )
        self._identities[agent_id] = identity
        self._role_registry[role].append(agent_id)
        self._detect_overlaps(agent_id)
        return identity

    def _detect_overlaps(self, agent_id: str) -> None:
        identity = self._identities.get(agent_id)
        if not identity:
            return
        for other_id, other in self._identities.items():
            if other_id == agent_id:
                continue
            if set(identity.capabilities) & set(other.capabilities):
                identity.overlaps.append(other_id)
                other.overlaps.append(agent_id)

    def detect_role_conflicts(self) -> list[dict[str, Any]]:
        conflicts = []
        for role, agents in self._role_registry.items():
            if len(agents) > 3:
                conflicts.append(
                    {
                        "type": "role_overpopulation",
                        "role": role,
                        "agent_count": len(agents),
                        "agents": agents,
                    }
                )
        return conflicts

    def detect_intent_conflicts(self, agent_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from collections import Counter

        conflicts = []
        target_actions = Counter()
        for action in agent_actions:
            target = action.get("target", "unknown")
            target_actions[target] += 1
        for target, count in target_actions.items():
            if count > 1:
                conflicts.append(
                    {
                        "type": "target_contention",
                        "target": target,
                        "actor_count": count,
                        "severity": "medium",
                    }
                )
        return conflicts

    def verify_authority(self, agent_id: str, required_role: str) -> bool:
        identity = self._identities.get(agent_id)
        if not identity or identity.status != "active":
            return False
        role_hierarchy = {"user": 0, "analyst": 1, "reviewer": 2, "admin": 3}
        if required_role not in role_hierarchy:
            return False
        required_level = role_hierarchy.get(required_role, 0)
        agent_level = role_hierarchy.get(identity.role, 0)
        return agent_level >= required_level

    def get_identity(self, agent_id: str) -> AgentIdentityRecord | None:
        return self._identities.get(agent_id)

    def list_identities(self) -> list[AgentIdentityRecord]:
        return list(self._identities.values())

    def get_role_assignments(self, role: str) -> list[str]:
        return list(self._role_registry.get(role, []))
