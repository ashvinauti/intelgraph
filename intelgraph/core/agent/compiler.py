from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompiledAction:
    action_id: str
    description: str
    source_hypothesis: str
    source_trace_id: str
    tool_type: str
    tool_action: str
    params: dict[str, Any]
    risk_score: float
    confidence: float
    estimated_cost: float
    alternative_actions: list[str] = field(default_factory=list)
    rollback_action_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "description": self.description,
            "source_hypothesis": self.source_hypothesis,
            "source_trace_id": self.source_trace_id,
            "tool_type": self.tool_type,
            "tool_action": self.tool_action,
            "risk_score": round(self.risk_score, 4),
            "confidence": round(self.confidence, 4),
            "estimated_cost": round(self.estimated_cost, 4),
            "has_alternatives": len(self.alternative_actions) > 0,
            "has_rollback": bool(self.rollback_action_id),
        }


class ReasoningCompiler:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._min_confidence = self._cfg.get("min_execution_confidence", 0.3)
        self._compiled: list[CompiledAction] = []

    def compile_hypothesis(
        self, hypothesis: dict[str, Any], trace_id: str = ""
    ) -> list[CompiledAction]:
        actions: list[CompiledAction] = []
        desc = hypothesis.get("description", "")
        conf = hypothesis.get("confidence", 0.5)
        scenario = hypothesis.get("scenario_type", "unknown")
        if conf < self._min_confidence:
            return actions
        tool_action_map = {
            "command_and_control": ("rest", "get_c2_traffic", {"query": "c2_indicators"}),
            "data_exfiltration": ("database", "query_exfil", {"table": "network_flow"}),
            "lateral_movement": ("rest", "trace_lateral", {"source": "endpoint_logs"}),
            "privilege_escalation": ("internal", "check_permissions", {"target": "user_accounts"}),
            "persistence": ("file", "check_startup", {"path": "/etc/init.d/"}),
            "defense_evasion": ("soc", "check_logs", {"source": "windows_events"}),
            "initial_access": ("rest", "check_exposure", {"type": "vulnerability_scan"}),
            "impact": ("database", "assess_damage", {"scope": "affected_systems"}),
        }
        tool_type, tool_action, params = tool_action_map.get(
            scenario, ("internal", "analyze", {"hypothesis": desc})
        )
        action = CompiledAction(
            action_id=f"act_{uuid.uuid4().hex[:12]}",
            description=f"Investigate {scenario}: {desc}",
            source_hypothesis=hypothesis.get("hypothesis_id", ""),
            source_trace_id=trace_id,
            tool_type=tool_type,
            tool_action=tool_action,
            params=params,
            risk_score=0.5 if tool_type != "soc" else 0.7,
            confidence=conf,
            estimated_cost=0.5,
            alternative_actions=[f"alt_{uuid.uuid4().hex[:8]}"],
            rollback_action_id=f"rb_{uuid.uuid4().hex[:12]}",
        )
        actions.append(action)
        self._compiled.append(action)
        return actions

    def compile_trace(self, reasoning_path: dict[str, Any]) -> CompiledAction:
        steps = reasoning_path.get("steps", [])
        conf = reasoning_path.get("total_confidence", 0.5)
        action = CompiledAction(
            action_id=f"act_{uuid.uuid4().hex[:12]}",
            description=f"Execute reasoning path with {len(steps)} steps",
            source_hypothesis="",
            source_trace_id=reasoning_path.get("path_id", ""),
            tool_type="internal",
            tool_action="trace_execution",
            params={"steps": steps, "path_id": reasoning_path.get("path_id", "")},
            risk_score=0.4,
            confidence=conf,
            estimated_cost=len(steps) * 0.1,
        )
        self._compiled.append(action)
        return action

    def select_action(
        self, actions: list[CompiledAction], strategy: str = "best"
    ) -> CompiledAction | None:
        if not actions:
            return None
        if strategy == "best":
            return max(actions, key=lambda a: a.confidence * (1 - a.risk_score))
        if strategy == "safe":
            return min(actions, key=lambda a: a.risk_score)
        if strategy == "cheap":
            return min(actions, key=lambda a: a.estimated_cost)
        return actions[0]

    def generate_rollback(self, action: CompiledAction) -> CompiledAction:
        rollback = CompiledAction(
            action_id=f"rb_{uuid.uuid4().hex[:12]}",
            description=f"Rollback: {action.description}",
            source_hypothesis=action.source_hypothesis,
            source_trace_id=action.source_trace_id,
            tool_type=action.tool_type,
            tool_action=f"undo_{action.tool_action}",
            params={
                k: f"original_{v}" if isinstance(v, str) else v for k, v in action.params.items()
            },
            risk_score=max(0.1, action.risk_score - 0.2),
            confidence=action.confidence * 0.8,
            estimated_cost=action.estimated_cost * 0.5,
        )
        action.rollback_action_id = rollback.action_id
        return rollback
