from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from intelgraph.api.auth import login_with_api_key
from intelgraph.core.multitenant import get_tenant_manager

router = APIRouter(prefix="/tenants", tags=["Tenants"])


def _tm() -> Any:
    return get_tenant_manager()


@router.post("", summary="Create a new tenant (super-admin)")
def create_tenant(
    request: Request,
    name: str = Query(..., description="Tenant display name"),
) -> dict[str, Any]:
    tenant, api_key = _tm().create_tenant(name)
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "api_key": api_key,
        "created_at": tenant.created_at,
        "message": f"Tenant '{name}' created. Save the API key — it will not be shown again.",
    }


@router.delete("", summary="Delete a tenant (super-admin)")
def delete_tenant(
    request: Request,
    tenant_id: str = Query(..., description="Tenant ID to delete"),
) -> dict[str, Any]:
    ok = _tm().delete_tenant(tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    return {"deleted": tenant_id}


@router.get("/list", summary="List all tenants")
def list_tenants(request: Request) -> list[dict[str, Any]]:
    return [t.to_dict() for t in _tm().list_tenants()]


@router.get("/{tenant_id}", summary="Get tenant details")
def get_tenant(tenant_id: str) -> dict[str, Any]:
    tenant = _tm().get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    return tenant.to_dict()


@router.get("/{tenant_id}/stats", summary="Get tenant usage stats")
def get_tenant_stats(tenant_id: str) -> dict[str, Any]:
    stats = _tm().get_stats(tenant_id)
    if "error" in stats:
        raise HTTPException(status_code=404, detail=stats["error"])
    return stats


@router.post("/{tenant_id}/rotate-key", summary="Rotate API key")
def rotate_api_key(tenant_id: str) -> dict[str, Any]:
    result = _tm().rotate_api_key(tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    return {"tenant_id": result[0], "api_key": result[1]}


@router.post("/login", summary="Login with tenant API key")
def tenant_login(api_key: str = Query(..., description="Tenant API key")) -> dict[str, Any]:
    result = login_with_api_key(api_key)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return result
