from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FieldError(BaseModel):
    field: str
    error: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[FieldError] | None = None


class EntityCreate(BaseModel):
    entity_type: str
    attributes: dict[str, Any]


class EntityUpdate(BaseModel):
    attributes: dict[str, Any]


class RelationshipCreate(BaseModel):
    type: str
    source_id: str
    target_id: str
    confidence_score: int = Field(default=50, ge=0, le=100)
    trust_weight: int = Field(default=50, ge=0, le=100)


class AuthRegister(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)
    role: str = Field(default="user", pattern=r"^(user|analyst|reviewer|admin)$")


class AuthLogin(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AuthRefresh(BaseModel):
    access_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class TaskEnqueueResponse(BaseModel):
    task_id: str
    task_type: str
    status: str


# ---------------------------------------------------------------------------
# 2FA Models
# ---------------------------------------------------------------------------


class Auth2FAEnable(BaseModel):
    issuer: str = "IntelGraph"


class Auth2FALogin(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class Auth2FAVerify(BaseModel):
    temp_token: str
    code: str


# ---------------------------------------------------------------------------
# OAuth2 Models
# ---------------------------------------------------------------------------


class OAuthClientRegister(BaseModel):
    client_id: str = Field(min_length=3, max_length=128)
    client_secret: str = Field(min_length=16, max_length=256)
    tenant_id: str = ""
    scopes: list[str] = ["read"]


class OAuthTokenRequest(BaseModel):
    grant_type: str = Field(
        default="client_credentials", pattern=r"^(client_credentials|refresh_token)$"
    )
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    scope: str = ""


class OAuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    expires_in: int = 900
    scope: str = ""
