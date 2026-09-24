from __future__ import annotations

from typing import Any

from intelgraph.core.evidence_chain import ChainManager
from intelgraph.core.orchestrator import TaskManager
from intelgraph.core.source_registry import SourceRegistryService
from intelgraph.core.storage import SQLiteBackend
from intelgraph.core.storage.audit import AuditLogger
from intelgraph.core.storage.backend import StorageBackend
from intelgraph.core.verification.manager import VerificationManager


def _create_backend(config: dict[str, Any]) -> StorageBackend:
    storage_cfg = config.get("storage", {})
    backend_name = storage_cfg.get("backend", "sqlite")
    if backend_name == "postgres":
        from intelgraph.core.storage.postgres_backend import PostgresBackend

        backend = PostgresBackend(
            host=storage_cfg.get("host", "localhost"),
            port=int(storage_cfg.get("port", 5432)),
            dbname=storage_cfg.get("dbname", "intelgraph"),
            user=storage_cfg.get("user", "intelgraph"),
            password=storage_cfg.get("password", ""),
            pool_size=int(storage_cfg.get("pool_size", 5)),
        )
    else:
        db_path = storage_cfg.get("path", "intelgraph.db")
        backend = SQLiteBackend(db_path)
    backend.connect()
    backend.initialize_schema()
    return backend


class ServiceContainer:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._backend = _create_backend(config)
        self._vm: VerificationManager | None = None
        self._cm: ChainManager | None = None
        self._sr: SourceRegistryService | None = None
        self._tm: TaskManager | None = None
        self._audit: AuditLogger | None = None

    @property
    def backend(self) -> StorageBackend:
        return self._backend

    @property
    def verification(self) -> VerificationManager:
        if self._vm is None:
            self._vm = VerificationManager(self._backend)
            self._vm.initialize()
        return self._vm

    @property
    def chain(self) -> ChainManager:
        if self._cm is None:
            self._cm = ChainManager(self._backend)
            self._cm.initialize()
        return self._cm

    @property
    def source_registry(self) -> SourceRegistryService:
        if self._sr is None:
            self._sr = SourceRegistryService(self._backend)
        return self._sr

    @property
    def task_manager(self) -> TaskManager:
        if self._tm is None:
            self._tm = TaskManager(config=self._config)
            self._tm.initialize()
        return self._tm

    @property
    def audit(self) -> AuditLogger:
        if self._audit is None:
            self._audit = AuditLogger(self._backend)
        return self._audit
