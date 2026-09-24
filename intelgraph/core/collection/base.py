import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import ulid

from intelgraph.core.evidence import Evidence, Provenance, SourceLineage


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CollectionDocument:
    id: str = field(default_factory=lambda: str(ulid.new()))
    content: str = ""
    content_type: str = "text"
    metadata: dict[str, Any] = field(default_factory=dict)
    source_url: str = ""
    collected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash and self.content:
            object.__setattr__(self, "content_hash", _content_hash(self.content))


@dataclass
class CollectionResult:
    collector_name: str = ""
    target: str = ""
    raw_data: str = ""
    documents: list[CollectionDocument] = field(default_factory=list)
    provenance: Provenance | None = None
    evidence: list[Evidence] = field(default_factory=list)
    source_metadata: dict[str, Any] = field(default_factory=dict)
    collection_time_ms: float = 0.0
    success: bool = True
    error: str | None = None


class Collector(ABC):
    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        self._name = name
        self._config = config or {}

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def collect(self, target: str, **kwargs: Any) -> CollectionResult: ...

    @abstractmethod
    def validate_target(self, target: str) -> bool: ...

    def make_provenance(
        self, collection_id: str, target: str, source_lineage: SourceLineage | None = None
    ) -> Provenance:
        return Provenance(
            collection_id=collection_id,
            collector_name=self._name,
            collected_at=datetime.now(UTC),
            source_lineage=source_lineage,
        )

    def make_evidence(
        self,
        source_url: str,
        content: str,
        source_tier: int,
        trust_score: int,
        reliability_score: int,
    ) -> Evidence:
        return Evidence(
            id=str(ulid.new()),
            source=source_url,
            content=content[:1000],
            collected_at=datetime.now(UTC),
            source_tier=source_tier,
            trust_score=trust_score,
            reliability_score=reliability_score,
        )

    def dry_run(self, target: str) -> dict[str, Any]:
        return {
            "collector": self._name,
            "target": target,
            "valid": self.validate_target(target),
            "dry_run": True,
        }
