from __future__ import annotations

import json
import time
from typing import Any

from intelgraph.core.source.connector import ConnectorConfig, ConnectorRegistry
from intelgraph.core.source.store import DataSourceStore


class DataSourceManager:
    def __init__(self, db_path: str):
        self.store = DataSourceStore(db_path)
        self.store.connect()

    def register_connector(
        self,
        source_id: str,
        source_name: str,
        connector_type: str,
        config_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg_kwargs: dict[str, Any] = {
            "id": source_id,
            "name": source_name,
            "connector_type": connector_type,
        }
        if config_overrides:
            cfg_kwargs.update(config_overrides)
        cfg = ConnectorConfig(**cfg_kwargs)
        connector = ConnectorRegistry.create(cfg)
        if connector is None:
            return {"error": f"Unknown connector type: {connector_type}"}
        self.store.register_source(cfg)
        return cfg.to_dict()

    def list_sources(self) -> list[dict[str, Any]]:
        return self.store.list_sources()

    def get_source(self, source_id: str) -> dict[str, Any]:
        src = self.store.get_source(source_id)
        if src is None:
            return {"error": "Source not found"}
        return src

    def delete_source(self, source_id: str) -> bool:
        return self.store.delete_source(source_id)

    def _parse_src_config(self, src: dict[str, Any]) -> dict[str, Any]:
        config_str = src.get("config", "{}")
        if isinstance(config_str, str) and config_str.strip():
            try:
                return json.loads(config_str)
            except (json.JSONDecodeError, TypeError):
                pass
        if isinstance(config_str, dict):
            return config_str
        return {}

    def poll_source(self, source_id: str) -> dict[str, Any]:
        src = self.store.get_source(source_id)
        if src is None:
            return {"error": "Source not found", "status": "error"}
        enabled = bool(src.get("enabled", True))
        if not enabled:
            return {"status": "skipped", "message": "Source is disabled"}
        cfg_data = self._parse_src_config(src)
        cfg = ConnectorConfig(
            id=src["id"],
            name=src["name"],
            connector_type=src["connector_type"],
            endpoint_url=cfg_data.get("endpoint_url"),
            file_path=cfg_data.get("file_path"),
            conn_string=cfg_data.get("conn_string"),
            query=cfg_data.get("query"),
            auth_credentials=cfg_data.get("auth_credentials"),
            retry_max_attempts=src.get("retry_max_attempts", cfg_data.get("retry_max_attempts", 3)),
            retry_base_delay=cfg_data.get("retry_base_delay", 1.0),
            enabled=enabled,
        )
        connector = ConnectorRegistry.create(cfg)
        if connector is None:
            return {"status": "error", "error": "Failed to create connector"}
        connector.connect()
        start = time.perf_counter()
        result = connector.poll_with_retry()
        elapsed_ms = (time.perf_counter() - start) * 1000
        connector.disconnect()
        if result.success:
            self.store.record_poll(
                source_id,
                "success",
                duration_ms=elapsed_ms,
                nodes_ingested=result.nodes_ingested,
            )
            self.store.update_source_status(source_id, "active", consecutive_failures=0)
            return {
                "status": "success",
                "nodes_ingested": result.nodes_ingested,
                "duration_ms": elapsed_ms,
            }
        else:
            self.store.record_poll(
                source_id,
                "failure",
                duration_ms=elapsed_ms,
                error_message=result.error_message,
            )
            consecutive = (src.get("consecutive_failures", 0) or 0) + 1
            self.store.update_source_status(
                source_id,
                "error" if consecutive >= 3 else "active",
                consecutive_failures=consecutive,
            )
            return {
                "status": "error",
                "error": result.error_message or "Poll failed",
                "duration_ms": elapsed_ms,
            }

    def bulk_poll(self, source_ids: list[str]) -> list[dict[str, Any]]:
        results = []
        for sid in source_ids:
            results.append(self.poll_source(sid))
        return results

    def run_scheduled_poll(self) -> list[dict[str, Any]]:
        sources = self.store.list_sources()
        results = []
        now = time.time()
        for src in sources:
            if not src.get("enabled", True):
                continue
            interval = src.get("polling_interval_seconds", 3600)
            if interval <= 0:
                results.append(self.poll_source(src["id"]))
                continue
            last_poll = src.get("last_poll_timestamp")
            if last_poll is None:
                results.append(self.poll_source(src["id"]))
            elif now - last_poll >= interval:
                results.append(self.poll_source(src["id"]))
        return results

    def get_poll_history(self, source_id: str) -> list[dict[str, Any]]:
        return self.store.get_poll_history(source_id)

    def close(self) -> None:
        self.store.close()
