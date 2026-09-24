from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class SourceLineage:
    source_id: str
    source_url: str
    intermediate_sources: tuple["SourceLineage", ...] = field(default_factory=tuple)

    def lineage_chain(self) -> list[str]:
        chain = [self.source_url]
        for src in self.intermediate_sources:
            chain.extend(src.lineage_chain())
        return chain


@dataclass(frozen=True)
class Evidence:
    id: str
    source: str
    content: str
    collected_at: datetime
    source_tier: int
    trust_score: int
    reliability_score: int

    def __post_init__(self) -> None:
        if self.source_tier not in (1, 2, 3):
            raise ValueError(f"source_tier must be 1, 2, or 3, got {self.source_tier}")
        if not 0 <= self.trust_score <= 100:
            raise ValueError(f"trust_score must be 0-100, got {self.trust_score}")
        if not 0 <= self.reliability_score <= 100:
            raise ValueError(f"reliability_score must be 0-100, got {self.reliability_score}")
        if not self.id:
            raise ValueError("evidence id must not be empty")


@dataclass(frozen=True)
class Provenance:
    collection_id: str
    collector_name: str
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    source_lineage: SourceLineage | None = None
