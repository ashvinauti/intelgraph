from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import structlog


def setup_logging(
    verbose: bool = False,
    correlation_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> None:
    cfg = config or {}
    log_cfg = cfg.get("logging", {})

    if verbose:
        level = logging.DEBUG
    else:
        level_name = log_cfg.get("level", "INFO")
        level = getattr(logging, level_name.upper(), logging.INFO)

    dev_mode = cfg.get("deployment", {}).get("profile", "development") == "development"

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer() if dev_mode else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handlers: list[logging.Handler] = []

    stream = logging.StreamHandler(sys.stderr)
    stream.setLevel(level)
    handlers.append(stream)

    log_file = log_cfg.get("file", "")
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        rotation_cfg = log_cfg.get("rotation", {})
        max_bytes = rotation_cfg.get("max_bytes", 10485760)
        backup_count = rotation_cfg.get("backup_count", 5)
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(level)
        handlers.append(file_handler)

    logging.basicConfig(
        format="%(message)s",
        handlers=handlers,
        level=level,
    )

    if correlation_id:
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
