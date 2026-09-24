from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.influence import InfluencePropagation
from intelgraph.core.graph.node import Node

router = APIRouter(prefix="/graph", tags=["graph"])


def _build_graph() -> IntelligenceGraph:
    from intelgraph.api.main import _container

    g = IntelligenceGraph()
    for entity in _container.backend.list_entities():
        eid = entity.id
        g.nodes[eid] = Node(entity=entity)
        g.adjacency.setdefault(eid, set())
        g.forward_adjacency.setdefault(eid, set())
        g.reverse_adjacency.setdefault(eid, set())
        g.node_edges.setdefault(eid, set())
    for rel in _container.backend.list_relationships():
        src = rel.source_id
        tgt = rel.target_id
        if src in g.nodes and tgt in g.nodes:
            g.adjacency.setdefault(src, set()).add(tgt)
            g.adjacency.setdefault(tgt, set()).add(src)
            g.forward_adjacency.setdefault(src, set()).add(tgt)
            g.reverse_adjacency.setdefault(tgt, set()).add(src)
            g.node_edges.setdefault(src, set()).add(rel.id)
            g.node_edges.setdefault(tgt, set()).add(rel.id)
            g.edge_node_map[rel.id] = (src, tgt)
            from intelgraph.core.graph.edge import Edge

            g.edges[rel.id] = Edge(relationship=rel)
    return g


def _get_influence() -> InfluencePropagation:
    return InfluencePropagation(_build_graph())


def _edge_weight_fn(edge: Any) -> float:
    return float(edge.relationship.confidence_score) / 100.0 if edge.relationship else 1.0


@router.post("/algorithms/pagerank", summary="Compute standard PageRank")
def compute_pagerank(
    damping: float = 0.85,
    max_iterations: int = 100,
    tolerance: float = 1e-8,
):
    infl = InfluencePropagation(_build_graph())
    result = infl.page_rank(damping, max_iterations, tolerance)
    return result


@router.post(
    "/algorithms/weighted-pagerank",
    summary="Compute weighted PageRank using edge confidence/trust weights",
)
def compute_weighted_pagerank(
    damping: float = 0.85,
    max_iterations: int = 100,
    tolerance: float = 1e-8,
):
    infl = InfluencePropagation(_build_graph(), weight_fn=_edge_weight_fn)
    result = infl.weighted_page_rank(damping, max_iterations, tolerance)
    return result


@router.post(
    "/algorithms/influence-propagation",
    summary="Run threshold-based influence propagation from seed nodes",
)
def compute_influence_propagation(
    body: dict[str, Any],
):
    seed_nodes = body.get("seed_nodes", {})
    if not seed_nodes:
        raise HTTPException(
            status_code=400, detail="seed_nodes is required (dict of node_id -> initial influence)"
        )
    threshold = body.get("threshold", 0.5)
    if not (0.0 < threshold <= 1.0):
        raise HTTPException(status_code=400, detail="threshold must be in (0, 1]")
    decay_factor = body.get("decay_factor", 0.5)
    if not (0.0 < decay_factor <= 1.0):
        raise HTTPException(status_code=400, detail="decay_factor must be in (0, 1]")
    max_depth = body.get("max_depth", 10)
    if max_depth < 1 or max_depth > 100:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 100")
    infl = InfluencePropagation(_build_graph())
    result = infl.influence_propagation(seed_nodes, threshold, decay_factor, max_depth)
    return result


@router.post(
    "/algorithms/influence-scores", summary="Compute composite influence scores for all nodes"
)
def compute_influence_scores(
    damping: float = 0.85,
    max_iterations: int = 100,
    tolerance: float = 1e-8,
):
    infl = InfluencePropagation(_build_graph())
    result = infl.influence_scores(damping, max_iterations, tolerance)
    return result


@router.get("/influence/top-n/{n}", summary="Get top N influence nodes")
def get_top_influence(
    n: int = 10,
    damping: float = 0.85,
):
    if n < 1 or n > 1000:
        raise HTTPException(status_code=400, detail="n must be between 1 and 1000")
    infl = InfluencePropagation(_build_graph())
    result = infl.top_influence_nodes(n, damping)
    return result


@router.get("/influence/chain/{node_id}", summary="Trace influence chain from a node")
def get_influence_chain(
    node_id: str,
    max_depth: int = 10,
    min_influence: float = 0.01,
):
    if max_depth < 1 or max_depth > 100:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 100")
    if not (0.0 <= min_influence <= 1.0):
        raise HTTPException(status_code=400, detail="min_influence must be in [0, 1]")
    infl = InfluencePropagation(_build_graph())
    result = infl.influence_chain(node_id, max_depth, min_influence)
    if not result["found"]:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    return result
