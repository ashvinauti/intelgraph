from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from intelgraph.core.playbook.defaults import DEFAULT_PLAYBOOKS
from intelgraph.core.playbook.models import (
    Playbook,
    PlaybookStatus,
    status_from_dict,
    step_to_status,
)


class PlaybookEngine:
    """Matches incidents to playbooks and tracks execution status."""

    def __init__(self, playbooks: list[Playbook] | None = None) -> None:
        self._playbooks = playbooks or DEFAULT_PLAYBOOKS
        self._statuses: dict[str, PlaybookStatus] = {}  # incident_id -> PlaybookStatus

    def match_playbooks(self, incident: dict[str, Any]) -> list[Playbook]:
        """Return playbooks matching an incident's attributes, sorted by relevance."""
        category = (incident.get("category") or "").lower()
        severity = (incident.get("severity") or "").lower()
        entity_id = (incident.get("entity_id") or "").lower()
        message = (incident.get("message") or "").lower()
        known_ransomware = incident.get("known_ransomware_use", False)

        matched: list[tuple[Playbook, float]] = []

        for pb in self._playbooks:
            score = 0.0
            tc = pb.trigger_conditions

            # Alert category match
            if tc.alert_categories:
                for ac in tc.alert_categories:
                    if ac.lower() in category or ac.lower() in message:
                        score += 30.0
                        break

            # Severity match
            if severity in tc.severities:
                score += 25.0

            # Entity type match — infer from entity_id or message
            etype_match = False
            for et in tc.entity_types:
                if et.lower() in entity_id:
                    etype_match = True
                    break
                # Also check message for type clues
                if et.replace("_", "") in message:
                    etype_match = True
                    break
            if etype_match:
                score += 20.0

            # Ransomware flag
            if tc.known_ransomware is True and known_ransomware:
                score += 40.0
            elif tc.known_ransomware is False and not known_ransomware:
                score += 10.0

            # Confidence
            confidence = (
                incident.get("confidence", 0)
                if isinstance(incident.get("confidence"), (int, float))
                else 0.5
            )
            if confidence >= tc.confidence_min:
                score += 15.0

            if score > 0:
                matched.append((pb, score))

        matched.sort(key=lambda x: -x[1])
        return [pb for pb, _ in matched]

    def start_playbook(self, incident_id: str, playbook: Playbook) -> PlaybookStatus:
        """Start a playbook for an incident, creating initial step statuses."""
        status = PlaybookStatus(
            playbook_id=playbook.playbook_id,
            playbook_name=playbook.name,
            incident_id=incident_id,
            matched_at=datetime.now(UTC).isoformat(),
            steps=[step_to_status(s) for s in sorted(playbook.steps, key=lambda s: s.order)],
        )
        self._statuses[incident_id] = status
        return status

    def get_playbook_status(self, incident_id: str) -> PlaybookStatus | None:
        """Return the current playbook status for an incident."""
        return self._statuses.get(incident_id)

    def complete_step(
        self,
        incident_id: str,
        step_id: str,
        completed_by: str = "system",
        notes: str = "",
    ) -> PlaybookStatus | None:
        """Mark a step as completed."""
        status = self._statuses.get(incident_id)
        if not status:
            return None
        for step in status.steps:
            if step.step_id == step_id and not step.completed:
                step.completed = True
                step.completed_at = datetime.now(UTC).isoformat()
                step.completed_by = completed_by
                step.notes = notes
                break
        # Check if all required steps are done
        if all(s.completed for s in status.steps if s.required):
            status.all_completed = True
            status.completed_at = datetime.now(UTC).isoformat()
        return status

    def apply_automated_steps(self, incident_id: str, playbook: Playbook) -> PlaybookStatus:
        """Execute all automated steps immediately."""
        status = self.start_playbook(incident_id, playbook)
        for step in playbook.steps:
            if step.automated:
                self.complete_step(
                    incident_id,
                    step.step_id,
                    completed_by="system",
                    notes=f"Automated: {step.description}",
                )
        return status

    def to_dicts(self) -> dict[str, dict[str, Any]]:
        """Serialize all statuses (for storage)."""
        result = {}
        for incident_id, status in self._statuses.items():
            result[incident_id] = {
                "playbook_id": status.playbook_id,
                "playbook_name": status.playbook_name,
                "incident_id": status.incident_id,
                "matched_at": status.matched_at,
                "steps": [
                    {
                        "step_id": s.step_id,
                        "action_type": s.action_type,
                        "description": s.description,
                        "automated": s.automated,
                        "required": s.required,
                        "completed": s.completed,
                        "completed_at": s.completed_at,
                        "completed_by": s.completed_by,
                        "notes": s.notes,
                    }
                    for s in status.steps
                ],
                "all_completed": status.all_completed,
                "completed_at": status.completed_at,
            }
        return result

    def restore_from_dicts(self, data: dict[str, dict[str, Any]]) -> None:
        """Restore statuses from serialized dicts."""
        for incident_id, d in data.items():
            self._statuses[incident_id] = status_from_dict(d)
