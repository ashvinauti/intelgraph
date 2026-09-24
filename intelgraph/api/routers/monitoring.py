from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from intelgraph.core.enterprise import get_performance_collector

router = APIRouter(prefix="/metrics", tags=["monitoring"])


@router.get("/performance")
def get_performance():
    """Full performance snapshot: pipeline stats, API latency percentiles, system metrics, component health."""
    perf = get_performance_collector()
    return perf.full_snapshot()


@router.get("/health")
def get_health():
    """Component health status (healthy/degraded/down) with per-component details."""
    perf = get_performance_collector()
    return perf.get_overall_health()


@router.get("/pipeline")
def get_pipeline_history():
    """Last 10 pipeline run details with durations and entity counts."""
    perf = get_performance_collector()
    return {
        "runs": perf.get_pipeline_history(10),
        "stats": perf.get_pipeline_stats(),
    }


@router.get("/stream")
async def metrics_stream(request: Request):
    """SSE endpoint for real-time system metrics (CPU/memory/disk). Pushes every 5 seconds."""
    perf = get_performance_collector()

    async def _event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                system = perf.record_system_metrics()
                health = perf.get_overall_health()
                pipeline = perf.get_pipeline_stats()
                data = json.dumps(
                    {
                        "system": system,
                        "health": {"overall_status": health["overall_status"]},
                        "pipeline": pipeline,
                    }
                )
                yield f"event: metrics\ndata: {data}\n\n"
                await asyncio.sleep(5)
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
