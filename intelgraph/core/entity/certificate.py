from dataclasses import dataclass, field
from datetime import datetime

from intelgraph.core.entity.base import BaseEntity, EntityType


@dataclass(frozen=True)
class Certificate(BaseEntity):
    entity_type: EntityType = field(default=EntityType.CERTIFICATE, init=False)
    serial: str = ""
    issuer: str = ""
    subject: str = ""
    fingerprint: str = ""
    validity_start: datetime | None = None
    validity_end: datetime | None = None
