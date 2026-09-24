"""GraphQL API for IntelGraph.

Exposes read/write access to the knowledge graph (entities, relationships,
search) alongside the existing REST API. Mounted at ``/graphql`` by
:mod:`intelgraph.api.main`. Reuses the same :class:`ServiceContainer` and
storage backend as the REST routers, so data created through either API is
visible through the other.
"""

from __future__ import annotations

from typing import Any, cast

import strawberry
from fastapi import Request
from strawberry.fastapi import GraphQLRouter
from strawberry.scalars import JSON

from intelgraph.core.relationship import Relationship as CoreRelationship
from intelgraph.core.relationship import RelationshipType as CoreRelationshipType
from intelgraph.core.storage.audit import AuditEntry
from intelgraph.core.storage.serializers import _entity_to_dict

_COMMON_ENTITY_FIELDS = {
    "id",
    "version",
    "entity_type",
    "created_at",
    "updated_at",
    "aliases",
    "confidence_score",
    "trust_score",
}

_ENTITY_CLASSES: dict[str, type] = {}


def _get_entity_class(entity_type: str) -> type | None:
    if not _ENTITY_CLASSES:
        from intelgraph.core.entity import (
            Certificate,
            Company,
            CveEntity,
            Domain,
            Email,
            IPAddress,
            Person,
            Technology,
            Username,
        )

        for cls in (
            Person,
            Company,
            Domain,
            Email,
            Username,
            IPAddress,
            Technology,
            Certificate,
            CveEntity,
        ):
            _ENTITY_CLASSES[cls.__name__.lower()] = cls
            _ENTITY_CLASSES[cls.__name__] = cls
    return _ENTITY_CLASSES.get(entity_type.lower()) or _ENTITY_CLASSES.get(entity_type)


@strawberry.type(description="A knowledge graph entity (person, domain, IP, CVE, etc.).")
class EntityNode:
    id: str
    entity_type: str
    version: int
    confidence_score: int
    trust_score: int
    aliases: list[str]
    created_at: str
    updated_at: str
    attributes: JSON = strawberry.field(
        description="Type-specific attributes (e.g. `ip`, `domain_name`, `cve_id`)."
    )


@strawberry.type(description="A directed, typed relationship between two entities.")
class RelationshipEdge:
    id: str
    type: str
    source_id: str
    target_id: str
    confidence_score: int
    trust_weight: int
    occurrence_count: int
    created_at: str


@strawberry.type(description="A ranked full-text search hit.")
class SearchHit:
    node_id: str
    entity_type: str
    entity_identifier: str
    confidence: float
    relevance: float


@strawberry.input(description="Attributes for creating a new entity.")
class EntityCreateInput:
    entity_type: str
    attributes: JSON


@strawberry.input(description="Attributes for creating a new relationship.")
class RelationshipCreateInput:
    type: str
    source_id: str
    target_id: str
    confidence_score: int = 50
    trust_weight: int = 50


def _entity_to_node(entity: Any) -> EntityNode:
    data = _entity_to_dict(entity)
    attributes = {k: v for k, v in data.items() if k not in _COMMON_ENTITY_FIELDS}
    return EntityNode(
        id=data["id"],
        entity_type=data["entity_type"],
        version=data["version"],
        confidence_score=data["confidence_score"],
        trust_score=data["trust_score"],
        aliases=list(data.get("aliases", [])),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        attributes=cast(JSON, attributes),
    )


def _relationship_to_edge(rel: CoreRelationship) -> RelationshipEdge:
    return RelationshipEdge(
        id=rel.id,
        type=rel.type.name,
        source_id=rel.source_id,
        target_id=rel.target_id,
        confidence_score=rel.confidence_score,
        trust_weight=rel.trust_weight,
        occurrence_count=rel.occurrence_count,
        created_at=rel.created_at.isoformat(),
    )


def _actor(info: strawberry.types.Info) -> str:
    request = info.context.get("request")
    uid = getattr(getattr(request, "state", None), "user_id", "") if request else ""
    return uid or "anonymous"


@strawberry.type
class Query:
    @strawberry.field(description="Fetch a single entity by ID.")
    def entity(self, info: strawberry.types.Info, id: str) -> EntityNode | None:
        backend = info.context["container"].backend
        record = backend.get_entity(id)
        return _entity_to_node(record) if record is not None else None

    @strawberry.field(description="List entities, optionally filtered by entity type.")
    def entities(
        self, info: strawberry.types.Info, entity_type: str | None = None
    ) -> list[EntityNode]:
        backend = info.context["container"].backend
        records = backend.list_entities(entity_type)
        return [_entity_to_node(r) for r in records]

    @strawberry.field(description="Fetch a single relationship by ID.")
    def relationship(self, info: strawberry.types.Info, id: str) -> RelationshipEdge | None:
        backend = info.context["container"].backend
        record = backend.get_relationship(id)
        return _relationship_to_edge(record) if record is not None else None

    @strawberry.field(
        description="List relationships, optionally filtered by source and/or target entity ID."
    )
    def relationships(
        self,
        info: strawberry.types.Info,
        source_id: str | None = None,
        target_id: str | None = None,
    ) -> list[RelationshipEdge]:
        backend = info.context["container"].backend
        records = backend.list_relationships(source_id, target_id)
        return [_relationship_to_edge(r) for r in records]

    @strawberry.field(
        description="Substring search across entity identifiers and attributes."
    )
    def search(self, info: strawberry.types.Info, query: str, limit: int = 20) -> list[SearchHit]:
        ql = query.strip().lower()
        if len(ql) < 2:
            return []
        backend = info.context["container"].backend
        hits: list[SearchHit] = []
        for entity in backend.list_entities():
            data = _entity_to_dict(entity)
            identifier = (
                data.get("name")
                or data.get("ip")
                or data.get("domain_name")
                or data.get("cve_id")
                or data["id"]
            )
            haystack = " ".join(
                str(v).lower() for v in data.values() if isinstance(v, (str, int, float))
            )
            if ql not in haystack:
                continue
            confidence = float(data.get("confidence_score", 0) or 0)
            identifier_l = str(identifier).lower()
            relevance = (
                100.0 + confidence
                if ql == identifier_l
                else 75.0 + confidence
                if ql in identifier_l
                else confidence
            )
            hits.append(
                SearchHit(
                    node_id=data["id"],
                    entity_type=data["entity_type"],
                    entity_identifier=str(identifier),
                    confidence=confidence,
                    relevance=relevance,
                )
            )
        hits.sort(key=lambda h: -h.relevance)
        return hits[:limit]


@strawberry.type
class Mutation:
    @strawberry.mutation(description="Create a new entity.")
    def create_entity(
        self, info: strawberry.types.Info, input: EntityCreateInput
    ) -> EntityNode:
        cls = _get_entity_class(input.entity_type)
        if cls is None:
            raise ValueError(f"Unknown entity type: {input.entity_type}")
        container = info.context["container"]
        attributes = cast("dict[str, Any]", input.attributes)
        entity = cls(**attributes)
        container.backend.put_entity(entity)
        container.audit.log(
            AuditEntry(
                entity_id=entity.id,
                entity_type=input.entity_type,
                operation="CREATE",
                new_data=attributes,
                actor=_actor(info),
            )
        )
        return _entity_to_node(entity)

    @strawberry.mutation(description="Create a new relationship between two entities.")
    def create_relationship(
        self, info: strawberry.types.Info, input: RelationshipCreateInput
    ) -> RelationshipEdge:
        try:
            rtype = CoreRelationshipType[input.type.upper().replace(" ", "_")]
        except KeyError:
            raise ValueError(f"Unknown relationship type: {input.type}") from None
        container = info.context["container"]
        rel = CoreRelationship(
            type=rtype,
            source_id=input.source_id,
            target_id=input.target_id,
            confidence_score=input.confidence_score,
            trust_weight=input.trust_weight,
        )
        container.backend.put_relationship(rel)
        container.audit.log(
            AuditEntry(
                entity_id=rel.id,
                entity_type="relationship",
                operation="CREATE",
                new_data={
                    "type": input.type,
                    "source_id": input.source_id,
                    "target_id": input.target_id,
                },
                actor=_actor(info),
            )
        )
        return _relationship_to_edge(rel)


schema = strawberry.Schema(query=Query, mutation=Mutation)


async def _get_context(request: Request) -> dict[str, Any]:
    from intelgraph.api.main import _container

    return {"request": request, "container": _container}


graphql_router = GraphQLRouter(
    schema,
    context_getter=_get_context,
    graphql_ide="graphiql",
)
