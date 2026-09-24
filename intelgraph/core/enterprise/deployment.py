from __future__ import annotations

from typing import Any

_DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "development": {
        "logging": {"level": "DEBUG"},
        "cors": {"origins": ["*"]},
        "rate_limit": {
            "max_requests": 1000,
            "window": 60,
            "health": {"max_requests": 1000, "window": 60},
            "auth": {"max_requests": 100, "window": 60},
            "read": {"max_requests": 500, "window": 60},
            "write": {"max_requests": 200, "window": 60},
        },
        "security": {
            "csp": "default-src 'self'",
            "hsts": False,
            "hsts_max_age": 0,
            "x_content_type_options": "nosniff",
            "x_frame_options": "DENY",
            "x_xss_protection": "1; mode=block",
            "cache_control": "no-store",
        },
        "alerting": {"enabled": False},
    },
    "staging": {
        "logging": {"level": "INFO"},
        "cors": {"origins": []},
        "rate_limit": {
            "max_requests": 200,
            "window": 60,
            "health": {"max_requests": 200, "window": 60},
            "auth": {"max_requests": 50, "window": 60},
            "read": {"max_requests": 200, "window": 60},
            "write": {"max_requests": 100, "window": 60},
        },
        "security": {
            "csp": "default-src 'self'",
            "hsts": True,
            "hsts_max_age": 31536000,
            "x_content_type_options": "nosniff",
            "x_frame_options": "DENY",
            "x_xss_protection": "1; mode=block",
            "cache_control": "no-store",
        },
        "alerting": {"enabled": True},
    },
    "production": {
        "logging": {"level": "WARNING"},
        "cors": {"origins": []},
        "rate_limit": {
            "max_requests": 100,
            "window": 60,
            "health": {"max_requests": 200, "window": 60},
            "auth": {"max_requests": 30, "window": 60},
            "read": {"max_requests": 100, "window": 60},
            "write": {"max_requests": 50, "window": 60},
        },
        "security": {
            "csp": "default-src 'self'",
            "hsts": True,
            "hsts_max_age": 31536000,
            "x_content_type_options": "nosniff",
            "x_frame_options": "DENY",
            "x_xss_protection": "1; mode=block",
            "cache_control": "no-store",
        },
        "alerting": {"enabled": True},
    },
}


def get_profile_config(profile: str) -> dict[str, Any]:
    return dict(_DEFAULT_PROFILES.get(profile, _DEFAULT_PROFILES["development"]))


def list_profiles() -> list[str]:
    return list(_DEFAULT_PROFILES)
