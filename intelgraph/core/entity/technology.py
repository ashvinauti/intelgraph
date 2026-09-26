from dataclasses import dataclass, field

from intelgraph.core.entity.base import BaseEntity, EntityType


@dataclass(frozen=True)
class Technology(BaseEntity):
    entity_type: EntityType = field(default=EntityType.TECHNOLOGY, init=False)
    name: str = ""
    category: str = ""
    # Software/product version. Named product_version so it does not shadow
    # BaseEntity.version, the integer record revision.
    product_version: str = ""
    cpe: str = ""
