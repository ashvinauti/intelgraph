from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from intelgraph.api.auth import decode_token, get_user_role, validate_token
from intelgraph.api.errors import _error_body
from intelgraph.core.enterprise.authz import Role, has_permission

_METHOD_PERMISSION_MAP: dict[str, dict[str, str]] = {
    "POST": {
        "/entities": "entity:create",
        "/relationships": "relationship:create",
        "/tasks/collect_entity": "task:create",
        "/tasks/verify_entity": "task:create",
        "/tasks/generate_report": "task:create",
        "/tenants": "tenant:admin",
    },
    "DELETE": {
        "/tenants": "tenant:admin",
    },
}

_DYNAMIC_WRITE_PREFIXES: list[tuple[str, str, str]] = [
    ("PUT", "/entities/", "entity:update"),
    ("DELETE", "/entities/", "entity:delete"),
    ("DELETE", "/relationships/", "relationship:delete"),
    ("GET", "/tenants/", "tenant:admin"),
]

_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/health",
    "/auth",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/web/dashboard.html",
    "/web/",
    "/static/",
    "/tenants/login",
    "/dashboard/",
    "/metrics/",
    "/export/",
    "/reports/",
    "/search",
    "/notifications/",
)


def _resolve_permission(method: str, path: str) -> str | None:
    exact = _METHOD_PERMISSION_MAP.get(method, {}).get(path)
    if exact:
        return exact
    for meth, prefix, perm in _DYNAMIC_WRITE_PREFIXES:
        if method == meth and path.startswith(prefix) and len(path) > len(prefix):
            return perm
    return None


def _extract_tenant_id_from_path(path: str) -> str:
    """Extract tenant_id from /tenants/{tenant_id}/... paths."""
    parts = path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "tenants" and parts[1].startswith("tnt_"):
        return parts[1]
    return ""


def create_authz_middleware(config: dict[str, Any]) -> Any:
    read_auth_required = config.get("api", {}).get("read_auth_required", False)
    multi_tenant_enabled = config.get("multitenant", {}).get("enabled", True)

    async def authz_middleware(request: Request, call_next: Any) -> Any:
        path = request.url.path

        if path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)

        method = request.method
        auth = request.headers.get("Authorization", "")
        token_str = auth[7:] if auth.startswith("Bearer ") else ""
        api_key_header = request.headers.get("X-API-Key", "")

        # Resolve tenant from token or API key
        token_tenant_id = ""
        uid = None
        if token_str:
            payload = decode_token(token_str)
            if payload:
                token_tenant_id = payload.get("tenant_id", "")
                uid = payload.get("sub")
            else:
                uid = validate_token(token_str)
        elif api_key_header:
            # Direct API key authentication (no JWT exchange required).
            # Resolves the tenant and treats the request as if the tenant
            # user had authenticated. The role defaults to "admin" for
            # tenant-scoped API keys, matching the login_with_api_key flow.
            try:
                from intelgraph.core.multitenant.manager import get_tenant_manager

                tenant = get_tenant_manager().verify_api_key(api_key_header)
            except Exception:
                tenant = None
            if tenant and tenant.is_active:
                token_tenant_id = tenant.tenant_id
                uid = f"tenant_{tenant.tenant_id}"

        # Store tenant context on request state
        request.state.tenant_id = token_tenant_id

        # Tenant-scoped access control: if the path targets a specific tenant,
        # the token must belong to that tenant (or be a super-admin without tenant_id)
        target_tenant = _extract_tenant_id_from_path(path) if multi_tenant_enabled else ""
        if target_tenant and token_tenant_id and token_tenant_id != target_tenant:
            return JSONResponse(
                status_code=403,
                content=_error_body("FORBIDDEN", "Tenant access denied"),
            )

        # Permission check for write operations
        perm = _resolve_permission(method, path)
        if perm is not None:
            if not token_str:
                return JSONResponse(
                    status_code=401,
                    content=_error_body("AUTH_REQUIRED", "Authentication required"),
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if uid is None:
                return JSONResponse(
                    status_code=401,
                    content=_error_body("AUTH_EXPIRED", "Token expired or invalid"),
                    headers={"WWW-Authenticate": "Bearer"},
                )
            role = get_user_role(uid)
            if not has_permission(role, perm):
                return JSONResponse(
                    status_code=403,
                    content=_error_body("FORBIDDEN", f"Permission '{perm}' required"),
                )
            request.state.user_id = uid
            request.state.user_role = role.value if isinstance(role, Role) else role
        elif method in ("POST", "PUT", "DELETE"):
            if not token_str:
                return JSONResponse(
                    status_code=401,
                    content=_error_body("AUTH_REQUIRED", "Authentication required"),
                    headers={"WWW-Authenticate": "Bearer"},
                )
        elif read_auth_required and method == "GET":
            if token_str:
                validated = validate_token(token_str)
                if validated is not None:
                    request.state.user_id = validated

        return await call_next(request)

    return authz_middleware
