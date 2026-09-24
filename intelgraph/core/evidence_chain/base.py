import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any

import ulid


class SupportType(Enum):
    SUPPORTS = auto()
    CONTRADICTS = auto()
    NEUTRAL = auto()

    @property
    def name_lower(self) -> str:
        return self.name.lower()


class EvidenceStatus(Enum):
    VERIFIED = auto()
    CONTESTED = auto()
    UNKNOWN = auto()
    DEBUNKED = auto()

    @property
    def name_lower(self) -> str:
        return self.name.lower()


def _chain_id(entity_id: str) -> str:
    return hashlib.sha256(entity_id.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str = field(default_factory=lambda: str(ulid.new()))
    source_id: str = ""
    document_id: str = ""
    claim: str = ""
    support_type: SupportType = SupportType.NEUTRAL
    confidence: float = 0.0
    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 100.0:
            raise ValueError(f"confidence must be 0-100, got {self.confidence}")
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        if not self.claim:
            raise ValueError("claim must not be empty")


@dataclass
class EvidenceChain:
    chain_id: str = ""
    entity_id: str = ""
    evidence: list[EvidenceItem] = field(default_factory=list)
    confidence: float = 0.0
    contradiction_score: float = 0.0
    status: EvidenceStatus = EvidenceStatus.UNKNOWN
    version: int = 1
    source_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def recompute_id(self) -> None:
        if not self.chain_id:
            self.chain_id = _chain_id(self.entity_id)

    def add_item(self, item: EvidenceItem) -> None:
        self.evidence.append(item)
        self.version += 1
        self.updated_at = datetime.now(UTC)
        self.source_count = len({e.source_id for e in self.evidence})

    def remove_item(self, evidence_id: str) -> bool:
        before = len(self.evidence)
        self.evidence = [e for e in self.evidence if e.evidence_id != evidence_id]
        removed = len(self.evidence) < before
        if removed:
            self.version += 1
            self.updated_at = datetime.now(UTC)
            self.source_count = len({e.source_id for e in self.evidence})
        return removed

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "entity_id": self.entity_id,
            "evidence": [
                {
                    "evidence_id": e.evidence_id,
                    "source_id": e.source_id,
                    "document_id": e.document_id,
                    "claim": e.claim,
                    "support_type": e.support_type.name_lower,
                    "confidence": e.confidence,
                    "extracted_at": e.extracted_at.isoformat(),
                    "metadata": e.metadata,
                }
                for e in self.evidence
            ],
            "confidence": self.confidence,
            "contradiction_score": self.contradiction_score,
            "status": self.status.name_lower,
            "version": self.version,
            "source_count": self.source_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
