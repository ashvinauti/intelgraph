from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from intelgraph.api.auth import (
    authenticate_oauth_client,
    refresh_oauth_token,
    register_oauth_client,
)
from intelgraph.api.models import OAuthClientRegister, OAuthTokenRequest, OAuthTokenResponse

router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.post("/token", response_model=OAuthTokenResponse)
def token(body: OAuthTokenRequest):
    if body.grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="Unsupported grant_type")
    if not body.client_id or not body.client_secret:
        raise HTTPException(status_code=400, detail="client_id and client_secret required")
    result = authenticate_oauth_client(body.client_id, body.client_secret)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid client credentials")
    return result


@router.post("/register")
def register_client(body: OAuthClientRegister, request: Request):
    """Register a new OAuth2 client. Requires admin role and API key auth."""
    from intelgraph.api.auth import get_user_role, validate_token

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token_str = auth[7:]
    uid = validate_token(token_str)
    if uid is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    role = get_user_role(uid)
    if not role or role.name not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin role required")
    result = register_oauth_client(
        client_id=body.client_id,
        client_secret=body.client_secret,
        tenant_id=body.tenant_id or "",
        scopes=body.scopes or ["read"],
    )
    return result


@router.post("/refresh", response_model=OAuthTokenResponse)
def refresh(body: OAuthTokenRequest):
    if body.grant_type != "refresh_token":
        raise HTTPException(status_code=400, detail="Unsupported grant_type")
    if not body.refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token required")
    result = refresh_oauth_token(body.refresh_token)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return result
