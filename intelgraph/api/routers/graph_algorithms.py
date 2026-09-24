from __future__ import annotations

from fastapi import APIRouter, HTTPException

from intelgraph.core.graph.algorithms import GraphAlgorithms
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node

router = APIRouter(prefix="/graph/algorithms", tags=["graph"])


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


def _get_algorithms() -> GraphAlgorithms:
    return GraphAlgorithms(_build_graph())


@router.post(
    "/mst",
    summary="Minimum Spanning Tree",
    description="Compute the minimum spanning tree using Kruskal or Prim algorithm.",
)
def compute_mst(algorithm: str = "kruskal"):
    if algorithm not in ("kruskal", "prim"):
        raise HTTPException(
            status_code=400, detail=f"Unknown algorithm: {algorithm}. Use 'kruskal' or 'prim'."
        )
    algs = _get_algorithms()
    g = _build_graph()
    if g.node_count == 0:
        raise HTTPException(status_code=404, detail="Graph is empty.")
    if algorithm == "prim":
        return algs.mst_prim()
    return algs.mst_kruskal()


@router.post(
    "/scc",
    summary="Strongly Connected Components",
    description="Find strongly connected components using Tarjan's algorithm.",
)
def compute_scc():
    algs = _get_algorithms()
    g = _build_graph()
    if g.node_count == 0:
        raise HTTPException(status_code=404, detail="Graph is empty.")
    return algs.scc_tarjan()


@router.post(
    "/diameter",
    summary="Graph Diameter",
    description="Compute the graph diameter (longest shortest path) using double BFS.",
)
def compute_diameter():
    algs = _get_algorithms()
    g = _build_graph()
    if g.node_count == 0:
        raise HTTPException(status_code=404, detail="Graph is empty.")
    return algs.diameter()


@router.post(
    "/shortest-path",
    summary="Shortest Path (A*)",
    description="Compute shortest path between two nodes using A* search with configurable heuristic.",
)
def compute_shortest_path(
    source_id: str,
    target_id: str,
    heuristic_type: str = "zero",
):
    if heuristic_type not in ("zero",):
        raise HTTPException(
            status_code=400, detail=f"Unknown heuristic: {heuristic_type}. Use 'zero'."
        )
    algs = _get_algorithms()
    g = _build_graph()
    if source_id not in g.nodes:
        raise HTTPException(status_code=404, detail=f"Source node {source_id} not found.")
    if target_id not in g.nodes:
        raise HTTPException(status_code=404, detail=f"Target node {target_id} not found.")
    return algs.astar(source_id, target_id)


@router.post(
    "/analytics",
    summary="Graph Algorithm Analytics",
    description="Compute algorithm analytics including path statistics, component distribution, and connectivity metrics.",
)
def compute_analytics():
    algs = _get_algorithms()
    g = _build_graph()
    if g.node_count == 0:
        raise HTTPException(status_code=404, detail="Graph is empty.")
    return {
        "path_statistics": algs.path_length_statistics(),
        "component_distribution": algs.connected_component_distribution(),
        "connectivity_metrics": algs.connectivity_metrics(),
    }
