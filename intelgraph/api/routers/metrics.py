from __future__ import annotations

from fastapi import APIRouter

from intelgraph.core.enterprise import get_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _prometheus_format() -> str:
    metrics = get_metrics().snapshot()
    lines: list[str] = []

    lines.append("# HELP intelgraph_request_count_total Total request count")
    lines.append("# TYPE intelgraph_request_count_total counter")
    lines.append(f"intelgraph_request_count_total {metrics.get('total_requests', 0)}")

    lines.append("# HELP intelgraph_error_count_total Total error count (5xx)")
    lines.append("# TYPE intelgraph_error_count_total counter")
    lines.append(f"intelgraph_error_count_total {metrics.get('total_errors', 0)}")

    lines.append("# HELP intelgraph_request_latency_ms Average request latency in ms")
    lines.append("# TYPE intelgraph_request_latency_ms gauge")
    lines.append(f"intelgraph_request_latency_ms {metrics.get('avg_duration_ms', 0.0)}")

    endpoints = metrics.get("endpoints", {})
    for ep, count in sorted(endpoints.items()):
        ep.replace("/", "_").replace("-", "_").strip("_")
        lines.append(f'# HELP intelgraph_endpoint_requests_total Requests per endpoint "{ep}"')
        lines.append("# TYPE intelgraph_endpoint_requests_total counter")
        lines.append(f'intelgraph_endpoint_requests_total{{endpoint="{ep}"}} {count}')

    status_codes = metrics.get("status_codes", {})
    for code, count in sorted(status_codes.items()):
        lines.append("# HELP intelgraph_status_code_total Requests per status code")
        lines.append("# TYPE intelgraph_status_code_total counter")
        lines.append(f'intelgraph_status_code_total{{code="{code}"}} {count}')

    gauges = metrics.get("gauges", {})
    for name, value in sorted(gauges.items()):
        safe_name = name.replace(" ", "_").replace("-", "_")
        lines.append(f"# HELP intelgraph_{safe_name} Gauge metric")
        lines.append("# TYPE intelgraph_gauge gauge")
        lines.append(f"intelgraph_{safe_name} {value}")

    lines.append("# HELP intelgraph_active_connections Active connections (estimated)")
    lines.append("# TYPE intelgraph_active_connections gauge")
    total = metrics.get("total_requests", 0)
    errors = metrics.get("total_errors", 0)
    active = max(0, total - errors)
    lines.append(f"intelgraph_active_connections {active}")

    return "\n".join(lines) + "\n"


@router.get(
    "",
    summary="Prometheus metrics",
    description="Expose metrics in Prometheus text format. Read-only, no business logic execution.",
)
def get_prometheus_metrics():
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=_prometheus_format(),
        media_type="text/plain; version=0.0.4",
    )
