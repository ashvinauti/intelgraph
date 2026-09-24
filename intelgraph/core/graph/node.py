from dataclasses import dataclass

from intelgraph.core.entity.base import BaseEntity


@dataclass(frozen=True)
class Node:
    entity: BaseEntity

    @property
    def id(self) -> str:
        return self.entity.id

    @property
    def entity_type(self) -> str:
        return self.entity.entity_type.type_name
