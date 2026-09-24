from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from intelgraph.core.graph.attack_path import AttackPathAnalyzer, AttackPathCache
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node

router = APIRouter(prefix="/graph/attack-path", tags=["graph"])

_cache = AttackPathCache()


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


def _get_analyzer() -> AttackPathAnalyzer:
    return AttackPathAnalyzer(_build_graph(), cache=_cache)


def _edge_weight_fn(edge: Any) -> float:
    return float(edge.relationship.confidence_score) / 100.0 if edge.relationship else 1.0


@router.post("/find", summary="Find shortest attack path between two nodes (confidence-weighted)")
def find_attack_path(body: dict[str, Any]):
    source = body.get("source", "")
    target = body.get("target", "")
    if not source or not target:
        raise HTTPException(status_code=400, detail="source and target are required")
    analyzer = AttackPathAnalyzer(_build_graph(), cache=_cache)
    result = analyzer.find_shortest_path(source, target)
    return result


@router.post("/all", summary="Enumerate all attack paths from a source (bounded depth)")
def find_all_attack_paths(body: dict[str, Any]):
    source = body.get("source", "")
    if not source:
        raise HTTPException(status_code=400, detail="source is required")
    target = body.get("target", None)
    max_depth = body.get("max_depth", 5)
    max_paths = body.get("max_paths", 100)
    if max_depth < 1 or max_depth > 10:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 10")
    if max_paths < 1 or max_paths > 1000:
        raise HTTPException(status_code=400, detail="max_paths must be between 1 and 1000")
    analyzer = AttackPathAnalyzer(_build_graph(), cache=_cache)
    result = analyzer.find_all_paths(source, target, max_depth, max_paths)
    return result


@router.get("/critical-nodes", summary="Identify critical bottleneck nodes across attack paths")
def get_critical_nodes(max_depth: int = 5):
    if max_depth < 1 or max_depth > 10:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 10")
    analyzer = AttackPathAnalyzer(_build_graph(), cache=_cache)
    result = analyzer.critical_nodes(max_depth)
    return result


@router.get("/surface/{entity_id}", summary="Map attack surface for an entity")
def get_attack_surface(entity_id: str, max_depth: int = 4):
    if max_depth < 1 or max_depth > 10:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 10")
    analyzer = AttackPathAnalyzer(_build_graph(), cache=_cache)
    result = analyzer.attack_surface(entity_id, max_depth)
    if not result["found"]:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return result


@router.post("/explain/{path_id}", summary="Get edge-level explanation of an attack path")
def explain_attack_path(path_id: str, body: dict[str, Any] = None):
    if body is None:
        body = {}
    analyzer = AttackPathAnalyzer(_build_graph(), cache=_cache)
    result = analyzer.explain_path(path_id, body)
    if not result["found"]:
        raise HTTPException(
            status_code=404, detail=f"Path {path_id} not found or not in provided paths"
        )
    return result


@router.get("/{path_id}", summary="Get attack path by ID")
def get_attack_path(path_id: str):
    analyzer = AttackPathAnalyzer(_build_graph(), cache=_cache)
    result = analyzer.get_path_by_id(path_id, [])
    if not result["found"]:
        raise HTTPException(status_code=404, detail=f"Path {path_id} not found")
    return result
