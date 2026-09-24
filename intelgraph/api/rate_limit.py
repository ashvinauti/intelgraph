from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from intelgraph.api.errors import _error_body


class RateLimiter:
    """Sliding-window log rate limiter.

    Algorithm: sliding-window log — each request timestamp is stored.
    On every check, entries older than *window* are pruned, then the
    count of remaining entries is compared against *max_requests*.
    This prevents burst attacks at window boundaries (unlike fixed-window).
    """

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int, window: float) -> tuple[bool, float]:
        now = time.time()
        bucket = self._buckets[key]
        cutoff = now - window
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= max_requests:
            reset_after = window if not bucket else bucket[0] + window - now
            return False, max(0.0, reset_after)
        bucket.append(now)
        return True, 0.0

    def remaining(self, key: str, max_requests: int, window: float) -> int:
        now = time.time()
        bucket = self._buckets[key]
        cutoff = now - window
        bucket[:] = [t for t in bucket if t > cutoff]
        return max(0, max_requests - len(bucket))

    def reset_time(self, key: str, window: float) -> float:
        now = time.time()
        bucket = self._buckets[key]
        cutoff = now - window
        bucket[:] = [t for t in bucket if t > cutoff]
        if not bucket:
            return 0.0
        return bucket[0] + window

    def clear(self) -> None:
        self._buckets.clear()


_limiter = RateLimiter()

_CATEGORY_LIMITS: dict[str, tuple[int, float]] = {
    "health": (200, 60.0),
    "auth": (30, 60.0),
    "read": (100, 60.0),
    "write": (50, 60.0),
}

_CATEGORY_PREFIXES: dict[str, tuple[str, ...]] = {
    "health": ("/health",),
    "auth": ("/auth",),
    "read": (
        "/entities/",
        "/relationships/",
        "/sources",
        "/query",
        "/search",
        "/tasks/",
        "/graph/",
        "/enrichment/",
        "/export/",
    ),
    "write": (
        "/entities",
        "/relationships",
        "/tasks/collect_entity",
        "/tasks/verify_entity",
        "/tasks/generate_report",
    ),
}


def _get_category(path: str) -> str:
    exact_matches: list[tuple[str, str]] = []
    prefix_matches: list[tuple[str, str]] = []
    for cat, prefixes in _CATEGORY_PREFIXES.items():
        for prefix in prefixes:
            if path == prefix:
                exact_matches.append((prefix, cat))
            elif path.startswith(prefix):
                prefix_matches.append((prefix, cat))
    exact_matches.sort(key=lambda x: -len(x[0]))
    prefix_matches.sort(key=lambda x: -len(x[0]))
    for _, cat in exact_matches:
        return cat
    for _, cat in prefix_matches:
        return cat
    return "read"


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting reverse-proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        if client_ip:
            return client_ip
    return request.client.host if request.client else "unknown"


def setup_rate_limiting(app: FastAPI, config: dict | None = None) -> None:
    # Only clear during testing to avoid cross-test pollution.
    # In production this is a no-op: buckets are naturally empty on startup.
    if os.environ.get("INTELGRAPH_ENV") == "test" or os.environ.get("PYTEST_VERSION"):
        _limiter.clear()

    limits = dict(_CATEGORY_LIMITS)
    rc = (config or {}).get("rate_limit", {})
    for cat in limits:
        cat_cfg = rc.get(cat, {})
        limits[cat] = (
            cat_cfg.get("max_requests", limits[cat][0]),
            cat_cfg.get("window", limits[cat][1]),
        )

    rl_config = (config or {}).get("rate_limit", {})
    per_user_enabled = rl_config.get("per_user", True)
    per_endpoint_enabled = rl_config.get("per_endpoint", True)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Any) -> Any:
        path = request.url.path
        user_key = _get_client_ip(request) if per_user_enabled else "global"
        category = _get_category(path)
        max_r, win = limits.get(category, (100, 60.0))
        key_parts = [user_key]
        if per_endpoint_enabled:
            key_parts.append(category)
            key_parts.append(path)
        else:
            key_parts.append(category)
        endpoint_key = ":".join(key_parts)
        allowed, retry_after = _limiter.check(endpoint_key, max_requests=max_r, window=win)
        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={
                    "Retry-After": str(int(retry_after)),
                    "X-RateLimit-Limit": str(max_r),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                    "X-RateLimit-Category": category,
                },
                content=_error_body(
                    "RATE_LIMITED",
                    f"Rate limit exceeded. Try again in {int(retry_after)}s.",
                ),
            )
        response = await call_next(request)
        remaining = _limiter.remaining(endpoint_key, max_requests=max_r, window=win)
        reset_time = _limiter.reset_time(endpoint_key, window=win)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(max_r)
        response.headers["X-RateLimit-Reset"] = str(int(reset_time))
        response.headers["X-RateLimit-Category"] = category
        return response
