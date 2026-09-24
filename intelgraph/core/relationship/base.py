from dataclasses import dataclass, field
from datetime import UTC, datetime

import ulid

from intelgraph.core.evidence import Evidence, Provenance
from intelgraph.core.relationship.types import RelationshipType


def _generate_id() -> str:
    return str(ulid.new())


@dataclass(frozen=True)
class Relationship:
    id: str = field(default_factory=_generate_id)
    type: RelationshipType = RelationshipType.RELATED_TO
    source_id: str = ""
    target_id: str = ""
    version: int = 1
    confidence_score: int = 0
    trust_weight: int = 0
    evidence_chain: tuple[Evidence, ...] = field(default_factory=tuple)
    provenance: tuple[Provenance, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    first_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    occurrence_count: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_score <= 100:
            raise ValueError(f"confidence_score must be 0-100, got {self.confidence_score}")
        if not 0 <= self.trust_weight <= 100:
            raise ValueError(f"trust_weight must be 0-100, got {self.trust_weight}")
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if not self.target_id:
            raise ValueError("target_id must not be empty")
