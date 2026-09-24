"""IOC enrichment router.

Stable, SOC-friendly REST endpoints for indicator enrichment and threat
lookup. Designed to be wired into SIEM/SOAR platforms: given an indicator
(IP, domain, URL, hash, CVE), return the entities, related infrastructure,
confidence scores, evidence summary, and threat score in a single response.

Authentication:
- JWT bearer (`Authorization: Bearer <jwt>`) works as elsewhere.
- API key (`X-API-Key: <key>`) works as a direct alternative so external
  SOARs can skip the token exchange step.

Rate limited under the "read" category by default; override via the
`enrichment` rate_limit category if you need different limits.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


def _build_graph() -> Any:
    from intelgraph.api.main import _container
    from intelgraph.core.graph.edge import Edge
    from intelgraph.core.graph.graph import IntelligenceGraph
    from intelgraph.core.graph.node import Node

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
            g.edges[rel.id] = Edge(relationship=rel)
    return g


_IOC_TYPE_FIELDS: dict[str, tuple[str, ...]] = {
    "ip_address": ("ip",),
    "domain": ("domain_name",),
    "cve": ("cve_id",),
    "url": ("url",),
    "hash": ("hash_value", "md5", "sha1", "sha256"),
}


def _entity_identifier(entity: Any) -> str:
    """Return the human-readable indicator value for an entity."""
    for attr in ("ip", "domain_name", "cve_id", "url", "hash_value", "md5", "sha1", "sha256"):
        val = getattr(entity, attr, None)
        if val:
            return str(val)
    return str(getattr(entity, "id", ""))


def _match_entity_value(entity: Any, ioc_type: str, ioc_value: str) -> bool:
    fields = _IOC_TYPE_FIELDS.get(ioc_type, ())
    if not fields:
        return False
    needle = ioc_value.lower().strip()
    for field in fields:
        val = getattr(entity, field, None)
        if val and str(val).lower().strip() == needle:
            return True
    return False


def _entity_to_summary(node_id: str, node: Any) -> dict[str, Any]:
    entity = node.entity
    evidence = getattr(entity, "evidence", ())
    return {
        "entity_id": node_id,
        "entity_type": entity.entity_type.type_name,
        "identifier": _entity_identifier(entity),
        "confidence_score": getattr(entity, "confidence_score", 0),
        "trust_score": getattr(entity, "trust_score", 0),
        "first_seen": getattr(entity, "first_seen", None).isoformat() if getattr(entity, "first_seen", None) else None,
        "last_seen": getattr(entity, "last_seen", None).isoformat() if getattr(entity, "last_seen", None) else None,
        "source": getattr(evidence[0].source, "name", "") if evidence and hasattr(evidence[0], "source") else "",
        "evidence_count": len(evidence),
        "attributes": {
            attr: getattr(entity, attr)
            for attr in ("ip", "domain_name", "cve_id", "url", "hash_value", "vendor_project", "product", "vulnerability_name")
            if getattr(entity, attr, None)
        },
    }


def _neighbors_summary(graph: Any, node_id: str, max_neighbors: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for nbr in graph.neighbors(node_id):
        nbr_id = ""
        for attr in ("node_id", "entity_id", "id"):
            val = getattr(nbr, attr, None)
            if val is not None:
                nbr_id = str(val)
                break
        edges_payload: list[dict[str, Any]] = []
        for edge_id in graph.node_edges.get(node_id, set()):
            edge = graph.edges.get(edge_id)
            if edge is None:
                continue
            src_tgt = graph.edge_node_map.get(edge_id)
            if src_tgt is None:
                continue
            other = src_tgt[1] if src_tgt[0] == node_id else src_tgt[0]
            if other != nbr_id:
                continue
            rel = edge.relationship
            edges_payload.append({
                "edge_id": edge_id,
                "relationship_type": rel.type.name.lower() if hasattr(rel, "type") else str(rel),
                "direction": "outgoing" if src_tgt[0] == node_id else "incoming",
                "confidence": getattr(rel, "confidence_score", 0),
            })
        out.append({
            "entity_id": nbr_id,
            "entity_type": nbr.entity.entity_type.type_name,
            "identifier": _entity_identifier(nbr.entity),
            "confidence_score": getattr(nbr.entity, "confidence_score", 0),
            "relationships": edges_payload,
        })
        if len(out) >= max_neighbors:
            break
    return out


@router.get(
    "/{ioc_type}/{ioc_value}",
    summary="Enrich an IOC",
    description=(
        "Look up an indicator of compromise (IP address, domain, URL, hash, or CVE) "
        "in the IntelGraph knowledge graph and return entity attributes, related "
        "infrastructure, confidence/trust scores, and evidence summary. "
        "Designed for SIEM/SOAR integrations — pass the result back into alert "
        "context to give analysts IOC provenance at a glance."
    ),
)
def enrich_ioc(
    ioc_type: str,
    ioc_value: str,
    request: Request,
    max_neighbors: int = Query(
        25, ge=0, le=200, description="Maximum number of related entities to return"
    ),
) -> dict[str, Any]:
    ioc_type = ioc_type.lower().strip()
    if ioc_type not in _IOC_TYPE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported ioc_type '{ioc_type}'. Supported: {sorted(_IOC_TYPE_FIELDS)}",
        )

    graph = _build_graph()
    matched_node_id: str | None = None
    matched_node = None
    for node_id, node in graph.nodes.items():
        if _match_entity_value(node.entity, ioc_type, ioc_value):
            matched_node_id = node_id
            matched_node = node
            break

    if matched_node is None or matched_node_id is None:
        return {
            "ioc_type": ioc_type,
            "ioc_value": ioc_value,
            "found": False,
            "message": "Indicator not found in the knowledge graph.",
        }

    summary = _entity_to_summary(matched_node_id, matched_node)
    neighbors = _neighbors_summary(graph, matched_node_id, max_neighbors)

    # Lazy threat score via the scoring module when available.
    threat_score: float | None = None
    try:
        from intelgraph.core.scoring.threat_score import ThreatScorer

        scorer = ThreatScorer(graph)
        threat_score = scorer.score(matched_node, graph)
    except Exception:
        threat_score = None

    return {
        "ioc_type": ioc_type,
        "ioc_value": ioc_value,
        "found": True,
        "entity": summary,
        "related_entities": neighbors,
        "related_count": len(neighbors),
        "threat_score": threat_score,
    }