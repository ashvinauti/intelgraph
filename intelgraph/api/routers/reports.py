from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from intelgraph.core.reporting.models import ReportType
from intelgraph.core.reporting.reporters import generate_report
from intelgraph.core.reporting.scheduler import REPORT_DIR, ReportScheduler

router = APIRouter(prefix="/reports", tags=["reports"])

_scheduler = ReportScheduler()
os.makedirs(REPORT_DIR, exist_ok=True)


def _get_data(request: Request) -> dict[str, Any]:
    """Get the latest pipeline result from dashboard_state."""
    try:
        from intelgraph.api.routers.dashboard import dashboard_state

        tenant_id = getattr(request.state, "tenant_id", None)
        r = dashboard_state.result_for(tenant_id) if tenant_id else dashboard_state.result
        return r or {}
    except Exception:
        return {}


@router.get("/scheduler")
def scheduler_status() -> dict[str, Any]:
    return {"reports_dir": REPORT_DIR}


@router.post("/generate")
def generate(body: dict[str, Any], request: Request) -> dict[str, Any]:
    rtype = body.get("type", "threat_summary")
    body.get("format", "html")
    time_range = body.get("time_range", "")

    data = _get_data(request)
    if not data:
        return {"error": "No pipeline data available. Run a pipeline first."}

    # Compute time range
    now = datetime.now(UTC)
    if time_range == "7d":
        since = now - timedelta(days=7)
    elif time_range == "30d":
        since = now - timedelta(days=30)
    else:
        since = None

    t_start = since.isoformat() if since else ""
    t_end = now.isoformat()

    # For entity_detail, extract specific entity info from data
    if rtype == ReportType.ENTITY_DETAIL.value:
        entity_id = body.get("entity_id", "")
        entity_identifier = body.get("entity_identifier", "")
        if entity_id or entity_identifier:
            detail_data = _build_entity_detail(data, entity_id or entity_identifier)
            if not detail_data:
                return {"error": f"Entity not found: {entity_id or entity_identifier}"}
            data = detail_data

    try:
        report = generate_report(rtype, data, time_range=(t_start, t_end))
    except ValueError as e:
        return {"error": str(e)}

    _scheduler.save_report(report)
    return {
        "status": "ok",
        "report_id": report.report_id,
        "report_type": rtype,
        "title": report.title,
        "generated_at": report.generated_at,
    }


def _build_entity_detail(data: dict, entity_key: str) -> dict[str, Any]:
    """Extract entity detail from pipeline result data."""
    nodes = data.get("graph_nodes_summary", [])
    target = None
    for n in nodes:
        if n.get("node_id") == entity_key or n.get("entity_identifier") == entity_key:
            target = n
            break
    if not target:
        return {}

    # Build a minimal graph from the nodes/edges in the result
    graph = data.get("_graph")
    evidence_list = []
    relationships = []
    chain = {}
    playbook_status = None

    # Get evidence from graph node
    if graph:
        node = graph.nodes.get(target["node_id"])
        if node:
            entity = node.entity
            for ev in getattr(entity, "evidence", ()):
                evidence_list.append(
                    {
                        "source": getattr(ev, "source", ""),
                        "content": getattr(ev, "content", ""),
                        "collected_at": str(getattr(ev, "collected_at", "")),
                        "trust_score": getattr(ev, "trust_score", 0),
                        "reliability_score": getattr(ev, "reliability_score", 0),
                    }
                )
            # Relationships
            for edge in graph.edges.values():
                if edge.source_id == target["node_id"] or edge.target_id == target["node_id"]:
                    relationships.append(
                        {
                            "source_id": edge.source_id,
                            "target_id": edge.target_id,
                            "type": edge.type,
                            "first_seen": str(getattr(edge, "first_seen", "")),
                            "last_seen": str(getattr(edge, "last_seen", "")),
                        }
                    )

            # Evidence chain
            chain_mgr = getattr(graph, "chain_manager", None)
            if chain_mgr:
                try:
                    chains = chain_mgr.get_chains_for_entity(target["node_id"])
                    if chains:
                        c = chains[0]
                        chain = {
                            "verification_status": getattr(c, "verification_status", "unknown"),
                            "overall_confidence": getattr(c, "overall_confidence", 0),
                            "steps": [
                                {
                                    "source": getattr(s, "source", ""),
                                    "support_type": getattr(s, "support_type", ""),
                                    "confidence": getattr(s, "confidence", 0),
                                }
                                for s in getattr(c, "items", [])
                            ],
                        }
                except Exception:
                    pass

            # Playbook
            for inc_id, pb in (data.get("playbook_statuses", {}) or {}).items():
                if target["node_id"] in inc_id:
                    playbook_status = pb
                    break

    return {
        "entity_id": target.get("node_id", ""),
        "entity_type": target.get("entity_type", ""),
        "entity_identifier": target.get("entity_identifier", ""),
        "confidence": target.get("confidence", 0),
        "threat_score": target.get("threat_score", 0),
        "evidence_list": evidence_list,
        "relationships": relationships,
        "chain": chain,
        "playbook_status": playbook_status,
    }


@router.get("")
def list_reports() -> dict[str, Any]:
    return {"reports": _scheduler.list_reports()}


@router.get("/{report_id}", response_model=None)
def get_report(report_id: str):
    meta = _scheduler.get_report(report_id)
    if not meta:
        return {"error": "Report not found"}
    html = _scheduler.get_report_html(report_id)
    if html:
        return HTMLResponse(content=html, media_type="text/html")
    return meta
