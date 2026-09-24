from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto

import ulid

from intelgraph.core.evidence import Evidence, Provenance


class EntityType(Enum):
    PERSON = auto()
    COMPANY = auto()
    DOMAIN = auto()
    EMAIL = auto()
    USERNAME = auto()
    IP_ADDRESS = auto()
    TECHNOLOGY = auto()
    CERTIFICATE = auto()
    CVE = auto()

    @property
    def type_name(self) -> str:
        return self.name.lower()


def _generate_id() -> str:
    return str(ulid.new())


@dataclass(frozen=True)
class BaseEntity:
    id: str = field(default_factory=_generate_id)
    version: int = 1
    entity_type: EntityType = field(init=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    first_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    aliases: tuple[str, ...] = field(default_factory=tuple)
    confidence_score: int = 0
    trust_score: int = 0
    provenance: tuple[Provenance, ...] = field(default_factory=tuple)
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_score <= 100:
            raise ValueError(f"confidence_score must be 0-100, got {self.confidence_score}")
        if not 0 <= self.trust_score <= 100:
            raise ValueError(f"trust_score must be 0-100, got {self.trust_score}")
