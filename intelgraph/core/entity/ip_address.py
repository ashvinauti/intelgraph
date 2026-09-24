from dataclasses import dataclass, field

from intelgraph.core.entity.base import BaseEntity, EntityType


@dataclass(frozen=True)
class IPAddress(BaseEntity):
    entity_type: EntityType = field(default=EntityType.IP_ADDRESS, init=False)
    ip: str = ""
    rdns: str = ""
    asn: str = ""
    organization: str = ""
    open_ports: tuple[int, ...] = field(default_factory=tuple)
