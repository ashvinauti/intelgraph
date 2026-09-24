from __future__ import annotations

import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_REQUIRED_CONFIG_KEYS: list[tuple[str, type]] = [
    ("storage.backend", str),
    ("logging.level", str),
    ("distributed.enabled", bool),
    ("api.read_auth_required", bool),
]

_ENV_VAR_MAP: dict[str, str] = {
    "INTELGRAPH_STORAGE_PATH": "storage.path",
    "INTELGRAPH_LOG_LEVEL": "logging.level",
    "INTELGRAPH_DEPLOYMENT": "deployment.profile",
    "INTELGRAPH_SECRET_KEY": "secret_key",
    "INTELGRAPH_CORS_ORIGINS": "cors.origins",
    "INTELGRAPH_DISTRIBUTED_ENABLED": "distributed.enabled",
    "INTELGRAPH_API_READ_AUTH": "api.read_auth_required",
}


class ConfigValidationError(Exception):
    pass


def validate_config(config: dict[str, Any]) -> None:
    errors: list[str] = []
    for key_path, expected_type in _REQUIRED_CONFIG_KEYS:
        val = _deep_get(config, key_path)
        if val is None:
            errors.append(f"Missing required config: {key_path}")
        elif not isinstance(val, expected_type):
            errors.append(
                f"Config {key_path} expected {expected_type.__name__}, got {type(val).__name__}"
            )
    if errors:
        msg = "; ".join(errors)
        raise ConfigValidationError(msg)
    logger.info("configuration validated", checks=len(_REQUIRED_CONFIG_KEYS))


def load_env_overrides(env_prefix: str = "INTELGRAPH_") -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for env_var, config_key in _ENV_VAR_MAP.items():
        val = os.environ.get(env_var)
        if val is not None:
            _deep_set(overrides, config_key, val)
    return overrides


def _deep_get(d: dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    for part in parts:
        if not isinstance(d, dict):
            return None
        d = d.get(part)
    return d


def _deep_set(d: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    for part in parts[:-1]:
        if part not in d:
            d[part] = {}
        d = d[part]
    d[parts[-1]] = value
