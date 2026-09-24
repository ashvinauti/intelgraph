from __future__ import annotations

import copy
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from intelgraph import __version__
from intelgraph.api.authz_middleware import create_authz_middleware
from intelgraph.api.dependencies import ServiceContainer
from intelgraph.api.errors import (
    AppError,
    app_error_handler,
    generic_error_handler,
    validation_error_handler,
)
from intelgraph.api.graphql_schema import graphql_router
from intelgraph.api.rate_limit import setup_rate_limiting
from intelgraph.api.routers import (
    agent as agent_router,
)
from intelgraph.api.routers import (
    auth_2fa as auth_2fa_router,
)
from intelgraph.api.routers import (
    auth_router,
    cognitive,
    datasources,
    entities,
    evidence,
    graph_algorithms,
    graph_analytics,
    graph_anomaly,
    graph_attack_path,
    graph_export,
    graph_influence,
    graph_nlp,
    graph_prediction,
    graph_reasoning,
    health,
    query,
    relationships,
    search,
    sources,
    tasks,
    verification,
)
from intelgraph.api.routers import (
    investigations as investigations_router,
)
from intelgraph.api.routers import (
    enrichment as enrichment_router,
)
from intelgraph.api.routers import (
    dashboard as dashboard_router,
)
from intelgraph.api.routers import (
    export_graph as export_graph_router,
)
from intelgraph.api.routers import (
    me as me_router,
)
from intelgraph.api.routers import (
    metaintel as metaintel_router,
)
from intelgraph.api.routers import (
    metrics as metrics_router,
)
from intelgraph.api.routers import (
    monitoring as monitoring_router,
)
from intelgraph.api.routers import (
    notifications as notifications_router,
)
from intelgraph.api.routers import (
    oauth as oauth_router,
)
from intelgraph.api.routers import (
    playbooks as playbooks_router,
)
from intelgraph.api.routers import (
    reports as reports_router,
)
from intelgraph.api.routers import (
    taxii as taxii_router,
)
from intelgraph.api.routers import (
    tenants as tenants_router,
)
from intelgraph.api.routers import (
    ucos as ucos_router,
)
from intelgraph.core.enterprise import (
    get_metrics,
    get_profile_config,
    load_env_overrides,
    validate_config,
)

_container: ServiceContainer = None  # type: ignore[assignment]


def create_app(config: dict[str, Any] | None = None) -> FastAPI:
    global _container

    from intelgraph.core.config import DEFAULT_CONFIG

    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if config:
        _deep_merge(cfg, config)
    env_overrides = load_env_overrides()
    for key, val in env_overrides.items():
        cfg[key] = val

    profile = cfg.get("deployment", {}).get("profile", "development")
    profile_cfg = get_profile_config(profile)
    _deep_merge(cfg, profile_cfg)

    from intelgraph.core.enterprise.config_validator import ConfigValidationError

    try:
        validate_config(cfg)
    except ConfigValidationError as e:
        import structlog

        structlog.get_logger(__name__).error("configuration validation failed", error=str(e))
        raise

    _container = ServiceContainer(cfg)

    origins = cfg.get("cors", {}).get("origins", [])
    _API_TAGS = [
        {"name": "auth", "description": "User registration, login, OAuth2, and 2FA."},
        {"name": "enrichment", "description": "IOC enrichment and threat lookup for SIEM/SOAR integrations."},
        {"name": "entities", "description": "Entity CRUD operations."},
        {"name": "relationships", "description": "Relationship CRUD operations."},
        {"name": "search", "description": "Full-text search across the knowledge graph."},
        {"name": "graph", "description": "Graph algorithms, analytics, anomaly detection, attack paths."},
        {"name": "export", "description": "Export the knowledge graph as GraphML, GEXF, JSON, CSV, or STIX 2.1."},
        {"name": "investigations", "description": "Investigation workspaces with pivot analysis, timeline, and analyst notes."},
        {"name": "notifications", "description": "Webhook, email, and Slack notification channels and history."},
        {"name": "reports", "description": "Scheduled and on-demand HTML threat intelligence reports."},
        {"name": "metrics", "description": "Performance, health, and pipeline observability endpoints."},
        {"name": "dashboard", "description": "Dashboard summary and live SSE metrics stream."},
        {"name": "graphql", "description": "GraphQL API for entities, relationships, and search."},
    ]
    app = FastAPI(
        title="IntelGraph API",
        version=__version__,
        description=(
            "Open-source threat intelligence platform. IntelGraph correlates "
            "indicators across multiple sources (URLhaus, OTX, Shodan, VirusTotal) "
            "into a knowledge graph and explains every alert with an evidence chain.\n\n"
            "## Authentication\n"
            "Two authentication mechanisms are supported and can be used interchangeably:\n"
            "- **JWT bearer**: `Authorization: Bearer <jwt>` — obtain a token from `/auth/login` or `/auth/register`.\n"
            "- **API key**: `X-API-Key: <tenant-api-key>` — issue a key via the tenants API; "
            "no token exchange required, ideal for SIEM/SOAR automation.\n\n"
            "## Rate limiting\n"
            "All endpoints are rate limited per client (sliding window). Response headers "
            "`X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` carry the quota. "
            "A `429 Too Many Requests` response includes a `Retry-After` header.\n\n"
            "## Compatibility\n"
            "STIX 2.1 and TAXII 2.1 exports are produced with the `stix2` library and validated "
            "against the official STIX 2.1 schema, so the output can be ingested by MISP, OpenCTI, "
            "and any TAXII 2.1 consumer."
        ),
        docs_url=None,
        redoc_url=None,
        openapi_tags=_API_TAGS,
        contact={
            "name": "IntelGraph",
            "url": "https://github.com/ashvinauti/intelgraph",
        },
        license_info={
            "name": "MIT",
            "url": "https://github.com/ashvinauti/intelgraph/blob/main/LICENSE",
        },
    )

    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="IntelGraph API - Swagger UI",
            swagger_js_url="/static/swagger/swagger-ui-bundle.js",
            swagger_css_url="/static/swagger/swagger-ui.css",
        )

    @app.get("/redoc", include_in_schema=False)
    async def redoc():
        return get_redoc_html(
            openapi_url="/openapi.json",
            title="IntelGraph API - ReDoc",
        )

    app.include_router(entities.router)
    app.include_router(relationships.router)
    app.include_router(evidence.router)
    app.include_router(verification.router)
    app.include_router(sources.router)
    app.include_router(query.router)
    app.include_router(search.router)
    app.include_router(health.router)
    app.include_router(metrics_router.router)
    app.include_router(auth_router.router)
    app.include_router(tasks.router)
    app.include_router(graph_analytics.router)
    app.include_router(graph_export.router)
    app.include_router(graph_algorithms.router)
    app.include_router(datasources.router)
    app.include_router(graph_influence.router)
    app.include_router(graph_anomaly.router)
    app.include_router(graph_attack_path.router)
    app.include_router(graph_reasoning.router)
    app.include_router(graph_prediction.router)
    app.include_router(graph_nlp.router)
    app.include_router(cognitive.router)
    app.include_router(agent_router.router)
    app.include_router(metaintel_router.router)
    app.include_router(playbooks_router.router)
    app.include_router(taxii_router.router)
    app.include_router(monitoring_router.router)
    app.include_router(export_graph_router.router)
    app.include_router(auth_2fa_router.router)
    app.include_router(oauth_router.router)
    app.include_router(me_router.router)
    app.include_router(tenants_router.router)
    app.include_router(notifications_router.router)
    app.include_router(reports_router.router)
    app.include_router(investigations_router.router)
    app.include_router(enrichment_router.router)
    app.include_router(graphql_router, prefix="/graphql", tags=["graphql"])

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/web/dashboard.html")

    app.include_router(ucos_router.router)
    app.include_router(dashboard_router.router)

    import os as _os

    _base_dir = _os.path.dirname(_os.path.dirname(__file__))
    _web_dir = _os.path.join(_base_dir, "web")
    if _os.path.isdir(_web_dir):
        app.mount("/web", StaticFiles(directory=_web_dir, html=True), name="web")
    _static_dir = _os.path.join(_base_dir, "static")
    if _os.path.isdir(_static_dir):
        app.mount("/static", StaticFiles(directory=_static_dir), name="static")

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    app.middleware("http")(create_authz_middleware(cfg))

    setup_rate_limiting(app, cfg)

    sec = cfg.get("security", {})

    _DASHBOARD_CSP = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' https://cdn.jsdelivr.net"
    )

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next: Any) -> Any:
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        response.headers["X-Content-Type-Options"] = sec.get("x_content_type_options", "nosniff")
        response.headers["X-Frame-Options"] = sec.get("x_frame_options", "DENY")
        response.headers["X-XSS-Protection"] = sec.get("x_xss_protection", "1; mode=block")
        response.headers["Cache-Control"] = sec.get("cache_control", "no-store")
        if sec.get("hsts", True):
            max_age = sec.get("hsts_max_age", 31536000)
            response.headers["Strict-Transport-Security"] = f"max-age={max_age}; includeSubDomains"
        path = request.url.path
        if path.startswith("/web/") or path == "/":
            response.headers["Content-Security-Policy"] = _DASHBOARD_CSP
        elif path in ("/docs", "/redoc") or path.startswith("/static/"):
            csp = "default-src 'self' 'unsafe-inline' 'unsafe-eval'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'"
            response.headers["Content-Security-Policy"] = csp
        else:
            csp = sec.get("csp", "")
            if csp:
                response.headers["Content-Security-Policy"] = csp
        get_metrics().record_request(request.url.path, duration, response.status_code)
        from intelgraph.core.enterprise import get_performance_collector

        get_performance_collector().record_api_latency(request.url.path, round(duration * 1000, 2))
        return response

    return app


def _deep_merge(base: dict, overlay: dict) -> None:
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


app = create_app()
