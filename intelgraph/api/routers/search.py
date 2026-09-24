from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from intelgraph.api.routers.dashboard import dashboard_state
from intelgraph.api.routers.query import _get_query_engine
from intelgraph.core.graph.query import GraphQueryEngine

router = APIRouter(prefix="/search", tags=["search"])


def _search_in_memory(
    qe: GraphQueryEngine,
    query: str,
    type_filter: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Fallback in-memory search when FTS5 is unavailable."""
    ql = query.lower()
    results: list[dict[str, Any]] = []
    for node in qe._graph.nodes.values():
        entity = node.entity
        etype = entity.entity_type.name.lower()
        if type_filter != "all" and etype != type_filter:
            continue
        identifier = (
            getattr(entity, "ip", None)
            or getattr(entity, "domain_name", None)
            or getattr(entity, "cve_id", None)
            or node.id
        )
        # Build searchable text
        search_text = identifier.lower() + " " + etype + " "
        data = {
            "ip": getattr(entity, "ip", ""),
            "domain_name": getattr(entity, "domain_name", ""),
            "cve_id": getattr(entity, "cve_id", ""),
            "vendor_project": getattr(entity, "vendor_project", ""),
            "product": getattr(entity, "product", ""),
            "vulnerability_name": getattr(entity, "vulnerability_name", ""),
        }
        for _field, val in data.items():
            if isinstance(val, str):
                search_text += val.lower() + " "
        # Evidence content
        ev = getattr(entity, "evidence", ())
        for e in ev:
            if e.content:
                search_text += e.content.lower() + " "
        if ql not in search_text:
            continue
        # Calculate simple relevance score
        score = 0.0
        conf = getattr(entity, "confidence_score", 0) or 0
        if ql == identifier.lower():
            score = 100.0 + conf  # exact identifier match
        elif ql in identifier.lower():
            score = 75.0 + conf  # partial identifier match
        elif ql in etype:
            score = 50.0 + conf
        else:
            score = conf  # weak match elsewhere
        results.append(
            {
                "node_id": node.id,
                "entity_type": etype,
                "entity_identifier": identifier,
                "confidence": conf,
                "relevance": score,
            }
        )
    results.sort(key=lambda r: -r["relevance"])
    return results[:limit]


def _search_dashboard_state(
    query: str,
    type_filter: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Search dashboard state graph nodes (real pipeline data)."""
    r = dashboard_state.result
    if not r:
        return []
    nodes = r.get("graph_nodes_summary", [])
    if not nodes:
        return []
    ql = query.lower()
    results: list[dict[str, Any]] = []
    for n in nodes:
        etype = n.get("entity_type", "").lower()
        if type_filter != "all":
            if type_filter == "ip_address" and etype != "ipaddress":
                continue
            if type_filter == "domain" and etype != "domain":
                continue
            if type_filter == "cve" and etype != "cveentity":
                continue
            if type_filter not in ("ip_address", "domain", "cve") and etype != type_filter:
                continue
        identifier = n.get("entity_identifier", "") or ""
        search_text = identifier.lower() + " " + etype + " "
        if ql not in search_text:
            continue
        conf = n.get("confidence", 0) or 0
        if ql == identifier.lower():
            score = 100.0 + conf
        elif ql in identifier.lower():
            score = 75.0 + conf
        elif ql in etype:
            score = 50.0 + conf
        else:
            score = conf
        results.append(
            {
                "node_id": n.get("node_id", identifier),
                "entity_type": etype,
                "entity_identifier": identifier,
                "confidence": conf,
                "relevance": score,
            }
        )
    results.sort(key=lambda r: -r["relevance"])
    return results[:limit]


@router.get(
    "",
    summary="Full-text search across entities",
    description=(
        "Search entities by keyword using FTS5. Returns matching entity IDs, "
        "types, and identifiers ranked by relevance."
    ),
)
def search(
    q: str = Query("", description="Search term (case-insensitive, partial match)"),
    type: str = Query("all", description="Entity type filter: entity|alert|incident|all"),
    limit: int = Query(20, description="Max results", ge=1, le=100),
    offset: int = Query(0, description="Offset for pagination", ge=0),
    qe: GraphQueryEngine = Depends(_get_query_engine),
):
    query = q.strip()
    if not query or len(query) < 2:
        return []

    type_filter = type.lower()
    if type_filter not in ("all", "ip_address", "domain", "cve", "entity", "alert", "incident"):
        type_filter = "all"

    # Try FTS5 via storage backend
    from intelgraph.api.main import _container

    backend = _container.backend
    try:
        # Check if FTS5 table exists
        if hasattr(backend, "_require"):
            conn = backend._require()
            has_fts = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='search_index'"
            ).fetchone()
            if has_fts:
                if type_filter in ("entity", "alert", "incident"):
                    pass
                results = conn.execute(
                    """
                    SELECT si.node_id, si.entity_type, si.entity_identifier,
                           rank as relevance, n.confidence_score
                    FROM search_index si
                    JOIN graph_nodes n ON n.node_id = si.node_id
                    WHERE search_index MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (_fts_sanitize(query), limit),
                ).fetchall()
                return [
                    {
                        "node_id": r["node_id"],
                        "entity_type": r["entity_type"],
                        "entity_identifier": r["entity_identifier"],
                        "confidence": r["confidence_score"],
                        "relevance": round(r["relevance"], 2),
                    }
                    for r in results
                ]
    except Exception:
        pass

    # Fallback to dashboard state nodes (real pipeline data)
    ds_results = _search_dashboard_state(query, type_filter, limit)
    if ds_results:
        return ds_results

    # Fallback to in-memory search
    return _search_in_memory(qe, query, type_filter, limit)


def _fts_sanitize(query: str) -> str:
    """Convert user query to FTS5-safe MATCH expression."""
    import re

    query = query.strip()
    if not query:
        return ""
    escaped = re.sub(r"[^\w\s.]", " ", query)
    escaped = re.sub(r"\s+", " ", escaped).strip()
    if not escaped:
        return ""
    terms = escaped.split()
    fts_terms = [f'"{t}"*' for t in terms]
    return " AND ".join(fts_terms)
