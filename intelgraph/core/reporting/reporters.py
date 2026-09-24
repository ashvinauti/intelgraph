from __future__ import annotations

import os
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from intelgraph.core.reporting.models import Report, ReportType

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _generate_id() -> str:
    return f"rpt_{uuid.uuid4().hex[:12]}"


def generate_report(
    report_type: str,
    data: dict[str, Any],
    time_range: tuple[str, str] | None = None,
) -> Report:
    """Generate a report from the given data.  'data' is the PipelineResult.to_dict() output
    optionally augmented with computed fields."""
    report_id = _generate_id()
    now = _now_iso()
    t_start, t_end = time_range or ("", "")

    if report_type == ReportType.THREAT_SUMMARY.value:
        title = "Threat Summary Report"
        html = _render_threat_summary(data, title, now, t_start, t_end)
    elif report_type == ReportType.ENTITY_DETAIL.value:
        title = f"Entity Detail Report: {data.get('entity_identifier', data.get('entity_id', 'unknown'))}"
        html = _render_entity_detail(data, title, now, t_start, t_end)
    elif report_type == ReportType.EXECUTIVE_SUMMARY.value:
        title = "Executive Summary Report"
        html = _render_executive_summary(data, title, now, t_start, t_end)
    else:
        raise ValueError(f"Unknown report type: {report_type}")

    report = Report(
        report_id=report_id,
        report_type=report_type,
        format="html",
        title=title,
        time_range_start=t_start,
        time_range_end=t_end,
        generated_at=now,
        html_content=html,
        metadata={
            "node_count": data.get("graph_node_count", 0),
            "alert_count": data.get("alert_count", 0),
        },
    )
    return report


# ---------------------------------------------------------------------------
# Threat Summary
# ---------------------------------------------------------------------------


def _render_threat_summary(data: dict, title: str, now: str, t_start: str, t_end: str) -> str:
    nodes = data.get("graph_nodes_summary", [])
    edges = data.get("graph_edges_summary", [])
    alerts = data.get("alerts", [])
    incidents = data.get("incidents", [])
    chain_stats = data.get("chain_stats", {}) or {}

    # Top threats sorted by threat_score
    top_threats = sorted(
        [n for n in nodes if n.get("threat_score", 0) > 0],
        key=lambda n: n["threat_score"],
        reverse=True,
    )[:10]

    # Source distribution from evidence edges or truth_entries
    truth_entries = data.get("truth_entries", [])
    sources = Counter()
    for te in truth_entries:
        if isinstance(te, dict):
            src = te.get("source", "unknown")
            sources[src] += 1
    source_list = sorted(sources.items(), key=lambda x: -x[1])

    # Entity type breakdown
    etypes = Counter(n.get("entity_type", "Unknown") for n in nodes)
    etype_list = sorted(etypes.items(), key=lambda x: -x[1])

    template = _env.get_template("threat_summary.html")
    return template.render(
        title=title,
        generated_at=now,
        time_range_start=t_start,
        time_range_end=t_end,
        node_count=len(nodes),
        edge_count=len(edges),
        alert_count=len(alerts),
        incident_count=len(incidents),
        contradiction_count=data.get("contradiction_count", 0),
        chain_count=chain_stats.get("total_chain_count", 0),
        top_threats=top_threats,
        alerts=alerts,
        incidents=incidents,
        sources=source_list,
        entity_types=etype_list,
    )


# ---------------------------------------------------------------------------
# Entity Detail
# ---------------------------------------------------------------------------


def _render_entity_detail(data: dict, title: str, now: str, t_start: str, t_end: str) -> str:
    template = _env.get_template("entity_detail.html")
    return template.render(
        title=title,
        generated_at=now,
        time_range_start=t_start,
        time_range_end=t_end,
        entity_id=data.get("entity_id", ""),
        entity_type=data.get("entity_type", ""),
        entity_identifier=data.get("entity_identifier", ""),
        confidence=data.get("confidence", 0),
        threat_score=data.get("threat_score", 0),
        evidence_list=data.get("evidence_list", []),
        relationships=data.get("relationships", []),
        chain=data.get("chain", {}),
        playbook_status=data.get("playbook_status"),
    )


# ---------------------------------------------------------------------------
# Executive Summary
# ---------------------------------------------------------------------------


def _render_executive_summary(data: dict, title: str, now: str, t_start: str, t_end: str) -> str:
    nodes = data.get("graph_nodes_summary", [])
    alerts = data.get("alerts", [])
    incidents = data.get("incidents", [])
    chain_stats = data.get("chain_stats", {}) or {}

    top_threats = sorted(
        [n for n in nodes if n.get("threat_score", 0) > 0],
        key=lambda n: n["threat_score"],
        reverse=True,
    )[:5]

    high_risk_cves = len(
        [n for n in nodes if n.get("entity_type") == "CveEntity" and n.get("confidence", 0) >= 90]
    )

    findings = []
    if top_threats:
        findings.append(
            f"Top threat identified: {top_threats[0]['entity_identifier']} with score {top_threats[0]['threat_score']:.0f}"
        )
    if high_risk_cves:
        findings.append(f"{high_risk_cves} high-risk CVE(s) detected requiring immediate attention")
    if incidents:
        findings.append(
            f"{len(incidents)} incident(s) generated, {sum(1 for i in incidents if i.get('confirmed'))} confirmed"
        )
    if alerts:
        criticals = sum(1 for a in alerts if a.get("severity") == "critical")
        if criticals:
            findings.append(f"{criticals} critical alert(s) triggered")
    if not findings:
        findings.append("No significant threats detected in this period.")

    recommendations = []
    if top_threats and top_threats[0]["threat_score"] >= 75:
        recommendations.append(
            f"Immediately investigate {top_threats[0]['entity_identifier']} — critical threat score"
        )
    if high_risk_cves:
        recommendations.append("Prioritize patching identified high-risk CVEs")
    if chain_stats.get("total_chain_count", 0) > 100:
        recommendations.append("Evidence chain volume is high; consider consolidating")
    if not recommendations:
        recommendations.append("Continue monitoring — no immediate action required")

    playbook_statuses = data.get("playbook_statuses", {}) or {}
    playbook_actions = []
    for inc_id, pb in playbook_statuses.items():
        steps = pb.get("steps", [])
        playbook_actions.append(
            {
                "name": pb.get("playbook_name", inc_id),
                "completed": sum(1 for s in steps if s.get("completed")),
                "pending": sum(1 for s in steps if not s.get("completed")),
            }
        )

    template = _env.get_template("executive_summary.html")
    return template.render(
        title=title,
        generated_at=now,
        time_range_start=t_start,
        time_range_end=t_end,
        threats=len(top_threats),
        incidents=len(incidents),
        high_risk_cves=high_risk_cves,
        alerts=len(alerts),
        entities=len(nodes),
        sources=data.get("source_count", 0),
        findings=findings,
        recommendations=recommendations,
        top_threats=top_threats,
        playbook_actions=playbook_actions,
    )
