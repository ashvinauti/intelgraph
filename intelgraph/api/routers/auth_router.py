from __future__ import annotations

from fastapi import APIRouter, HTTPException

from intelgraph.api.auth import login_user, refresh_token, register_user
from intelgraph.api.models import (
    AuthLogin,
    AuthRefresh,
    AuthRegister,
    RefreshTokenResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    summary="Register a new user",
    description="Register a new user with username, password, and optional role. Returns a JWT access token.",
)
def register(body: AuthRegister):
    return register_user(body.username, body.password, role=body.role)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in",
    description="Authenticate with username and password. Returns a JWT access token.",
)
def login(body: AuthLogin):
    result = login_user(body.username, body.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return result


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    summary="Refresh access token",
    description="Exchange an existing valid access token for a new one with a fresh expiry.",
)
def refresh(body: AuthRefresh):
    result = refresh_token(body.access_token)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return result
