"""Investigation workspace data models.

An Investigation groups related findings around a starting IOC, allows
analysts to build a timeline, and attach notes. The pivot engine walks
the in-memory knowledge graph to surface related infrastructure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any


class InvestigationStatus(Enum):
    OPEN = auto()
    IN_PROGRESS = auto()
    CLOSED = auto()

    def __str__(self) -> str:
        return self.name.lower()


class FindingType(Enum):
    DIRECT = auto()
    PIVOT = auto()
    ENRICHMENT = auto()

    def __str__(self) -> str:
        return self.name.lower()


@dataclass
class TimelineEvent:
    event_id: str
    investigation_id: str
    timestamp: datetime
    event_type: str
    title: str
    description: str
    source: str = "analyst"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "investigation_id": self.investigation_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "metadata": self.metadata,
        }


@dataclass
class Note:
    note_id: str
    investigation_id: str
    author: str
    content: str
    created_at: datetime
    pinned: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "note_id": self.note_id,
            "investigation_id": self.investigation_id,
            "author": self.author,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "pinned": self.pinned,
        }


@dataclass
class Finding:
    finding_id: str
    investigation_id: str
    ioc_value: str
    ioc_type: str
    finding_type: str
    confidence: int
    evidence_summary: str
    related_entity_id: str | None = None
    relationships: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "investigation_id": self.investigation_id,
            "ioc_value": self.ioc_value,
            "ioc_type": self.ioc_type,
            "finding_type": self.finding_type,
            "confidence": self.confidence,
            "evidence_summary": self.evidence_summary,
            "related_entity_id": self.related_entity_id,
            "relationships": self.relationships,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Investigation:
    investigation_id: str
    name: str
    seed_ioc: str
    seed_ioc_type: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    status: InvestigationStatus = InvestigationStatus.OPEN
    findings: list[Finding] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "investigation_id": self.investigation_id,
            "name": self.name,
            "seed_ioc": self.seed_ioc,
            "seed_ioc_type": self.seed_ioc_type,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": str(self.status),
            "findings": [f.to_dict() for f in self.findings],
            "timeline": [t.to_dict() for t in self.timeline],
            "notes": [n.to_dict() for n in self.notes],
            "tags": self.tags,
            "finding_count": len(self.findings),
            "note_count": len(self.notes),
        }