import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from intelgraph.core.entity import BaseEntity
from intelgraph.core.evidence import Evidence, Provenance
from intelgraph.core.relationship import Relationship
from intelgraph.core.storage.backend import StorageBackend
from intelgraph.core.storage.migration import run_migrations
from intelgraph.core.storage.models import SCHEMA_SQL
from intelgraph.core.storage.serializers import (  # noqa: F401
    _dict_to_entity,
    _dict_to_relationship,
    _entity_to_dict,
    _provenance_to_dict,
    _relationship_to_dict,
)


class SQLiteBackend(StorageBackend):
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

    def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def initialize_schema(self) -> None:
        conn = self._require()
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    def migrate(self, target_version: int | None = None) -> None:
        current = self.schema_version()
        conn = self._require()
        with self._lock:
            target = run_migrations(conn, SCHEMA_SQL, current, target_version)
            conn.execute("UPDATE schema_version SET version = ?", (target,))
            conn.commit()

    def schema_version(self) -> int:
        conn = self._require()
        try:
            row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            return row["version"] if row else 0
        except sqlite3.OperationalError:
            return 0

    # ── Entity CRUD ──

    def put_entity(self, entity: BaseEntity, operation: str = "CREATE") -> None:
        conn = self._require()
        data = _entity_to_dict(entity)
        now = datetime.now(UTC).isoformat()
        with self._lock:
            existing = self.get_entity(entity.id)
            if existing and operation != "UPDATE":
                operation = "UPDATE"
            conn.execute(
                """INSERT OR REPLACE INTO entities
                   (id, entity_type, version, data, confidence_score, trust_score, created_at, updated_at, is_latest)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    entity.id,
                    entity.entity_type.type_name,
                    entity.version,
                    json.dumps(data, default=str),
                    entity.confidence_score,
                    entity.trust_score,
                    entity.created_at.isoformat(),
                    now,
                ),
            )
            conn.execute(
                """INSERT INTO entity_versions
                   (id, version, entity_type, data, confidence_score, trust_score, created_at, updated_at, operation)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entity.id,
                    entity.version,
                    entity.entity_type.type_name,
                    json.dumps(data, default=str),
                    entity.confidence_score,
                    entity.trust_score,
                    entity.created_at.isoformat(),
                    now,
                    operation,
                ),
            )
            conn.commit()

    def get_entity(self, entity_id: str) -> BaseEntity | None:
        conn = self._require()
        row = conn.execute(
            "SELECT data, entity_type FROM entities WHERE id = ? AND is_latest = 1",
            (entity_id,),
        ).fetchone()
        if row is None:
            return None
        return _dict_to_entity(json.loads(row["data"]), row["entity_type"])

    def get_entity_version(self, entity_id: str, version: int) -> BaseEntity | None:
        conn = self._require()
        row = conn.execute(
            "SELECT data, entity_type FROM entity_versions WHERE id = ? AND version = ?",
            (entity_id, version),
        ).fetchone()
        if row is None:
            return None
        return _dict_to_entity(json.loads(row["data"]), row["entity_type"])

    def delete_entity(self, entity_id: str) -> None:
        conn = self._require()
        now = datetime.now(UTC).isoformat()
        with self._lock:
            entity = self.get_entity(entity_id)
            if entity:
                conn.execute("UPDATE entities SET is_latest = 0 WHERE id = ?", (entity_id,))
                conn.execute(
                    """INSERT INTO entity_versions
                       (id, version, entity_type, data, confidence_score, trust_score, created_at, updated_at, operation)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'DELETE')""",
                    (
                        entity.id,
                        entity.version + 1,
                        entity.entity_type.type_name,
                        json.dumps(_entity_to_dict(entity), default=str),
                        entity.confidence_score,
                        entity.trust_score,
                        entity.created_at.isoformat(),
                        now,
                    ),
                )
                conn.commit()

    def list_entities(self, entity_type: str | None = None) -> list[BaseEntity]:
        conn = self._require()
        if entity_type:
            rows = conn.execute(
                "SELECT data, entity_type FROM entities WHERE entity_type = ? AND is_latest = 1",
                (entity_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT data, entity_type FROM entities WHERE is_latest = 1"
            ).fetchall()
        return [_dict_to_entity(json.loads(r["data"]), r["entity_type"]) for r in rows]

    def list_entity_versions(self, entity_id: str) -> list[dict[str, Any]]:
        conn = self._require()
        rows = conn.execute(
            "SELECT * FROM entity_versions WHERE id = ? ORDER BY version DESC",
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Relationship CRUD ──

    def put_relationship(self, relationship: Relationship, operation: str = "CREATE") -> None:
        conn = self._require()
        data = _relationship_to_dict(relationship)
        now = datetime.now(UTC).isoformat()
        with self._lock:
            conn.execute(
                """INSERT OR REPLACE INTO relationships
                   (id, type, source_id, target_id, version, data, confidence_score, trust_weight, created_at, is_latest)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (
                    relationship.id,
                    relationship.type.type_name,
                    relationship.source_id,
                    relationship.target_id,
                    relationship.version,
                    json.dumps(data, default=str),
                    relationship.confidence_score,
                    relationship.trust_weight,
                    now,
                ),
            )
            conn.execute(
                """INSERT INTO relationship_versions
                   (id, version, type, source_id, target_id, data, confidence_score, trust_weight, created_at, operation)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    relationship.id,
                    relationship.version,
                    relationship.type.type_name,
                    relationship.source_id,
                    relationship.target_id,
                    json.dumps(data, default=str),
                    relationship.confidence_score,
                    relationship.trust_weight,
                    now,
                    operation,
                ),
            )
            conn.commit()

    def get_relationship(self, relationship_id: str) -> Relationship | None:
        conn = self._require()
        row = conn.execute(
            "SELECT data, type FROM relationships WHERE id = ? AND is_latest = 1",
            (relationship_id,),
        ).fetchone()
        if row is None:
            return None
        return _dict_to_relationship(json.loads(row["data"]), row["type"])

    def delete_relationship(self, relationship_id: str) -> None:
        conn = self._require()
        now = datetime.now(UTC).isoformat()
        with self._lock:
            rel = self.get_relationship(relationship_id)
            if rel:
                conn.execute(
                    "UPDATE relationships SET is_latest = 0 WHERE id = ?",
                    (relationship_id,),
                )
                conn.execute(
                    """INSERT INTO relationship_versions
                       (id, version, type, source_id, target_id, data, confidence_score, trust_weight, created_at, operation)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DELETE')""",
                    (
                        rel.id,
                        rel.version + 1,
                        rel.type.type_name,
                        rel.source_id,
                        rel.target_id,
                        json.dumps(_relationship_to_dict(rel), default=str),
                        rel.confidence_score,
                        rel.trust_weight,
                        now,
                    ),
                )
                conn.commit()

    def list_relationships(
        self, source_id: str | None = None, target_id: str | None = None
    ) -> list[Relationship]:
        conn = self._require()
        if source_id:
            rows = conn.execute(
                "SELECT data, type FROM relationships WHERE source_id = ? AND is_latest = 1",
                (source_id,),
            ).fetchall()
        elif target_id:
            rows = conn.execute(
                "SELECT data, type FROM relationships WHERE target_id = ? AND is_latest = 1",
                (target_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT data, type FROM relationships WHERE is_latest = 1"
            ).fetchall()
        return [_dict_to_relationship(json.loads(r["data"]), r["type"]) for r in rows]

    # ── Provenance ──

    def store_provenance(self, entity_id: str, provenance: Provenance) -> None:
        conn = self._require()
        with self._lock:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute(
                """INSERT OR REPLACE INTO provenance
                   (id, entity_id, collection_id, collector_name, collected_at, source_lineage, raw_data_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    provenance.collection_id,
                    entity_id,
                    provenance.collection_id,
                    provenance.collector_name,
                    provenance.collected_at.isoformat(),
                    json.dumps(_provenance_to_dict(provenance), default=str),
                    "",
                ),
            )
            conn.execute("PRAGMA foreign_keys=ON")
            conn.commit()

    def get_provenance(self, entity_id: str) -> list[Provenance]:
        conn = self._require()
        rows = conn.execute("SELECT * FROM provenance WHERE entity_id = ?", (entity_id,)).fetchall()
        result = []
        for r in rows:
            sl = json.loads(r["source_lineage"]) if r["source_lineage"] else None
            result.append(
                Provenance(
                    collection_id=r["collection_id"],
                    collector_name=r["collector_name"],
                    collected_at=datetime.fromisoformat(r["collected_at"]),
                    source_lineage=sl,
                )
            )
        return result

    # ── Collection Evidence ──

    def store_collection_evidence(self, evidence: Evidence, entity_id: str | None = None) -> None:
        conn = self._require()
        eid = entity_id or evidence.source
        conn.execute(
            """INSERT OR REPLACE INTO collection_evidence
               (id, entity_id, source, content, collected_at, source_tier, trust_score, reliability_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evidence.id,
                eid,
                evidence.source,
                evidence.content,
                evidence.collected_at.isoformat(),
                evidence.source_tier,
                evidence.trust_score,
                evidence.reliability_score,
            ),
        )
        conn.commit()

    def get_collection_evidence(self, entity_id: str) -> list[Evidence]:
        conn = self._require()
        rows = conn.execute(
            "SELECT * FROM collection_evidence WHERE entity_id = ?", (entity_id,)
        ).fetchall()
        return [
            Evidence(
                id=r["id"],
                source=r["source"],
                content=r["content"],
                collected_at=datetime.fromisoformat(r["collected_at"]),
                source_tier=r["source_tier"],
                trust_score=r["trust_score"],
                reliability_score=r["reliability_score"],
            )
            for r in rows
        ]

    # ── Source Registry ──

    def register_source(self, source: dict[str, Any]) -> None:
        conn = self._require()
        conn.execute(
            """INSERT OR REPLACE INTO source_registry
               (id, source_name, source_url, source_tier, trust_score, reliability_score, last_validated, classification, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source["id"],
                source["source_name"],
                source["source_url"],
                source["source_tier"],
                source["trust_score"],
                source["reliability_score"],
                source.get("last_validated", ""),
                source.get("classification", ""),
                source.get("metadata", "{}"),
            ),
        )
        conn.commit()

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        conn = self._require()
        row = conn.execute("SELECT * FROM source_registry WHERE id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    def list_sources(self) -> list[dict[str, Any]]:
        conn = self._require()
        return [dict(r) for r in conn.execute("SELECT * FROM source_registry").fetchall()]

    # ── Canonical Map ──

    def put_canonical_map(self, canonical: dict[str, Any]) -> None:
        conn = self._require()
        conn.execute(
            """INSERT OR REPLACE INTO canonical_map
               (canonical_id, entity_type, canonical_name, linked_entity_ids, aliases, highest_confidence, highest_trust, created_at, updated_at, data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                canonical["canonical_id"],
                canonical["entity_type"],
                canonical["canonical_name"],
                json.dumps(list(canonical.get("linked_entity_ids", set()))),
                json.dumps(list(canonical.get("aliases", set()))),
                canonical.get("highest_confidence", 0),
                canonical.get("highest_trust", 0),
                canonical.get("created_at", datetime.now(UTC).isoformat()),
                datetime.now(UTC).isoformat(),
                json.dumps(canonical.get("properties", {}), default=str),
            ),
        )
        conn.commit()

    def get_canonical_map(self, entity_id: str) -> dict[str, Any] | None:
        conn = self._require()
        row = conn.execute(
            "SELECT * FROM canonical_map WHERE instr(linked_entity_ids, ?) > 0",
            (entity_id,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["linked_entity_ids"] = set(json.loads(result["linked_entity_ids"]))
        result["aliases"] = set(json.loads(result.get("aliases", "[]")))
        return result

    def list_canonical_maps(self) -> list[dict[str, Any]]:
        conn = self._require()
        rows = conn.execute("SELECT * FROM canonical_map").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["linked_entity_ids"] = set(json.loads(d["linked_entity_ids"]))
            d["aliases"] = set(json.loads(d.get("aliases", "[]")))
            result.append(d)
        return result

    # ── Snapshots ──

    def create_snapshot(
        self,
        snapshot_id: str,
        label: str,
        data: dict[str, Any],
        entity_count: int,
        relationship_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        conn = self._require()
        conn.execute(
            """INSERT INTO snapshots
               (id, label, entity_count, relationship_count, data, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                label,
                entity_count,
                relationship_count,
                json.dumps(data, default=str),
                datetime.now(UTC).isoformat(),
                json.dumps(metadata or {}, default=str),
            ),
        )
        conn.commit()
        return snapshot_id

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        conn = self._require()
        row = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        return dict(row) if row else None

    def list_snapshots(self) -> list[dict[str, Any]]:
        conn = self._require()
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id, label, entity_count, relationship_count, created_at FROM snapshots ORDER BY created_at DESC"
            ).fetchall()
        ]

    # ── Audit ──

    def write_audit(self, entry: dict[str, Any]) -> None:
        conn = self._require()
        conn.execute(
            """INSERT INTO audit_log
               (id, entity_id, entity_type, operation, old_data, new_data, actor, correlation_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["id"],
                entry.get("entity_id"),
                entry.get("entity_type"),
                entry["operation"],
                entry.get("old_data"),
                entry.get("new_data"),
                entry.get("actor"),
                entry.get("correlation_id"),
                entry["timestamp"],
            ),
        )
        conn.commit()

    def query_audit(self, entity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._require()
        if entity_id:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE entity_id = ? ORDER BY timestamp DESC LIMIT ?",
                (entity_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Cache ──

    def cache_get(self, key: str) -> dict[str, Any] | None:
        conn = self._require()
        row = conn.execute(
            "SELECT * FROM cache WHERE key = ? AND (expires_at IS NULL OR expires_at >= ?)",
            (key, datetime.now(UTC).isoformat()),
        ).fetchone()
        return dict(row) if row else None

    def cache_set(self, key: str, value: str, expires_at: str | None) -> None:
        conn = self._require()
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (key, value, expires_at, datetime.now(UTC).isoformat()),
        )
        conn.commit()

    def cache_delete(self, key: str) -> None:
        conn = self._require()
        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        conn.commit()

    def cache_delete_pattern(self, pattern: str) -> None:
        conn = self._require()
        conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"%{pattern}%",))
        conn.commit()

    def cache_clear(self) -> None:
        conn = self._require()
        conn.execute("DELETE FROM cache")
        conn.commit()

    # ── Internal ──

    def _require(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Storage not connected. Call connect() first.")
        return self._conn


# Serialization helpers imported from intelgraph.core.storage.serializers
