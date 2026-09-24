from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request

from intelgraph.api.auth import get_user_role, validate_token
from intelgraph.core.enterprise.authz import has_permission


def require_auth(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    return validate_token(token)


def require_permission(permission: str) -> Any:
    def _checker(request: Request) -> None:
        uid = require_auth(request)
        if uid is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        role = get_user_role(uid)
        if not has_permission(role, permission):
            raise HTTPException(status_code=403, detail=f"Forbidden: {permission} required")

    return Depends(_checker)
