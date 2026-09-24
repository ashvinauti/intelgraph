from __future__ import annotations

import csv
import json
import random
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from intelgraph.core.enterprise.observability import get_metrics


@dataclass
class PollResult:
    success: bool
    nodes_ingested: int = 0
    edges_ingested: int = 0
    duplicates_removed: int = 0
    entities_merged: int = 0
    error_message: str = ""
    duration_ms: float = 0.0
    raw_data: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "nodes_ingested": self.nodes_ingested,
            "edges_ingested": self.edges_ingested,
            "duplicates_removed": self.duplicates_removed,
            "entities_merged": self.entities_merged,
            "error_message": self.error_message,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class ConnectorConfig:
    id: str
    name: str
    connector_type: str
    polling_interval_seconds: int = 3600
    retry_max_attempts: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    enabled: bool = True
    auth_type: str | None = None
    auth_credentials: dict[str, str] | None = None
    endpoint_url: str | None = None
    file_path: str | None = None
    conn_string: str | None = None
    query: str | None = None
    headers: dict[str, str] | None = None
    feed_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        creds = dict(self.auth_credentials) if self.auth_credentials else None
        if creds:
            for key in creds:
                if key.lower() in ("password", "secret", "token", "api_key"):
                    creds[key] = "***MASKED***"
        return {
            "id": self.id,
            "name": self.name,
            "connector_type": self.connector_type,
            "polling_interval_seconds": self.polling_interval_seconds,
            "retry_max_attempts": self.retry_max_attempts,
            "enabled": self.enabled,
            "auth_type": self.auth_type,
            "auth_credentials": creds,
            "endpoint_url": self.endpoint_url,
            "file_path": self.file_path,
            "query": self.query,
            "feed_schema": self.feed_schema,
            "metadata": self.metadata,
        }


def _backoff_delay(attempt: int, base: float, max_delay: float) -> float:
    delay = base * (2**attempt) + random.uniform(0, 0.1)
    return min(delay, max_delay)


class Connector(ABC):
    def __init__(self, config: ConnectorConfig) -> None:
        self._config = config
        self._connected = False
        self._metrics = get_metrics()

    @property
    def config(self) -> ConnectorConfig:
        return self._config

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _record_metrics(self, name: str, duration: float, success: bool) -> None:
        self._metrics.set_gauge(f"source_{name}_duration_ms", duration * 1000)
        self._metrics.set_gauge(f"source_{name}_success", 1.0 if success else 0.0)

    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def poll(self) -> PollResult: ...

    def disconnect(self) -> None:
        self._connected = False

    def health_check(self) -> bool:
        return self._connected

    def poll_with_retry(self) -> PollResult:
        last_error = ""
        for attempt in range(self._config.retry_max_attempts):
            try:
                t0 = time.perf_counter()
                result = self.poll()
                duration = time.perf_counter() - t0
                result.duration_ms = duration * 1000
                self._record_metrics(self._config.connector_type, duration, result.success)
                if result.success:
                    return result
                last_error = result.error_message
            except Exception as exc:
                last_error = str(exc)
                self._record_metrics(self._config.connector_type + "_error", 0, False)
            if attempt < self._config.retry_max_attempts - 1:
                delay = _backoff_delay(
                    attempt, self._config.retry_base_delay, self._config.retry_max_delay
                )
                time.sleep(delay)
        return PollResult(success=False, error_message=f"All retries exhausted: {last_error}")

    def validate_data(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        schema = self._config.feed_schema
        if not schema:
            return data
        required = set(schema.get("required_fields", []))
        validated: list[dict[str, Any]] = []
        for item in data:
            item_lower = {k.lower(): v for k, v in item.items()}
            if required and not required.issubset(item_lower.keys()):
                continue
            validated.append(item_lower)
        return validated


class HttpConnector(Connector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._session = None

    def connect(self) -> bool:
        if not self._config.endpoint_url:
            return False
        self._connected = True
        return True

    def poll(self) -> PollResult:
        endpoint = self._config.endpoint_url or ""
        try:
            import urllib.request

            req = urllib.request.Request(endpoint)
            if self._config.headers:
                for k, v in self._config.headers.items():
                    req.add_header(k, v)
            if self._config.auth_type == "api_key" and self._config.auth_credentials:
                key = self._config.auth_credentials.get("api_key", "")
                req.add_header("Authorization", f"Bearer {key}")
            resp = urllib.request.urlopen(req, timeout=30)
            body = resp.read().decode("utf-8")
            raw: list[dict[str, Any]] = json.loads(body)
            if isinstance(raw, dict):
                raw = [raw]
            validated = self.validate_data(raw)
            return PollResult(success=True, raw_data=validated, nodes_ingested=len(validated))
        except Exception as exc:
            return PollResult(success=False, error_message=str(exc))

    def health_check(self) -> bool:
        if not self._config.endpoint_url:
            return False
        try:
            import urllib.request

            req = urllib.request.Request(self._config.endpoint_url)
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.status == 200
        except Exception:
            return False


class FileConnector(Connector):
    def connect(self) -> bool:
        if not self._config.file_path:
            return False
        self._connected = True
        return True

    def poll(self) -> PollResult:
        path = self._config.file_path or ""
        try:
            entries: list[dict[str, Any]] = []
            if path.endswith(".json"):
                with open(path) as f:
                    data = json.load(f)
                    entries = data if isinstance(data, list) else [data]
            elif path.endswith(".csv"):
                with open(path) as f:
                    reader = csv.DictReader(f)
                    entries = list(reader)
            else:
                with open(path) as f:
                    content = f.read()
                    try:
                        data = json.loads(content)
                        entries = data if isinstance(data, list) else [data]
                    except json.JSONDecodeError:
                        entries = [{"content": content}]
            validated = self.validate_data(entries)
            return PollResult(success=True, raw_data=validated, nodes_ingested=len(validated))
        except Exception as exc:
            return PollResult(success=False, error_message=str(exc))

    def health_check(self) -> bool:
        import os

        return bool(self._config.file_path and os.path.isfile(self._config.file_path))


class DatabaseConnector(Connector):
    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._db_conn: sqlite3.Connection | None = None

    def connect(self) -> bool:
        if not self._config.conn_string:
            return False
        try:
            self._db_conn = sqlite3.connect(self._config.conn_string)
            self._db_conn.row_factory = sqlite3.Row
            self._connected = True
            return True
        except Exception:
            return False

    def poll(self) -> PollResult:
        if not self._connected or not self._db_conn:
            return PollResult(success=False, error_message="Not connected")
        try:
            cursor = self._db_conn.execute(self._config.query or "SELECT * FROM entities")
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            entries = [dict(zip(columns, row, strict=False)) for row in rows]
            validated = self.validate_data(entries)
            return PollResult(success=True, raw_data=validated, nodes_ingested=len(validated))
        except Exception as exc:
            return PollResult(success=False, error_message=str(exc))

    def disconnect(self) -> None:
        if self._db_conn:
            self._db_conn.close()
            self._db_conn = None
        self._connected = False

    def health_check(self) -> bool:
        if not self._db_conn:
            return False
        try:
            self._db_conn.execute("SELECT 1")
            return True
        except Exception:
            return False


_connector_types: dict[str, type[Connector]] = {}


class ConnectorRegistry:
    @staticmethod
    def register(name: str, cls: type[Connector]) -> None:
        _connector_types[name] = cls

    @staticmethod
    def get(name: str) -> type[Connector] | None:
        return _connector_types.get(name)

    @staticmethod
    def list_types() -> list[str]:
        return list(_connector_types.keys())

    @staticmethod
    def create(config: ConnectorConfig) -> Connector | None:
        cls = _connector_types.get(config.connector_type)
        if cls is None:
            return None
        return cls(config)


ConnectorRegistry.register("http", HttpConnector)
ConnectorRegistry.register("file", FileConnector)
ConnectorRegistry.register("database", DatabaseConnector)
