from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from intelgraph.core.graph.anomaly import AnomalyDetector
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node

router = APIRouter(prefix="/graph/anomaly", tags=["graph"])


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


def _get_detector(config: dict[str, Any] | None = None) -> AnomalyDetector:
    return AnomalyDetector(_build_graph(), config=config)


def _edge_weight_fn(edge: Any) -> float:
    return float(edge.relationship.confidence_score) / 100.0 if edge.relationship else 1.0


@router.post("/detect", summary="Run full anomaly detection across the graph")
def detect_anomalies():
    detector = AnomalyDetector(_build_graph())
    result = detector.detect()
    return result


@router.get("/nodes/{node_id}", summary="Get anomaly details for a specific node")
def get_node_anomaly(node_id: str):
    detector = AnomalyDetector(_build_graph())
    result = detector.detect_for_node(node_id)
    if not result["found"]:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    return result


@router.get("/timeline", summary="Get anomaly timeline for all nodes")
def get_anomaly_timeline():
    detector = AnomalyDetector(_build_graph())
    result = detector.timeline()
    return result


@router.get("/top-n/{n}", summary="Get top N anomalous nodes")
def get_top_anomalies(n: int = 10):
    if n < 1 or n > 1000:
        raise HTTPException(status_code=400, detail="n must be between 1 and 1000")
    detector = AnomalyDetector(_build_graph())
    result = detector.top_anomalies(n)
    return result


@router.get("/explain/{node_id}", summary="Get standardized anomaly explanation for a node")
def explain_anomaly(node_id: str):
    detector = AnomalyDetector(_build_graph())
    result = detector.explain(node_id)
    if not result["found"]:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    return result


@router.get(
    "/explain/detail/{node_id}",
    summary="Get detailed anomaly explanation with full signal breakdown",
)
def explain_anomaly_detail(node_id: str):
    detector = AnomalyDetector(_build_graph())
    result = detector.explain_detail(node_id)
    if not result["found"]:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    return result
