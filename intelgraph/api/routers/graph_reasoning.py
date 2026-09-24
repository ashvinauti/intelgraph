from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.graph.reasoning import CausalReasoner

router = APIRouter(prefix="/graph/reasoning", tags=["graph"])


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
            from intelgraph.core.graph.edge import Edge

            g.adjacency.setdefault(src, set()).add(tgt)
            g.adjacency.setdefault(tgt, set()).add(src)
            g.forward_adjacency.setdefault(src, set()).add(tgt)
            g.reverse_adjacency.setdefault(tgt, set()).add(src)
            g.node_edges.setdefault(src, set()).add(rel.id)
            g.node_edges.setdefault(tgt, set()).add(rel.id)
            g.edge_node_map[rel.id] = (src, tgt)
            g.edges[rel.id] = Edge(relationship=rel)
    return g


def _get_reasoner() -> CausalReasoner:
    return CausalReasoner(_build_graph())


def _edge_weight_fn(edge: Any) -> float:
    return float(edge.relationship.confidence_score) / 100.0 if edge.relationship else 1.0


@router.post("/root-cause", summary="Root cause analysis from an anomaly node (backpropagation)")
def root_cause_analysis(body: dict[str, Any]):
    anomaly_node = body.get("anomaly_node", "")
    if not anomaly_node:
        raise HTTPException(status_code=400, detail="anomaly_node is required")
    max_depth = body.get("max_depth", 5)
    max_causes = body.get("max_causes", 10)
    if max_depth < 1 or max_depth > 10:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 10")
    if max_causes < 1 or max_causes > 100:
        raise HTTPException(status_code=400, detail="max_causes must be between 1 and 100")
    reasoner = CausalReasoner(_build_graph())
    result = reasoner.root_cause_analysis(anomaly_node, max_depth, max_causes)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("error", "analysis failed"))
    return result


@router.post("/causal-path", summary="Discover causal path between two nodes")
def causal_path_analysis(body: dict[str, Any]):
    source = body.get("source", "")
    target = body.get("target", "")
    if not source or not target:
        raise HTTPException(status_code=400, detail="source and target are required")
    max_depth = body.get("max_depth", 5)
    if max_depth < 1 or max_depth > 10:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 10")
    reasoner = CausalReasoner(_build_graph())
    result = reasoner.causal_path(source, target, max_depth)
    return result


@router.get("/explain/{node_id}", summary="Get causal explanation for a node")
def explain_causal(node_id: str, max_depth: int = 5):
    if max_depth < 1 or max_depth > 10:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 10")
    reasoner = CausalReasoner(_build_graph())
    result = reasoner.explain(node_id, max_depth)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("error", "node not found"))
    return result


@router.get("/chains/{node_id}", summary="Get causal chains (ancestor/descendant) for a node")
def get_causal_chains(node_id: str, max_depth: int = 5):
    if max_depth < 1 or max_depth > 10:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 10")
    reasoner = CausalReasoner(_build_graph())
    result = reasoner.chains(node_id, max_depth)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("error", "node not found"))
    return result


@router.get("/causal-graph", summary="Get the constructed causal graph (cause->effect DAG)")
def get_causal_graph():
    reasoner = CausalReasoner(_build_graph())
    result = reasoner.causal_graph_network()
    return result


@router.get("/top-causes/{node_id}", summary="Get top N ranked root causes for a node")
def get_top_causes(node_id: str, max_depth: int = 5, top_n: int = 10):
    if max_depth < 1 or max_depth > 10:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 10")
    if top_n < 1 or top_n > 100:
        raise HTTPException(status_code=400, detail="top_n must be between 1 and 100")
    reasoner = CausalReasoner(_build_graph())
    result = reasoner.top_causes(node_id, max_depth, top_n)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("error", "node not found"))
    return result
