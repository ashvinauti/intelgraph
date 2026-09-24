from dataclasses import dataclass, field
from datetime import datetime

from intelgraph.core.entity.base import BaseEntity, EntityType


@dataclass(frozen=True)
class Domain(BaseEntity):
    entity_type: EntityType = field(default=EntityType.DOMAIN, init=False)
    domain_name: str = ""
    registrant: str = ""
    registrar: str = ""
    creation_date: datetime | None = None
    expiration_date: datetime | None = None
    nameservers: tuple[str, ...] = field(default_factory=tuple)
    ip_addresses: tuple[str, ...] = field(default_factory=tuple)
    technologies: tuple[str, ...] = field(default_factory=tuple)
