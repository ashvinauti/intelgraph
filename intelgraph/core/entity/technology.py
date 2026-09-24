from dataclasses import dataclass, field

from intelgraph.core.entity.base import BaseEntity, EntityType


@dataclass(frozen=True)
class Technology(BaseEntity):
    entity_type: EntityType = field(default=EntityType.TECHNOLOGY, init=False)
    name: str = ""
    category: str = ""
    version: str = ""
    cpe: str = ""
