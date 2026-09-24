from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from intelgraph.core.source.connector import ConnectorConfig

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS data_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    config TEXT NOT NULL,
    polling_interval_seconds INTEGER NOT NULL DEFAULT 3600,
    retry_max_attempts INTEGER NOT NULL DEFAULT 3,
    auth_type TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_poll_at TEXT,
    last_poll_status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS poll_history (
    id TEXT PRIMARY KEY,
    data_source_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    nodes_ingested INTEGER NOT NULL DEFAULT 0,
    edges_ingested INTEGER NOT NULL DEFAULT 0,
    entities_merged INTEGER NOT NULL DEFAULT 0,
    duplicates_removed INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    FOREIGN KEY (data_source_id) REFERENCES data_sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feed_schemas (
    id TEXT PRIMARY KEY,
    data_source_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    schema_definition TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (data_source_id) REFERENCES data_sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entity_resolutions (
    id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    data_source_id TEXT,
    merge_strategy TEXT NOT NULL DEFAULT 'priority',
    merged_fields TEXT,
    confidence_score REAL NOT NULL DEFAULT 0.0,
    resolved_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_poll_history_source ON poll_history(data_source_id);
CREATE INDEX IF NOT EXISTS idx_poll_history_status ON poll_history(status);
CREATE INDEX IF NOT EXISTS idx_feed_schemas_source ON feed_schemas(data_source_id);
CREATE INDEX IF NOT EXISTS idx_entity_resolutions_source ON entity_resolutions(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_resolutions_target ON entity_resolutions(target_entity_id);
"""


class DataSourceStore:
    def __init__(self, db_path: str = "intelgraph.db") -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        path = Path(self._db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._initialize_tables()

    def _initialize_tables(self) -> None:
        if self._conn:
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.commit()

    def _require(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("DataSourceStore not connected")
        return self._conn

    def register_source(self, config: ConnectorConfig) -> dict[str, Any]:
        conn = self._require()
        now = datetime.now(UTC).isoformat()
        config_dict = config.to_dict()
        with self._lock:
            conn.execute(
                """INSERT INTO data_sources
                   (id, name, connector_type, config, polling_interval_seconds,
                    retry_max_attempts, auth_type, enabled, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    config.id,
                    config.name,
                    config.connector_type,
                    json.dumps(config_dict),
                    config.polling_interval_seconds,
                    config.retry_max_attempts,
                    config.auth_type or "",
                    1 if config.enabled else 0,
                    "active",
                    now,
                    now,
                ),
            )
            conn.commit()
        return config_dict

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        conn = self._require()
        row = conn.execute(
            "SELECT * FROM data_sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_sources(self) -> list[dict[str, Any]]:
        conn = self._require()
        rows = conn.execute(
            "SELECT * FROM data_sources ORDER BY created_at DESC",
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_source(self, source_id: str) -> bool:
        conn = self._require()
        with self._lock:
            cur = conn.execute("DELETE FROM data_sources WHERE id = ?", (source_id,))
            conn.commit()
        return cur.rowcount > 0

    def update_source_status(
        self,
        source_id: str,
        status: str,
        consecutive_failures: int | None = None,
    ) -> None:
        conn = self._require()
        now = datetime.now(UTC).isoformat()
        with self._lock:
            if consecutive_failures is not None:
                conn.execute(
                    "UPDATE data_sources SET status = ?, consecutive_failures = ?, updated_at = ? WHERE id = ?",
                    (status, consecutive_failures, now, source_id),
                )
            else:
                conn.execute(
                    "UPDATE data_sources SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, source_id),
                )
            conn.commit()

    def record_poll(
        self,
        data_source_id: str,
        status: str,
        duration_ms: float = 0.0,
        nodes_ingested: int = 0,
        edges_ingested: int = 0,
        entities_merged: int = 0,
        duplicates_removed: int = 0,
        error_message: str = "",
    ) -> dict[str, Any]:
        conn = self._require()
        now = datetime.now(UTC).isoformat()
        poll_id = str(uuid.uuid4())
        with self._lock:
            conn.execute(
                """INSERT INTO poll_history
                   (id, data_source_id, status, started_at, completed_at, duration_ms,
                    nodes_ingested, edges_ingested, entities_merged, duplicates_removed, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    poll_id,
                    data_source_id,
                    status,
                    now,
                    now,
                    int(duration_ms),
                    nodes_ingested,
                    edges_ingested,
                    entities_merged,
                    duplicates_removed,
                    error_message,
                ),
            )
            conn.execute(
                "UPDATE data_sources SET last_poll_at = ?, last_poll_status = ?, updated_at = ? WHERE id = ?",
                (now, status, now, data_source_id),
            )
            conn.commit()
        return {"id": poll_id, "status": status, "duration_ms": duration_ms}

    def get_poll_history(self, data_source_id: str, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._require()
        rows = conn.execute(
            "SELECT * FROM poll_history WHERE data_source_id = ? ORDER BY started_at DESC LIMIT ?",
            (data_source_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_source_status(self, source_id: str) -> dict[str, Any]:
        conn = self._require()
        source = self.get_source(source_id)
        if source is None:
            return {"error": "not_found"}
        latest_poll = conn.execute(
            "SELECT * FROM poll_history WHERE data_source_id = ? ORDER BY started_at DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        recent_failures = conn.execute(
            "SELECT COUNT(*) as cnt FROM poll_history WHERE data_source_id = ? AND status = 'failure' AND started_at > datetime('now', '-1 day')",
            (source_id,),
        ).fetchone()
        return {
            "id": source["id"],
            "name": source["name"],
            "connector_type": source["connector_type"],
            "status": source["status"],
            "enabled": bool(source["enabled"]),
            "consecutive_failures": source["consecutive_failures"],
            "last_poll_at": source["last_poll_at"],
            "last_poll_status": source["last_poll_status"],
            "latest_poll": dict(latest_poll) if latest_poll else None,
            "failures_last_24h": dict(recent_failures)["cnt"] if recent_failures else 0,
        }

    def save_feed_schema(
        self, data_source_id: str, schema: dict[str, Any], version: int = 1
    ) -> dict[str, Any]:
        conn = self._require()
        now = datetime.now(UTC).isoformat()
        schema_id = str(uuid.uuid4())
        with self._lock:
            conn.execute(
                "INSERT INTO feed_schemas (id, data_source_id, version, schema_definition, created_at) VALUES (?, ?, ?, ?, ?)",
                (schema_id, data_source_id, version, json.dumps(schema), now),
            )
            conn.commit()
        return {"id": schema_id, "version": version}

    def get_feed_schemas(self, data_source_id: str) -> list[dict[str, Any]]:
        conn = self._require()
        rows = conn.execute(
            "SELECT * FROM feed_schemas WHERE data_source_id = ? ORDER BY version DESC",
            (data_source_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["schema_definition"] = json.loads(d["schema_definition"])
            result.append(d)
        return result

    def record_resolution(
        self,
        source_entity_id: str,
        target_entity_id: str,
        data_source_id: str | None,
        merge_strategy: str,
        merged_fields: dict[str, Any] | None,
        confidence: float = 0.0,
    ) -> str:
        conn = self._require()
        now = datetime.now(UTC).isoformat()
        res_id = str(uuid.uuid4())
        with self._lock:
            conn.execute(
                """INSERT INTO entity_resolutions
                   (id, source_entity_id, target_entity_id, data_source_id, merge_strategy, merged_fields, confidence_score, resolved_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    res_id,
                    source_entity_id,
                    target_entity_id,
                    data_source_id,
                    merge_strategy,
                    json.dumps(merged_fields or {}),
                    confidence,
                    now,
                ),
            )
            conn.commit()
        return res_id

    def get_resolution_history(
        self,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = self._require()
        if entity_id:
            rows = conn.execute(
                """SELECT * FROM entity_resolutions
                   WHERE source_entity_id = ? OR target_entity_id = ?
                   ORDER BY resolved_at DESC LIMIT ?""",
                (entity_id, entity_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entity_resolutions ORDER BY resolved_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["merged_fields"] = json.loads(d["merged_fields"]) if d.get("merged_fields") else {}
            result.append(d)
        return result

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
