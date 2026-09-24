from dataclasses import dataclass, field

from intelgraph.core.entity.base import BaseEntity, EntityType


@dataclass(frozen=True)
class Email(BaseEntity):
    entity_type: EntityType = field(default=EntityType.EMAIL, init=False)
    address: str = ""
    domain: str = ""
    associated_accounts: tuple[str, ...] = field(default_factory=tuple)
