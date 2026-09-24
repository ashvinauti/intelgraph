from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from intelgraph.core.source.connector import ConnectorRegistry
from intelgraph.core.source.manager import DataSourceManager

router = APIRouter(prefix="/data-sources", tags=["data-sources"])

_manager: DataSourceManager | None = None


def _get_manager() -> DataSourceManager:
    global _manager
    if _manager is None:
        from intelgraph.api.main import _container

        cfg = _container._config
        db_path = cfg.get("storage", {}).get("path", "intelgraph.db")
        _manager = DataSourceManager(db_path)
        _manager.store.connect()
    return _manager


@router.post("/register", summary="Register a new data source")
def register_source(body: dict[str, Any]):
    source_id = body.get("source_id")
    if not source_id:
        import uuid

        source_id = str(uuid.uuid4())
    source_name = body.get("name", body.get("source_name", "unnamed"))
    connector_type = body.get("connector_type", body.get("type", ""))
    overrides: dict[str, Any] = {}
    key_map = {"polling_interval": "polling_interval_seconds"}
    for key in (
        "endpoint_url",
        "file_path",
        "conn_string",
        "query",
        "polling_interval",
        "polling_interval_seconds",
        "retry_max_attempts",
        "retry_base_delay",
        "auth_type",
        "auth_credentials",
        "headers",
        "feed_schema",
        "metadata",
        "enabled",
    ):
        val = body.get(key)
        if val is not None:
            mapped = key_map.get(key, key)
            overrides[mapped] = val
    manager = _get_manager()
    result = manager.register_connector(source_id, source_name, connector_type, overrides)
    if "error" in result:
        types = ", ".join(sorted(ConnectorRegistry.list_types()))
        raise HTTPException(status_code=422, detail=f"{result['error']}. Supported types: {types}.")
    src = manager.get_source(source_id)
    return src


@router.get("", summary="List all data sources")
def list_sources():
    return _get_manager().list_sources()


@router.get("/{source_id}", summary="Get a single data source")
def get_source(source_id: str):
    src = _get_manager().get_source(source_id)
    if "error" in src:
        raise HTTPException(status_code=404, detail=src["error"])
    return src


@router.delete("/{source_id}", summary="Delete a data source")
def delete_source(source_id: str):
    manager = _get_manager()
    if not manager.delete_source(source_id):
        raise HTTPException(status_code=404, detail="Data source not found")
    return {"status": "deleted", "source_id": source_id}


@router.post("/{source_id}/poll", summary="Poll a data source")
def poll_source(source_id: str):
    result = _get_manager().poll_source(source_id)
    if result.get("status") == "error" and "Source not found" in result.get("error", ""):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{source_id}/status", summary="Get data source status")
def get_status(source_id: str):
    status = _get_manager().store.get_source_status(source_id)
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    return status


@router.get("/{source_id}/poll-history", summary="Get poll history for a data source")
def get_poll_history(source_id: str, limit: int = 50):
    result = _get_manager().get_poll_history(source_id)
    if not result and _get_manager().get_source(source_id) is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    return result


@router.post("/bulk-poll", summary="Poll multiple data sources")
def bulk_poll(body: list[str]):
    return _get_manager().bulk_poll(body)
