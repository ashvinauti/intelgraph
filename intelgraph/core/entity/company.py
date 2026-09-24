from dataclasses import dataclass, field

from intelgraph.core.entity.base import BaseEntity, EntityType


@dataclass(frozen=True)
class Company(BaseEntity):
    entity_type: EntityType = field(default=EntityType.COMPANY, init=False)
    name: str = ""
    legal_name: str = ""
    domain: str = ""
    industry: str = ""
    headquarters: str = ""
    subsidiaries: tuple[str, ...] = field(default_factory=tuple)
