from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class StepActionType(Enum):
    INVESTIGATE = auto()
    BLOCK = auto()
    PATCH = auto()
    NOTIFY = auto()
    ESCALATE = auto()
    MONITOR = auto()
    ISOLATE = auto()
    RESTORE = auto()
    SINKHOLE = auto()
    SCAN = auto()


@dataclass
class PlaybookStep:
    step_id: str
    action_type: StepActionType
    description: str
    automated: bool = False
    required: bool = True
    order: int = 0


@dataclass
class PlaybookStepStatus:
    step_id: str
    action_type: str
    description: str
    automated: bool
    required: bool
    completed: bool = False
    completed_at: str | None = None
    completed_by: str | None = None
    notes: str | None = None


@dataclass
class TriggerCondition:
    alert_categories: list[str] = field(default_factory=list)
    severities: list[str] = field(default_factory=list)
    entity_types: list[str] = field(default_factory=list)
    known_ransomware: bool | None = None
    confidence_min: float = 0.0
    contradiction_max: float = 100.0


@dataclass
class Playbook:
    playbook_id: str
    name: str
    description: str
    trigger_conditions: TriggerCondition
    steps: list[PlaybookStep] = field(default_factory=list)
    severity_level: str = "medium"
    entity_types: list[str] = field(default_factory=list)


@dataclass
class PlaybookStatus:
    playbook_id: str
    playbook_name: str
    incident_id: str
    matched_at: str
    steps: list[PlaybookStepStatus] = field(default_factory=list)
    all_completed: bool = False
    completed_at: str | None = None


def step_to_status(step: PlaybookStep) -> PlaybookStepStatus:
    return PlaybookStepStatus(
        step_id=step.step_id,
        action_type=step.action_type.name.lower(),
        description=step.description,
        automated=step.automated,
        required=step.required,
    )


def status_from_dict(data: dict[str, Any]) -> PlaybookStatus:
    steps = [PlaybookStepStatus(**s) for s in data.get("steps", [])]
    return PlaybookStatus(
        playbook_id=data["playbook_id"],
        playbook_name=data["playbook_name"],
        incident_id=data["incident_id"],
        matched_at=data["matched_at"],
        steps=steps,
        all_completed=data.get("all_completed", False),
        completed_at=data.get("completed_at"),
    )
