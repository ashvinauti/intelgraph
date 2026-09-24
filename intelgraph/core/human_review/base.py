from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any

import ulid


class ReviewOutcome(Enum):
    APPROVED_REVIEW = auto()
    REJECTED_REVIEW = auto()
    NEEDS_MORE_EVIDENCE = auto()

    @property
    def name_lower(self) -> str:
        return self.name.lower()


@dataclass
class ReviewRecord:
    review_id: str = field(default_factory=lambda: str(ulid.new()))
    entity_id: str = ""
    entity_type: str = ""
    outcome: ReviewOutcome = ReviewOutcome.NEEDS_MORE_EVIDENCE
    reviewer: str = ""
    review_notes: str = ""
    confidence_influence: float = 0.0
    contradiction_influence: float = 0.0
    previous_chain_confidence: float = 0.0
    new_chain_confidence: float = 0.0
    previous_chain_version: int = 0
    new_chain_version: int = 0
    source_evidence_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reviewed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "outcome": self.outcome.name_lower,
            "reviewer": self.reviewer,
            "review_notes": self.review_notes,
            "confidence_influence": self.confidence_influence,
            "contradiction_influence": self.contradiction_influence,
            "previous_chain_confidence": self.previous_chain_confidence,
            "new_chain_confidence": self.new_chain_confidence,
            "previous_chain_version": self.previous_chain_version,
            "new_chain_version": self.new_chain_version,
            "source_evidence_ids": self.source_evidence_ids,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }
