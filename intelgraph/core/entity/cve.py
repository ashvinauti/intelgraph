from dataclasses import dataclass, field

from intelgraph.core.entity.base import BaseEntity, EntityType


@dataclass(frozen=True)
class CveEntity(BaseEntity):
    entity_type: EntityType = field(default=EntityType.CVE, init=False)
    cve_id: str = ""
    vendor_project: str = ""
    product: str = ""
    vulnerability_name: str = ""
    date_added: str = ""
    due_date: str = ""
    known_ransomware_use: bool = False
    short_description: str = ""
