from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class SecurityIncident:
    incident_id: str
    incident_type: str
    severity: str
    source_layer: str
    description: str
    contains_threat: bool
    resolved: bool
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type,
            "severity": self.severity,
            "source_layer": self.source_layer,
            "description": self.description,
            "contains_threat": self.contains_threat,
            "resolved": self.resolved,
        }


class SafetyMetaControlLayer:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._incidents: list[SecurityIncident] = []
        self._kill_switch_global = False
        self._quarantine_mode = False
        self._attack_surface: dict[str, list[str]] = defaultdict(list)
        self._policy_violations: list[dict[str, Any]] = []
        self._contained_loops: list[dict[str, Any]] = []

    def monitor_layer(self, layer_id: str, metrics: dict[str, Any]) -> list[SecurityIncident]:
        incidents = []
        error_rate = metrics.get("error_rate", 0)
        anomaly_count = metrics.get("anomaly_count", 0)
        if error_rate > 0.3:
            incident = SecurityIncident(
                incident_id=f"sec_{uuid.uuid4().hex[:12]}",
                incident_type="high_error_rate",
                severity="high",
                source_layer=layer_id,
                description=f"Error rate {error_rate:.2f} exceeds threshold in {layer_id}",
                contains_threat=True,
                resolved=False,
                timestamp=time.time(),
            )
            self._incidents.append(incident)
            incidents.append(incident)
        if anomaly_count > 10:
            incident = SecurityIncident(
                incident_id=f"sec_{uuid.uuid4().hex[:12]}",
                incident_type="anomaly_spike",
                severity="medium",
                source_layer=layer_id,
                description=f"Anomaly spike ({anomaly_count}) in {layer_id}",
                contains_threat=True,
                resolved=False,
                timestamp=time.time(),
            )
            self._incidents.append(incident)
            incidents.append(incident)
        return incidents

    def detect_unsafe_loops(self, execution_traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
        loops = []
        seen = set()
        for trace in execution_traces:
            action = trace.get("action", "")
            if action in seen:
                loops.append(
                    {"action": action, "repeated": True, "trace_id": trace.get("trace_id", "")}
                )
            seen.add(action)
        if loops:
            self._contained_loops.extend(loops)
        return loops

    def engage_global_kill_switch(self) -> bool:
        self._kill_switch_global = True
        return True

    def disengage_global_kill_switch(self) -> bool:
        self._kill_switch_global = False
        return True

    def enter_quarantine(self) -> bool:
        self._quarantine_mode = True
        return True

    def exit_quarantine(self) -> bool:
        self._quarantine_mode = False
        return True

    def record_policy_violation(
        self, policy_id: str, agent_id: str, details: dict[str, Any]
    ) -> None:
        self._policy_violations.append(
            {
                "policy_id": policy_id,
                "agent_id": agent_id,
                "details": details,
                "time": time.time(),
            }
        )

    def get_active_threats(self) -> list[SecurityIncident]:
        return [i for i in self._incidents if i.contains_threat and not i.resolved]

    def resolve_incident(self, incident_id: str) -> bool:
        incident = next((i for i in self._incidents if i.incident_id == incident_id), None)
        if not incident:
            return False
        incident.resolved = True
        return True

    def get_incidents(self, limit: int = 100) -> list[SecurityIncident]:
        return self._incidents[-limit:]

    def is_system_safe(self) -> bool:
        return not self._kill_switch_global and not self._quarantine_mode
