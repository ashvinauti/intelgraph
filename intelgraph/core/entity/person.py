from dataclasses import dataclass, field

from intelgraph.core.entity.base import BaseEntity, EntityType


@dataclass(frozen=True)
class Person(BaseEntity):
    entity_type: EntityType = field(default=EntityType.PERSON, init=False)
    name: str = ""
    email_addresses: tuple[str, ...] = field(default_factory=tuple)
    usernames: tuple[str, ...] = field(default_factory=tuple)
    social_profiles: tuple[str, ...] = field(default_factory=tuple)
    company_affiliations: tuple[str, ...] = field(default_factory=tuple)
    domains: tuple[str, ...] = field(default_factory=tuple)
    phone_numbers: tuple[str, ...] = field(default_factory=tuple)
    title: str = ""
