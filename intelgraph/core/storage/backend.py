from abc import ABC, abstractmethod
from typing import Any

from intelgraph.core.entity import BaseEntity
from intelgraph.core.evidence import Evidence, Provenance
from intelgraph.core.relationship import Relationship


class StorageBackend(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def initialize_schema(self) -> None: ...

    @abstractmethod
    def migrate(self, target_version: int | None = None) -> None: ...

    @abstractmethod
    def schema_version(self) -> int: ...

    # Entity CRUD
    @abstractmethod
    def put_entity(self, entity: BaseEntity, operation: str = "CREATE") -> None: ...

    @abstractmethod
    def get_entity(self, entity_id: str) -> BaseEntity | None: ...

    @abstractmethod
    def get_entity_version(self, entity_id: str, version: int) -> BaseEntity | None: ...

    @abstractmethod
    def delete_entity(self, entity_id: str) -> None: ...

    @abstractmethod
    def list_entities(self, entity_type: str | None = None) -> list[BaseEntity]: ...

    @abstractmethod
    def list_entity_versions(self, entity_id: str) -> list[dict[str, Any]]: ...

    # Relationship CRUD
    @abstractmethod
    def put_relationship(self, relationship: Relationship, operation: str = "CREATE") -> None: ...

    @abstractmethod
    def get_relationship(self, relationship_id: str) -> Relationship | None: ...

    @abstractmethod
    def delete_relationship(self, relationship_id: str) -> None: ...

    @abstractmethod
    def list_relationships(
        self, source_id: str | None = None, target_id: str | None = None
    ) -> list[Relationship]: ...

    # Provenance
    @abstractmethod
    def store_provenance(self, entity_id: str, provenance: Provenance) -> None: ...

    @abstractmethod
    def get_provenance(self, entity_id: str) -> list[Provenance]: ...

    # Collection evidence
    @abstractmethod
    def store_collection_evidence(
        self, evidence: Evidence, entity_id: str | None = None
    ) -> None: ...

    @abstractmethod
    def get_collection_evidence(self, entity_id: str) -> list[Evidence]: ...

    # Source registry
    @abstractmethod
    def register_source(self, source: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_source(self, source_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list_sources(self) -> list[dict[str, Any]]: ...

    # Canonical map
    @abstractmethod
    def put_canonical_map(self, canonical: dict[str, Any]) -> None: ...

    @abstractmethod
    def get_canonical_map(self, entity_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list_canonical_maps(self) -> list[dict[str, Any]]: ...

    # Snapshots
    @abstractmethod
    def create_snapshot(
        self,
        snapshot_id: str,
        label: str,
        data: dict[str, Any],
        entity_count: int,
        relationship_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str: ...

    @abstractmethod
    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def list_snapshots(self) -> list[dict[str, Any]]: ...

    # Audit
    @abstractmethod
    def write_audit(self, entry: dict[str, Any]) -> None: ...

    @abstractmethod
    def query_audit(
        self, entity_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    # Cache (low-level, called by CacheManager)
    @abstractmethod
    def cache_get(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def cache_set(self, key: str, value: str, expires_at: str | None) -> None: ...

    @abstractmethod
    def cache_delete(self, key: str) -> None: ...

    @abstractmethod
    def cache_delete_pattern(self, pattern: str) -> None: ...

    @abstractmethod
    def cache_clear(self) -> None: ...
