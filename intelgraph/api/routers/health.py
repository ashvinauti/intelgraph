from __future__ import annotations

from fastapi import APIRouter

from intelgraph import __version__
from intelgraph.api.models import HealthResponse
from intelgraph.core.enterprise import get_metrics

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "",
    response_model=HealthResponse,
    summary="Health check",
    description="Basic health check. Returns OK if the service is running. Read-only, no business logic.",
)
def health():
    return HealthResponse(status="ok", version=__version__)


@router.get(
    "/live",
    summary="Liveness probe",
    description="Returns liveness status with metrics snapshot. Read-only, no business logic.",
)
def live():
    metrics = get_metrics().snapshot()
    return {"status": "alive", "metrics": metrics}


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Readiness check validating storage connectivity only. Read-only, no business logic.",
)
def ready():
    from intelgraph.api.main import _container

    backend = _container.backend
    storage_ok = False
    try:
        backend.list_entities()
        storage_ok = True
    except Exception:
        storage_ok = False
    metrics = get_metrics().snapshot()
    return {
        "status": "ready" if storage_ok else "unhealthy",
        "storage": "connected" if storage_ok else "disconnected",
        "metrics": metrics,
    }
