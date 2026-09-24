"""FastAPI router for the Investigation Workspace API.

Endpoints cover investigation lifecycle, pivot-from-seed, findings, notes,
and timeline events. All write endpoints require JWT auth (POST/DELETE).

Public read endpoints (GET) return investigation summaries, findings,
notes, and timelines without auth, mirroring the existing dashboard pattern.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from intelgraph.core.investigation.manager import InvestigationManager
from intelgraph.core.investigation.models import Finding

router = APIRouter(prefix="/investigations", tags=["investigations"])


def _get_manager() -> InvestigationManager:
    from intelgraph.api.main import _container

    state_path = getattr(_container, "investigation_state", None)
    return InvestigationManager(state_path=state_path)


def _build_graph() -> Any:
    from intelgraph.api.main import _container
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
            from intelgraph.core.graph.edge import Edge

            g.edges[rel.id] = Edge(relationship=rel)
    return g


@router.get("", summary="List all investigations")
def list_investigations(request: Request) -> dict[str, Any]:
    mgr = _get_manager()
    return {"investigations": [inv.to_dict() for inv in mgr.list_investigations()]}


@router.post("", summary="Create a new investigation")
def create_investigation(body: dict[str, Any], request: Request) -> dict[str, Any]:
    name = body.get("name", "").strip()
    seed_ioc = body.get("seed_ioc", "").strip()
    seed_ioc_type = body.get("seed_ioc_type", "").strip().lower()
    created_by = body.get("created_by", "analyst")
    tags = body.get("tags", [])

    if not name or not seed_ioc or not seed_ioc_type:
        raise HTTPException(status_code=400, detail="name, seed_ioc, and seed_ioc_type are required")

    mgr = _get_manager()
    inv = mgr.create_investigation(
        name=name,
        seed_ioc=seed_ioc,
        seed_ioc_type=seed_ioc_type,
        created_by=created_by,
        tags=tags,
    )
    return inv.to_dict()


@router.get("/{investigation_id}", summary="Get investigation details")
def get_investigation(investigation_id: str, request: Request) -> dict[str, Any]:
    mgr = _get_manager()
    inv = mgr.get_investigation(investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return inv.to_dict()


@router.delete("/{investigation_id}", summary="Delete an investigation")
def delete_investigation(investigation_id: str, request: Request) -> dict[str, Any]:
    mgr = _get_manager()
    ok = mgr.delete_investigation(investigation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {"status": "ok"}


@router.patch("/{investigation_id}/status", summary="Update investigation status")
def update_status(
    investigation_id: str,
    body: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    status = body.get("status", "").strip().lower()
    if not status:
        raise HTTPException(status_code=400, detail="status is required")
    mgr = _get_manager()
    inv = mgr.update_status(investigation_id, status)
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return inv.to_dict()


@router.post("/{investigation_id}/pivot", summary="Run pivot analysis from seed IOC")
def run_pivot(
    investigation_id: str,
    body: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    mgr = _get_manager()
    inv = mgr.get_investigation(investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    max_depth = int(body.get("max_depth", 2))
    entity_types = body.get("entity_types")

    graph = _build_graph()
    findings = mgr.pivot_from_seed(
        investigation_id=investigation_id,
        graph=graph,
        max_depth=max_depth,
        entity_types=entity_types,
    )
    return {
        "investigation_id": investigation_id,
        "seed_ioc": inv.seed_ioc,
        "seed_ioc_type": inv.seed_ioc_type,
        "new_findings": len(findings),
        "findings": [f.to_dict() for f in findings],
    }


@router.get("/{investigation_id}/findings", summary="List all findings in an investigation")
def list_findings(investigation_id: str, request: Request) -> dict[str, Any]:
    mgr = _get_manager()
    inv = mgr.get_investigation(investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {"findings": [f.to_dict() for f in inv.findings]}


@router.post("/{investigation_id}/findings", summary="Manually add a finding")
def add_finding(
    investigation_id: str,
    body: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    mgr = _get_manager()
    inv = mgr.get_investigation(investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    import uuid
    from datetime import UTC, datetime

    finding = Finding(
        finding_id=f"find_{uuid.uuid4().hex[:10]}",
        investigation_id=investigation_id,
        ioc_value=body.get("ioc_value", ""),
        ioc_type=body.get("ioc_type", "unknown"),
        finding_type=body.get("finding_type", "direct"),
        confidence=int(body.get("confidence", 50)),
        evidence_summary=body.get("evidence_summary", ""),
        related_entity_id=body.get("related_entity_id"),
        relationships=body.get("relationships", []),
    )
    mgr.add_finding(investigation_id, finding)
    inv = mgr.get_investigation(investigation_id)
    return inv.to_dict()  # type: ignore[union-attr]


@router.get("/{investigation_id}/timeline", summary="Get investigation timeline")
def get_timeline(investigation_id: str, request: Request) -> dict[str, Any]:
    mgr = _get_manager()
    events = mgr.get_timeline(investigation_id)
    if not events and mgr.get_investigation(investigation_id) is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return {"events": [e.to_dict() for e in events]}


@router.post("/{investigation_id}/timeline", summary="Add a custom timeline event")
def add_timeline_event(
    investigation_id: str,
    body: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    mgr = _get_manager()
    event_type = body.get("event_type", "custom").strip()
    title = body.get("title", "").strip()
    description = body.get("description", "").strip()
    source = body.get("source", "analyst")
    metadata = body.get("metadata", {})

    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    event = mgr.add_timeline_event(
        investigation_id, event_type, title, description, source, metadata
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return event.to_dict()


@router.get("/{investigation_id}/notes", summary="List all notes in an investigation")
def list_notes(investigation_id: str, request: Request) -> dict[str, Any]:
    mgr = _get_manager()
    inv = mgr.get_investigation(investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    pinned_first = sorted(inv.notes, key=lambda n: (not n.pinned, n.created_at))
    return {"notes": [n.to_dict() for n in pinned_first]}


@router.post("/{investigation_id}/notes", summary="Add an analyst note")
def add_note(
    investigation_id: str,
    body: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    mgr = _get_manager()
    inv = mgr.get_investigation(investigation_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    author = body.get("author", "analyst").strip()
    content = body.get("content", "").strip()
    pinned = bool(body.get("pinned", False))

    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    note = mgr.add_note(investigation_id, author, content, pinned=pinned)
    return note.to_dict()  # type: ignore[union-attr]


@router.delete("/{investigation_id}/notes/{note_id}", summary="Delete a note")
def delete_note(investigation_id: str, note_id: str, request: Request) -> dict[str, Any]:
    mgr = _get_manager()
    ok = mgr.delete_note(investigation_id, note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"status": "ok"}