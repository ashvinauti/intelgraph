from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any

import ulid


class VerificationState(Enum):
    CONFIRMED = auto()
    PROBABLE = auto()
    POSSIBLE = auto()
    SPECULATIVE = auto()

    @property
    def name_lower(self) -> str:
        return self.name.lower()


class OperationalState(Enum):
    ACTIVE = auto()
    CONTESTED = auto()
    DEBUNKED = auto()
    ARCHIVED = auto()

    @property
    def name_lower(self) -> str:
        return self.name.lower()


@dataclass
class VerificationRecord:
    verification_id: str = field(default_factory=lambda: str(ulid.new()))
    entity_id: str = ""
    entity_type: str = ""
    verification_state: VerificationState = VerificationState.SPECULATIVE
    operational_state: OperationalState = OperationalState.ACTIVE
    confidence: float = 0.0
    consensus: float = 0.0
    contradiction: float = 0.0
    source_count: int = 0
    human_review_boost: float = 0.0
    matched_rules: list[str] = field(default_factory=list)
    reasoning: str = ""
    computation_steps: list[str] = field(default_factory=list)
    version: int = 1
    is_high_impact: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "verification_state": self.verification_state.name_lower,
            "operational_state": self.operational_state.name_lower,
            "confidence": self.confidence,
            "consensus": self.consensus,
            "contradiction": self.contradiction,
            "source_count": self.source_count,
            "human_review_boost": self.human_review_boost,
            "matched_rules": self.matched_rules,
            "reasoning": self.reasoning,
            "computation_steps": self.computation_steps,
            "version": self.version,
            "is_high_impact": self.is_high_impact,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
