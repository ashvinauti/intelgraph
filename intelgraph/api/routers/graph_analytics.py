from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from intelgraph.core.graph.analytics import GraphAnalytics
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node

router = APIRouter(prefix="/graph", tags=["graph"])

_VALID_ALGORITHMS = frozenset({"degree", "pagerank", "betweenness", "closeness"})


def _build_graph() -> IntelligenceGraph:
    from intelgraph.api.main import _container

    g = IntelligenceGraph()
    for entity in _container.backend.list_entities():
        eid = entity.id
        g.nodes[eid] = Node(entity=entity)
        g.adjacency.setdefault(eid, set())
        g.forward_adjacency.setdefault(eid, set())
        g.reverse_adjacency.setdefault(eid, set())
    for rel in _container.backend.list_relationships():
        src = rel.source_id
        tgt = rel.target_id
        if src in g.nodes and tgt in g.nodes:
            g.adjacency.setdefault(src, set()).add(tgt)
            g.adjacency.setdefault(tgt, set()).add(src)
            g.forward_adjacency.setdefault(src, set()).add(tgt)
            g.reverse_adjacency.setdefault(tgt, set()).add(src)
    return g


def _get_analytics() -> GraphAnalytics:
    return GraphAnalytics(_build_graph())


@router.get("/centrality/{node_id}")
def get_centrality(
    node_id: str,
    algorithm: str = "degree",
    analytics: GraphAnalytics = Depends(_get_analytics),
):
    if algorithm not in _VALID_ALGORITHMS:
        algs = ", ".join(sorted(_VALID_ALGORITHMS))
        raise HTTPException(
            status_code=400, detail=f"Unknown algorithm: {algorithm}. Use one of: {algs}."
        )
    try:
        if algorithm == "pagerank":
            result = analytics.page_rank(node_id)
        elif algorithm == "betweenness":
            result = analytics.betweenness_centrality(node_id)
        elif algorithm == "closeness":
            result = analytics.closeness_centrality(node_id)
        else:
            result = analytics.degree_centrality(node_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    return {
        "node_id": node_id,
        "algorithm": algorithm,
        "centrality": round(result, 6),
    }


@router.get("/stats")
def get_stats(
    detail: bool = False,
    analytics: GraphAnalytics = Depends(_get_analytics),
):
    return analytics.stats(detail=detail)
