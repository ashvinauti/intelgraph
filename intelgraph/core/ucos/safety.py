from __future__ import annotations

import time
import uuid
from typing import Any


class UnifiedSafetyLayer:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._kill_switch = False
        self._quarantine_mode = False
        self._safe_degradation = False
        self._incidents: list[dict[str, Any]] = []
        self._sandbox_level = self._cfg.get("sandbox_level", "medium")

    def check_safety(self, action: dict[str, Any]) -> dict[str, Any]:
        if self._kill_switch:
            return {
                "safe": False,
                "reason": "Global kill-switch engaged",
                "action": action.get("type", ""),
            }
        action_type = action.get("type", "")
        risk = action.get("risk", 0.0)
        if self._quarantine_mode and risk > 0.3:
            return {
                "safe": False,
                "reason": "Quarantine mode: high-risk blocked",
                "action": action_type,
            }
        if self._safe_degradation and risk > 0.6:
            return {
                "safe": False,
                "reason": "Safe degradation: risk threshold lowered",
                "action": action_type,
            }
        if risk > 0.9:
            return {"safe": False, "reason": "Risk exceeds maximum 0.9", "action": action_type}
        return {"safe": True, "reason": "Safety check passed", "action": action_type}

    def engage_kill_switch(self) -> None:
        self._kill_switch = True
        self._log_incident("kill_switch_engaged", "critical")

    def disengage_kill_switch(self) -> None:
        self._kill_switch = False
        self._log_incident("kill_switch_disengaged", "info")

    def enter_quarantine(self) -> None:
        self._quarantine_mode = True
        self._log_incident("quarantine_entered", "high")

    def exit_quarantine(self) -> None:
        self._quarantine_mode = False
        self._log_incident("quarantine_exited", "info")

    def enable_safe_degradation(self) -> None:
        self._safe_degradation = True
        self._log_incident("safe_degradation_enabled", "high")

    def disable_safe_degradation(self) -> None:
        self._safe_degradation = False
        self._log_incident("safe_degradation_disabled", "info")

    def detect_runaway_loop(self, recent_actions: list[dict[str, Any]]) -> bool:
        if len(recent_actions) < 3:
            return False
        last_types = [a.get("type", "") for a in recent_actions[-10:]]
        if len(last_types) >= 5 and len(set(last_types[-5:])) == 1:
            self._log_incident("runaway_loop_detected", "critical")
            return True
        return False

    def _log_incident(self, incident_type: str, severity: str) -> None:
        self._incidents.append(
            {
                "incident_id": f"si_{uuid.uuid4().hex[:12]}",
                "type": incident_type,
                "severity": severity,
                "timestamp": time.time(),
            }
        )

    def get_incidents(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._incidents[-limit:]

    def get_status(self) -> dict[str, Any]:
        return {
            "kill_switch": self._kill_switch,
            "quarantine": self._quarantine_mode,
            "safe_degradation": self._safe_degradation,
            "sandbox_level": self._sandbox_level,
            "incident_count": len(self._incidents),
        }
