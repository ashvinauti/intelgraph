from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from intelgraph.core.graph.export import ExportSettings, GraphExporter
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node

router = APIRouter(prefix="/graph/export", tags=["graph"])

_MAX_EXPORT_SIZE_BYTES = 100 * 1024 * 1024
_CONTENT_TYPES = {
    "graphml": "application/xml",
    "dot": "text/vnd.graphviz",
    "json": "application/json",
}


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


def _format_streamer(
    graph: IntelligenceGraph,
    format: str,
    settings: ExportSettings,
):
    exporter = GraphExporter(graph, settings)
    yield from exporter.export_iter(format)


@router.get(
    "/{fmt}",
    summary="Export graph in specified format",
    description="Export the intelligence graph in GraphML, DOT, or JSON format. Supports node/edge filtering, subgraph extraction, community annotations, and centrality metrics. Streaming for large graphs.",
)
def export_graph(
    request: Request,
    fmt: str,
    pretty: bool = Query(False, description="Pretty-print output"),
    compressed: bool = Query(False, description="Gzip-compress the output"),
    include_community: bool = Query(
        False, description="Include community annotations if available"
    ),
    include_centrality: bool = Query(False, description="Include centrality metrics if available"),
    entity_type: list[str] = Query(default=[], description="Include only specific entity types"),
    exclude_entity_type: list[str] = Query(default=[], description="Exclude specific entity types"),
    relationship_type: list[str] = Query(
        default=[], description="Include only specific relationship types"
    ),
    exclude_relationship_type: list[str] = Query(
        default=[], description="Exclude specific relationship types"
    ),
    min_confidence: int = Query(0, ge=0, le=100, description="Minimum confidence score"),
    min_trust_weight: int = Query(0, ge=0, le=100, description="Minimum trust weight"),
    subgraph_node_id: str | None = Query(
        None, description="Export subgraph starting from this node"
    ),
    subgraph_depth: int = Query(1, ge=0, le=10, description="Subgraph traversal depth"),
):
    if fmt not in GraphExporter.SUPPORTED_FORMATS:
        alts = ", ".join(sorted(GraphExporter.SUPPORTED_FORMATS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {fmt}. Supported: {alts}.",
        )

    graph = _build_graph()
    if graph.node_count == 0:
        raise HTTPException(status_code=404, detail="Graph is empty, nothing to export.")

    community_map: dict[str, list[str]] | None = None
    centrality_map: dict[str, dict[str, float]] | None = None

    settings = ExportSettings(
        include_entity_types=set(entity_type) if entity_type else None,
        exclude_entity_types=set(exclude_entity_type) if exclude_entity_type else None,
        include_relationship_types=set(relationship_type) if relationship_type else None,
        exclude_relationship_types=(
            set(exclude_relationship_type) if exclude_relationship_type else None
        ),
        min_confidence=min_confidence,
        min_trust_weight=min_trust_weight,
        subgraph_node_id=subgraph_node_id,
        subgraph_depth=subgraph_depth,
        communities=community_map,
        centrality=centrality_map,
        include_metadata=True,
        pretty=pretty,
        compressed=compressed,
    )

    content_type = _CONTENT_TYPES.get(fmt, "application/octet-stream")
    if compressed:
        content_type = "application/gzip"

    exporter = GraphExporter(graph, settings)

    if compressed:
        raw = exporter.export(fmt)
        if isinstance(raw, bytes):
            return StreamingResponse(
                iter([raw]),
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="intelgraph.{fmt}.gz"',
                    "Content-Encoding": "gzip",
                },
            )
        return StreamingResponse(
            iter([raw]),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="intelgraph.{fmt}.gz"',
                "Content-Encoding": "gzip",
            },
        )

    def _stream():
        yield from exporter.export_iter(fmt)

    return StreamingResponse(
        _stream(),
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="intelgraph.{fmt}"',
            "X-Export-Node-Count": str(graph.node_count),
            "X-Export-Edge-Count": str(graph.edge_count),
        },
    )
