from __future__ import annotations

import json
import logging
import sys

import click

from intelgraph.core.enterprise import get_metrics
from intelgraph.core.operations.backup import BackupManager

logger = logging.getLogger(__name__)


@click.group(name="ops", help="Operations commands: health, metrics, backup, rotate-logs")
def ops_group() -> None:
    pass


@ops_group.command(name="health", help="Report system health status")
@click.pass_obj
def ops_health(obj: dict) -> None:
    cfg = obj.get("config", {})
    metrics = get_metrics().snapshot()
    import structlog

    log = structlog.get_logger(__name__)
    storage_backend = cfg.get("storage", {}).get("backend", "sqlite")
    db_path = cfg.get("storage", {}).get("path", "intelgraph.db")

    result = {
        "status": "ok",
        "version": __import__("intelgraph").__version__,
        "storage_backend": storage_backend,
        "db_path": db_path,
        "metrics": {
            "total_requests": metrics.get("total_requests", 0),
            "total_errors": metrics.get("total_errors", 0),
            "avg_duration_ms": metrics.get("avg_duration_ms", 0.0),
        },
    }
    click.echo(json.dumps(result, indent=2))
    log.info("ops health", status="ok", storage=storage_backend)


@ops_group.command(name="metrics", help="Export current metrics as JSON")
@click.pass_obj
def ops_metrics(obj: dict) -> None:
    metrics = get_metrics().snapshot()
    click.echo(json.dumps(metrics, indent=2, default=str))


@ops_group.command(name="backup", help="Create a database backup")
@click.option("--label", default="", help="Optional backup label")
@click.pass_obj
def ops_backup(obj: dict, label: str) -> None:
    cfg = obj.get("config", {})
    bm = BackupManager(cfg)
    result = bm.create_backup(label=label)
    output = BackupManager.metadata(result)
    click.echo(json.dumps(output, indent=2))
    if not result.success:
        logger.error("backup failed: %s", result.error)
        sys.exit(1)
    logger.info("backup created", path=result.path, size=result.size_bytes)


@ops_group.command(name="rotate-logs", help="Trigger log rotation")
@click.pass_obj
def ops_rotate_logs(obj: dict) -> None:
    import logging.handlers

    rotated = 0
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.doRollover()
            rotated += 1
    for name in logging.root.manager.loggerDict:
        logger_obj = logging.getLogger(name)
        for handler in logger_obj.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.doRollover()
                rotated += 1
    result = {"status": "ok", "rotated_handlers": rotated}
    click.echo(json.dumps(result, indent=2))
    if rotated == 0:
        logger.warning("no RotatingFileHandler found, nothing to rotate")
    else:
        logger.info("log rotation complete", handlers=rotated)
