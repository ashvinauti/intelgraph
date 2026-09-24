from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from intelgraph.core.enterprise import Role, user_role
from intelgraph.core.multitenant import get_tenant_manager

_token_store: dict[str, dict[str, Any]] = {}

_SECRET_KEY: str = os.environ.get(
    "INTELGRAPH_SECRET_KEY",
    secrets.token_hex(32),
)

TOKEN_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 24


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000)
    return f"{salt}:{dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    if ":" not in stored:
        return False
    salt, expected = stored.split(":", 1)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000)
    return dk.hex() == expected


def register_user(
    username: str, password: str, role: str = "user", tenant_id: str = ""
) -> dict[str, Any]:
    uid = hashlib.sha256(username.encode()).hexdigest()[:16]
    _token_store[uid] = {
        "username": username,
        "password_hash": _hash_password(password),
        "role": role,
        "tenant_id": tenant_id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    return _issue_token(uid, tenant_id)


def login_user(username: str, password: str) -> dict[str, Any] | None:
    for uid, data in _token_store.items():
        if data["username"] == username and _verify_password(password, data["password_hash"]):
            return _issue_token(uid, data.get("tenant_id", ""))
    return None


def login_with_api_key(api_key: str) -> dict[str, Any] | None:
    tenant = get_tenant_manager().verify_api_key(api_key)
    if not tenant or not tenant.is_active:
        return None
    uid = f"tenant_{tenant.tenant_id}"
    if uid not in _token_store:
        _token_store[uid] = {
            "username": f"tenant_{tenant.name}",
            "password_hash": "",
            "role": "admin",
            "tenant_id": tenant.tenant_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
    return _issue_token(uid, tenant.tenant_id)


def _issue_token(user_id: str, tenant_id: str = "") -> dict[str, Any]:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_EXPIRY_HOURS),
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    token = jwt.encode(payload, _SECRET_KEY, algorithm=TOKEN_ALGORITHM)
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_EXPIRY_HOURS * 3600}


def validate_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.PyJWTError:
        return None


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, _SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
    except jwt.PyJWTError:
        return None


def refresh_token(token: str) -> dict[str, Any] | None:
    uid = validate_token(token)
    if uid is None:
        return None
    if uid not in _token_store:
        return None
    return _issue_token(uid, _token_store[uid].get("tenant_id", ""))


def get_user_role(user_id: str) -> Role:
    data = _token_store.get(user_id)
    return user_role(data)


def get_tenant_id(request: Any) -> str:
    tenant_id = getattr(request.state, "tenant_id", "")
    return tenant_id or ""


# ---------------------------------------------------------------------------
# OAuth2 Client Credentials
# ---------------------------------------------------------------------------

_oauth_clients: dict[str, dict[str, Any]] = {}

OAUTH_ACCESS_TOKEN_EXPIRY_SECONDS = 900  # 15 minutes
OAUTH_REFRESH_TOKEN_EXPIRY_DAYS = 7


def register_oauth_client(
    client_id: str,
    client_secret: str,
    tenant_id: str = "",
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    hashed = _hash_password(client_secret)
    _oauth_clients[client_id] = {
        "client_secret_hash": hashed,
        "tenant_id": tenant_id,
        "scopes": scopes or ["read"],
        "created_at": datetime.now(UTC).isoformat(),
        "is_active": True,
    }
    return {"client_id": client_id, "client_secret": client_secret, "tenant_id": tenant_id}


def authenticate_oauth_client(client_id: str, client_secret: str) -> dict[str, Any] | None:
    client = _oauth_clients.get(client_id)
    if not client or not client.get("is_active", False):
        return None
    if not _verify_password(client_secret, client["client_secret_hash"]):
        return None
    return _issue_oauth_token(client_id, client["tenant_id"], client.get("scopes", []))


def _issue_oauth_token(
    client_id: str,
    tenant_id: str,
    scopes: list[str],
) -> dict[str, Any]:
    now = datetime.now(UTC)
    access_payload: dict[str, Any] = {
        "sub": client_id,
        "iat": now,
        "exp": now + timedelta(seconds=OAUTH_ACCESS_TOKEN_EXPIRY_SECONDS),
        "scope": " ".join(scopes),
        "token_type": "access",
    }
    if tenant_id:
        access_payload["tenant_id"] = tenant_id

    refresh_payload: dict[str, Any] = {
        "sub": client_id,
        "iat": now,
        "exp": now + timedelta(days=OAUTH_REFRESH_TOKEN_EXPIRY_DAYS),
        "token_type": "refresh",
    }
    if tenant_id:
        refresh_payload["tenant_id"] = tenant_id

    access_token = jwt.encode(access_payload, _SECRET_KEY, algorithm=TOKEN_ALGORITHM)
    refresh_token_str = jwt.encode(refresh_payload, _SECRET_KEY, algorithm=TOKEN_ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_str,
        "token_type": "bearer",
        "expires_in": OAUTH_ACCESS_TOKEN_EXPIRY_SECONDS,
        "scope": " ".join(scopes),
    }


def refresh_oauth_token(refresh_token_str: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(refresh_token_str, _SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("token_type") != "refresh":
        return None
    client_id = payload.get("sub", "")
    client = _oauth_clients.get(client_id)
    if not client or not client.get("is_active", False):
        return None
    return _issue_oauth_token(client_id, payload.get("tenant_id", ""), client.get("scopes", []))


# ---------------------------------------------------------------------------
# 2FA Integration
# ---------------------------------------------------------------------------

from intelgraph.core.auth.totp import TOTPManager

_totp_manager: TOTPManager | None = None


def get_totp_manager() -> TOTPManager:
    global _totp_manager
    if _totp_manager is None:
        _totp_manager = TOTPManager()
    return _totp_manager


def login_with_2fa_step1(username: str, password: str) -> dict[str, Any] | None:
    """First step of 2FA login: validate password, return '2fa_required' if 2FA enabled."""
    for uid, data in _token_store.items():
        if data["username"] == username and _verify_password(password, data["password_hash"]):
            totp_manager = get_totp_manager()
            if totp_manager.is_enabled(uid):
                # Generate a short-lived temp token for 2FA verification
                now = datetime.now(UTC)
                temp_payload: dict[str, Any] = {
                    "sub": uid,
                    "iat": now,
                    "exp": now + timedelta(minutes=5),
                    "purpose": "2fa_verification",
                }
                temp_token = jwt.encode(temp_payload, _SECRET_KEY, algorithm=TOKEN_ALGORITHM)
                return {"status": "2fa_required", "temp_token": temp_token}
            # No 2FA — issue token directly
            return _issue_token(uid, data.get("tenant_id", ""))
    return None


def verify_2fa_code(temp_token: str, code: str) -> dict[str, Any] | None:
    """Second step of 2FA login: verify TOTP code with temp token."""
    try:
        payload = jwt.decode(temp_token, _SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != "2fa_verification":
        return None
    uid = payload.get("sub", "")
    data = _token_store.get(uid)
    if not data:
        return None
    totp_manager = get_totp_manager()
    if not totp_manager.verify(uid, code):
        return None
    return _issue_token(uid, data.get("tenant_id", ""))
