from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from intelgraph.api.auth import _token_store, decode_token
from intelgraph.core.multitenant import get_tenant_manager

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", summary="Get current user info")
def get_me(request: Request) -> dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth[7:]
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    sub = payload.get("sub", "")
    user_data = _token_store.get(sub, {})
    tenant_id = payload.get("tenant_id", "")
    tenant_name = ""
    if tenant_id:
        tenant = get_tenant_manager().get(tenant_id)
        tenant_name = tenant.name if tenant else ""
    return {
        "user_id": sub,
        "username": user_data.get("username", sub),
        "role": user_data.get("role", "user"),
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
    }
