from enum import Enum, auto


class RelationshipType(Enum):
    WORKS_FOR = auto()
    OWNS = auto()
    USES = auto()
    CONNECTED_TO = auto()
    MENTIONS = auto()
    REGISTERED_TO = auto()
    ASSOCIATED_WITH = auto()
    AUTHORED = auto()
    RELATED_TO = auto()
    HOSTED_ON = auto()
    RESOLVES_TO = auto()
    SUBDOMAIN_OF = auto()

    @property
    def type_name(self) -> str:
        return self.name.lower()
