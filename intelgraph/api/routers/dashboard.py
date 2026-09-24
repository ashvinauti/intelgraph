from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from intelgraph.core.explanation.builder import ExplanationBuilder
from intelgraph.core.nlp.extractor import NEREngine

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _get_tenant(req: Request) -> str:
    return getattr(req.state, "tenant_id", "")


# ---------------------------------------------------------------------------
# In-memory pipeline result store — populated by feed_dashboard()
# Persisted to /tmp/opencode/phase7/dashboard_state.json for server restarts
# ---------------------------------------------------------------------------

_STATE_DIR = Path("/tmp/opencode/phase7")


class DashboardState:
    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any] | None] = {}
        self._sources_map: dict[str, dict[str, Any]] = {}
        self._ner_counts_map: dict[str, dict[str, int]] = {}
        self._ner_samples_map: dict[str, dict[str, list[str]]] = {}
        self._tenant_results: dict[str, dict[str, Any] | None] = {}
        # Auto-load persisted state on init so pipeline data survives restarts
        self._load("")

    def _state_path(self, tenant_id: str = "") -> Path:
        suffix = f"_{tenant_id}" if tenant_id else ""
        return _STATE_DIR / f"dashboard_state{suffix}.json"

    def _load(self, tenant_id: str = "") -> None:
        path = self._state_path(tenant_id)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                if tenant_id:
                    self._tenant_results[tenant_id] = data.get("result")
                else:
                    self._results[tenant_id] = data.get("result")
                    self._sources_map[tenant_id] = data.get("sources", {})
                    self._ner_counts_map[tenant_id] = data.get("ner_counts", {})
                    self._ner_samples_map[tenant_id] = data.get("ner_samples", {})
            except Exception:
                pass

    def _save(self, tenant_id: str = "") -> None:
        path = self._state_path(tenant_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if tenant_id:
            data = {"result": self._tenant_results.get(tenant_id)}
        else:
            data = {
                "result": self._results.get(""),
                "sources": self._sources_map.get("", {}),
                "ner_counts": self._ner_counts_map.get("", {}),
                "ner_samples": self._ner_samples_map.get("", {}),
            }
        path.write_text(json.dumps(data, indent=2))

    def feed(self, result: dict[str, Any], tenant_id: str = "") -> None:
        if tenant_id:
            self._tenant_results[tenant_id] = result
        else:
            self._results[""] = result
        self._save(tenant_id)

    def feed_sources(self, sources: dict[str, Any], tenant_id: str = "") -> None:
        if not tenant_id:
            self._sources_map[""] = sources
            self._save()

    def feed_ner(
        self, counts: dict[str, int], samples: dict[str, list[str]], tenant_id: str = ""
    ) -> None:
        if not tenant_id:
            self._ner_counts_map[""] = counts
            self._ner_samples_map[""] = samples
            self._save()

    def _get_result(self, tenant_id: str) -> dict[str, Any] | None:
        if tenant_id:
            r = self._tenant_results.get(tenant_id)
            if r is not None:
                return r
            self._load(tenant_id)
            return self._tenant_results.get(tenant_id)
        return self.results.get("")

    @property
    def result(self) -> dict[str, Any] | None:
        return self._results.get("")

    def result_for(self, tenant_id: str) -> dict[str, Any] | None:
        return self._get_result(tenant_id)

    @property
    def sources(self) -> dict[str, Any]:
        return self._sources_map.get("", {})

    @property
    def ner_counts(self) -> dict[str, int]:
        return self._ner_counts_map.get("", {})

    @property
    def ner_samples(self) -> dict[str, list[str]]:
        return self._ner_samples_map.get("", {})


dashboard_state = DashboardState()


# ---------------------------------------------------------------------------
# Helper: recompute NER stats from source texts
# ---------------------------------------------------------------------------


def _parse_iso(s: str | None) -> datetime | None:
    from datetime import datetime

    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def _compute_ner_stats(source_texts: list[str]) -> tuple[dict[str, int], dict[str, list[str]]]:
    ner = NEREngine()
    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {"DOMAIN": [], "FILENAME": [], "UNKNOWN": []}
    seen: dict[str, set[str]] = {k: set() for k in samples}
    for text in source_texts:
        for entity in ner.extract(text):
            label = entity.label
            counts[label] = counts.get(label, 0) + 1
            if label in seen and entity.text not in seen[label]:
                seen[label].add(entity.text)
                if len(samples[label]) < 10:
                    samples[label].append(entity.text)
    return counts, samples


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/summary")
def get_summary(request: Request) -> dict[str, Any]:
    tenant_id = _get_tenant(request)
    r = dashboard_state.result_for(tenant_id) if tenant_id else dashboard_state.result
    if not r:
        return {"error": "No pipeline data available. Run a pipeline first."}
    counts, _ = _compute_ner_stats(r.get("source_texts", []))
    nodes = r.get("graph_nodes_summary", [])
    top_threats = sorted(
        [n for n in nodes if n.get("threat_score", 0) > 0],
        key=lambda n: n["threat_score"],
        reverse=True,
    )[:5]
    return {
        "node_count": r.get("graph_node_count", 0),
        "edge_count": r.get("graph_edge_count", 0),
        "contradiction_count": r.get("contradiction_count", 0),
        "alert_count": r.get("alert_count", 0),
        "incident_count": r.get("incident_count", 0),
        "entity_count": r.get("entity_count", 0),
        "path_count": r.get("path_count", 0),
        "domain_count": counts.get("DOMAIN", 0),
        "filename_count": counts.get("FILENAME", 0),
        "unknown_count": counts.get("UNKNOWN", 0),
        "source_count": r.get("source_count", 0),
        "chain_count": (r.get("chain_stats") or {}).get("total_chain_count", 0),
        "error_count": len(r.get("errors", [])),
        "dashboard_snapshot": r.get("dashboard_snapshot"),
        "tenant_id": tenant_id or "default",
        "top_threats": top_threats,
        "max_threat_score": max((n.get("threat_score", 0) for n in nodes), default=0),
        "anomaly_results": r.get("anomaly_results", [])[:20],
    }


# ---------------------------------------------------------------------------
# SSE: real-time metric streaming
# ---------------------------------------------------------------------------

_SSE_INTERVAL = 5.0  # seconds between pushes


def _sse_metrics(tenant_id: str = "") -> dict[str, Any]:
    """Return the 4 key metrics (+ extras) for SSE push."""
    r = dashboard_state.result_for(tenant_id) if tenant_id else dashboard_state.result
    if not r:
        return {
            "node_count": 0,
            "contradiction_count": 0,
            "alert_count": 0,
            "incident_count": 0,
            "entity_count": 0,
            "edge_count": 0,
        }
    return {
        "node_count": r.get("graph_node_count", 0),
        "contradiction_count": r.get("contradiction_count", 0),
        "alert_count": r.get("alert_count", 0),
        "incident_count": r.get("incident_count", 0),
        "entity_count": r.get("entity_count", 0),
        "edge_count": r.get("graph_edge_count", 0),
    }


@router.get("/stream")
async def dashboard_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events endpoint for real-time dashboard metrics."""
    tenant_id = _get_tenant(request)

    async def _event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                data = json.dumps(_sse_metrics(tenant_id))
                yield f"event: metrics\ndata: {data}\n\n"
                await asyncio.sleep(_SSE_INTERVAL)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/incidents")
def get_incidents(request: Request) -> list[dict[str, Any]]:
    tenant_id = _get_tenant(request)
    r = dashboard_state.result_for(tenant_id) if tenant_id else dashboard_state.result
    if not r:
        return []
    severity_map = {"critical": 3, "high": 2, "medium": 1, "low": 0}

    def _normalize(item: dict[str, Any]) -> dict[str, Any]:
        raw_sev = item.get("severity", "medium")
        sev = severity_map.get(raw_sev, 1) if isinstance(raw_sev, str) else (raw_sev or 1)
        status = "active"
        if item.get("resolved") is True:
            status = "resolved"
        elif item.get("confirmed") is not True:
            status = "unconfirmed"
        return {
            "id": item.get("alert_id", item.get("id", "")),
            "category": item.get("category", "unknown"),
            "severity": sev,
            "message": item.get("message", ""),
            "status": status,
            "entity_id": item.get("entity_id", ""),
            "source_layers": item.get("source_layers", []),
            "current_value": item.get("current_value"),
            "threshold_value": item.get("threshold_value"),
            "resolved": item.get("resolved", False),
            "confirmed": item.get("confirmed", False),
        }

    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in r.get("incidents", []) + r.get("alerts", []):
        normalized = _normalize(item)
        iid = normalized["id"]
        if iid and iid not in seen:
            seen.add(iid)
            result.append(normalized)
    return result


@router.get("/sources")
def get_sources(request: Request) -> dict[str, Any]:
    return {
        "sources": dashboard_state.sources,
        "ner": {
            "counts": dashboard_state.ner_counts,
            "samples": dashboard_state.ner_samples,
        },
        "tenant_id": _get_tenant(request) or "default",
    }


@router.get("/ner-stats")
def get_ner_stats(request: Request) -> dict[str, Any]:
    tenant_id = _get_tenant(request)
    r = dashboard_state.result_for(tenant_id) if tenant_id else dashboard_state.result
    if not r:
        return {"error": "No pipeline data available."}
    counts, samples = _compute_ner_stats(r.get("source_texts", []))
    return {"counts": counts, "samples": samples}


@router.get("/incidents/{incident_id}/explain")
def explain_incident(request: Request, incident_id: str) -> dict[str, Any]:
    tenant_id = _get_tenant(request)
    r = dashboard_state.result_for(tenant_id) if tenant_id else dashboard_state.result
    if not r:
        return {"error": "No pipeline data available. Run a pipeline first."}
    builder = ExplanationBuilder(r)
    return builder.explain(incident_id)


@router.get("/incidents/{incident_id}/playbook")
def get_incident_playbook(request: Request, incident_id: str) -> dict[str, Any]:
    tenant_id = _get_tenant(request)
    r = dashboard_state.result_for(tenant_id) if tenant_id else dashboard_state.result
    if not r:
        return {"error": "No pipeline data available."}
    statuses = r.get("playbook_statuses", {})
    pb = statuses.get(incident_id)
    if not pb:
        return {
            "incident_id": incident_id,
            "playbook": None,
            "message": "No playbook matched for this incident.",
        }
    return {"incident_id": incident_id, "playbook": pb}


@router.post("/feed")
def feed_dashboard_data(request: Request, data: dict[str, Any]) -> dict[str, Any]:
    """Feed pipeline results to the dashboard state. Call this after running a pipeline."""
    tenant_id = _get_tenant(request)
    result = data.get("result", data)
    sources = data.get("sources", {})
    ner_counts = data.get("ner_counts", {})
    ner_samples = data.get("ner_samples", {})
    
    dashboard_state.feed(result, tenant_id)
    if sources:
        dashboard_state.feed_sources(sources, tenant_id)
    if ner_counts and ner_samples:
        dashboard_state.feed_ner(ner_counts, ner_samples, tenant_id)
    
    return {"status": "ok", "message": "Dashboard data updated"}


@router.get("/graph")
def get_graph(request: Request, limit: int = 200, since: str | None = None) -> dict[str, Any]:
    """Get graph data for D3 visualization."""
    tenant_id = _get_tenant(request)
    r = dashboard_state.result_for(tenant_id) if tenant_id else dashboard_state.result
    if not r:
        return {"nodes": [], "edges": []}
    
    nodes: list[dict[str, Any]] = r.get("graph_nodes_summary", [])
    edges: list[dict[str, Any]] = r.get("graph_edges_summary", [])
    
    # Temporal filter
    if since:
        from datetime import datetime, timedelta
        
        if since.endswith("d"):
            cutoff = datetime.now(UTC) - timedelta(days=int(since[:-1]))
        else:
            try:
                cutoff = datetime.fromisoformat(since)
            except ValueError:
                cutoff = None
        if cutoff:
            nodes = [
                n
                for n in nodes
                if _parse_iso(n.get("last_seen")) and _parse_iso(n["last_seen"]) >= cutoff
            ]
    
    if len(nodes) > limit:
        # Sort by confidence descending, take top *limit*
        nodes_sorted = sorted(nodes, key=lambda n: n.get("confidence", 0), reverse=True)
        kept = nodes_sorted[:limit]
        kept_ids = {n["node_id"] for n in kept}
        edges = [e for e in edges if (e.get("source_id") or e.get("source", "")) in kept_ids and (e.get("target_id") or e.get("target", "")) in kept_ids]
        nodes = kept
    
    # Transform to D3 format
    d3_nodes = [
        {
            "node_id": n.get("node_id", ""),
            "id": n.get("node_id", ""),
            "entity_type": n.get("entity_type", "unknown"),
            "entity_identifier": n.get("entity_identifier", ""),
            "threat_score": n.get("threat_score", 0),
            "evidence_count": n.get("evidence_count", 0),
            "confidence": n.get("confidence", 0),
        }
        for n in nodes
    ]
    
    d3_edges = [
        {
            "source": e.get("source_id") or e.get("source", ""),
            "target": e.get("target_id") or e.get("target", ""),
            "source_id": e.get("source_id") or e.get("source", ""),
            "target_id": e.get("target_id") or e.get("target", ""),
            "relationship_type": e.get("relationship_type", "related"),
            "type": e.get("relationship_type", "related"),
            "confidence": e.get("confidence", 0),
        }
        for e in edges
    ]
    
    return {"nodes": d3_nodes, "edges": d3_edges}


@router.post("/incidents/{incident_id}/playbook/steps/{step_id}/complete")
def complete_playbook_step(
    request: Request,
    incident_id: str,
    step_id: str,
    completed_by: str = "human",
    notes: str = "",
) -> dict[str, Any]:
    from intelgraph.core.playbook import PlaybookEngine

    engine = PlaybookEngine()
    tenant_id = _get_tenant(request)
    r = dashboard_state.result_for(tenant_id) if tenant_id else dashboard_state.result
    status_data = r.get("playbook_statuses") if r else None
    if status_data:
        engine.restore_from_dicts(status_data)
    status = engine.complete_step(incident_id, step_id, completed_by=completed_by, notes=notes)
    if status is None:
        raise HTTPException(
            status_code=404, detail=f"Incident {incident_id} has no active playbook."
        )
    if r is not None:
        r["playbook_statuses"] = engine.to_dicts()
    return {
        "incident_id": incident_id,
        "step_id": step_id,
        "completed": True,
        "playbook": engine.to_dicts().get(incident_id, {}),
    }
