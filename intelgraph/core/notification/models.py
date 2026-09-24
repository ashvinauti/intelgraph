from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class NotificationSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def __ge__(self, other: NotificationSeverity) -> bool:
        order = ["low", "medium", "high", "critical"]
        return order.index(self.value) >= order.index(other.value)


class NotificationStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class NotificationChannel:
    channel_id: str
    channel_type: str  # "email", "webhook", "slack"
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    min_severity: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> NotificationChannel:
        return NotificationChannel(**d)


@dataclass
class NotificationEvent:
    event_id: str
    event_type: str  # "alert", "incident", "threat_score_exceeded", "playbook_step"
    severity: str  # "low", "medium", "high", "critical"
    title: str
    body: str
    entity_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> NotificationEvent:
        return NotificationEvent(**d)


@dataclass
class NotificationHistoryEntry:
    event_id: str
    channel_id: str
    status: str  # NotificationStatus value
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    error: str = ""
    attempt: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> NotificationHistoryEntry:
        return NotificationHistoryEntry(**d)
