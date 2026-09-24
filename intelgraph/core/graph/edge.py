from dataclasses import dataclass

from intelgraph.core.relationship import Relationship


@dataclass(frozen=True)
class Edge:
    relationship: Relationship

    @property
    def id(self) -> str:
        return self.relationship.id

    @property
    def source_id(self) -> str:
        return self.relationship.source_id

    @property
    def target_id(self) -> str:
        return self.relationship.target_id
