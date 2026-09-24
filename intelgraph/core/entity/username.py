from dataclasses import dataclass, field

from intelgraph.core.entity.base import BaseEntity, EntityType


@dataclass(frozen=True)
class Username(BaseEntity):
    entity_type: EntityType = field(default=EntityType.USERNAME, init=False)
    username: str = ""
    platform: str = ""
    profile_url: str = ""
