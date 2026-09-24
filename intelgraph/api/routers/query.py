from __future__ import annotations

from fastapi import APIRouter, Depends

from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.graph.query import GraphQueryEngine

router = APIRouter(prefix="/query", tags=["query"])


def _build_graph() -> IntelligenceGraph:
    from intelgraph.api.main import _container

    g = IntelligenceGraph()
    for entity in _container.backend.list_entities():
        eid = entity.id
        g.nodes[eid] = Node(entity=entity)
        g.adjacency.setdefault(eid, set())
    for rel in _container.backend.list_relationships():
        src = rel.source_id
        tgt = rel.target_id
        if src in g.nodes and tgt in g.nodes:
            g.adjacency.setdefault(src, set()).add(tgt)
            g.adjacency.setdefault(tgt, set()).add(src)
    return g


def _get_query_engine() -> GraphQueryEngine:
    from intelgraph.api.main import _container

    g = _build_graph()
    return GraphQueryEngine(
        g,
        verification_lookup=lambda eid: (
            _container.verification.get_verification(eid).to_dict()
            if _container.verification.get_verification(eid)
            else None
        ),
        chain_lookup=lambda eid: (
            _container.chain.get_chain_by_entity(eid).to_dict()
            if _container.chain.get_chain_by_entity(eid)
            else None
        ),
    )


@router.get(
    "",
    summary="Query entities",
    description="Filter entities by type, verification state, confidence range, source trust, with pagination.",
)
def query(
    entity_type: str | None = None,
    verification_state: str | None = None,
    confidence_min: float | None = None,
    confidence_max: float | None = None,
    source_trust_min: float | None = None,
    limit: int = 0,
    offset: int = 0,
    qe: GraphQueryEngine = Depends(_get_query_engine),
):
    nodes = qe.filter_nodes(
        entity_type=entity_type,
        verification_state=verification_state,
        confidence_min=confidence_min,
        confidence_max=confidence_max,
        source_trust_min=source_trust_min,
        limit=limit,
        offset=offset,
    )
    return [{"id": n.id, "entity_type": n.entity_type} for n in nodes]
