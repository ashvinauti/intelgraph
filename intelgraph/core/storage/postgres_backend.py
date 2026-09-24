from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import Any

from intelgraph.core.entity import BaseEntity
from intelgraph.core.evidence import Evidence, Provenance
from intelgraph.core.relationship import Relationship
from intelgraph.core.storage.backend import StorageBackend
from intelgraph.core.storage.migration import run_migrations
from intelgraph.core.storage.models import SCHEMA_SQL_PG

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2 import pool as pg_pool

    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


class PostgresBackend(StorageBackend):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        dbname: str = "intelgraph",
        user: str = "intelgraph",
        password: str = "",
        pool_size: int = 5,
    ) -> None:
        if not HAS_PSYCOPG2:
            raise ImportError(
                "psycopg2-binary is required for PostgreSQL backend. "
                "Install it with: pip install intelgraph[postgres]"
            )
        self._host = host
        self._port = port
        self._dbname = dbname
        self._user = user
        self._password = password
        self._pool_size = pool_size
        self._pool: pg_pool.ThreadedConnectionPool | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        self._pool = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=self._pool_size,
            host=self._host,
            port=self._port,
            dbname=self._dbname,
            user=self._user,
            password=self._password,
        )

    def disconnect(self) -> None:
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None

    def pool_stats(self) -> dict[str, int]:
        if self._pool is None:
            return {"pool_active": 0, "pool_idle": 0, "pool_total": 0}
        try:
            return {
                "pool_active": self._pool._used or 0,
                "pool_idle": (self._pool._pool or 0) - (self._pool._used or 0),
                "pool_total": self._pool_size,
            }
        except Exception:
            return {"pool_active": 0, "pool_idle": 0, "pool_total": self._pool_size}

    def initialize_schema(self) -> None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL_PG)
            conn.commit()
        finally:
            self._release(conn)

    def migrate(self, target_version: int | None = None) -> None:
        current = self.schema_version()
        conn = self._require()
        try:
            with conn.cursor() as cur:
                target = run_migrations(cur, SCHEMA_SQL_PG, current, target_version)
                cur.execute("UPDATE schema_version SET version = %s", (target,))
            conn.commit()
        finally:
            self._release(conn)

    def schema_version(self) -> int:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version FROM schema_version LIMIT 1")
                row = cur.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0
        finally:
            self._release(conn)

    # ── Entity CRUD ──

    def put_entity(self, entity: BaseEntity, operation: str = "CREATE") -> None:
        conn = self._require()
        try:
            data = _entity_to_dict(entity)
            now = datetime.now(UTC).isoformat()
            with self._lock:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO entities
                           (id, entity_type, version, data, confidence_score, trust_score, created_at, updated_at, is_latest)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
                           ON CONFLICT (id) DO UPDATE SET
                           version = EXCLUDED.version, data = EXCLUDED.data,
                           confidence_score = EXCLUDED.confidence_score, trust_score = EXCLUDED.trust_score,
                           updated_at = EXCLUDED.updated_at, is_latest = 1""",
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
                    cur.execute(
                        """INSERT INTO entity_versions
                           (id, version, entity_type, data, confidence_score, trust_score, created_at, updated_at, operation)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
        finally:
            self._release(conn)

    def get_entity(self, entity_id: str) -> BaseEntity | None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data, entity_type FROM entities WHERE id = %s AND is_latest = 1",
                    (entity_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return _dict_to_entity(json.loads(row[0]), row[1])
        finally:
            self._release(conn)

    def get_entity_version(self, entity_id: str, version: int) -> BaseEntity | None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data, entity_type FROM entity_versions WHERE id = %s AND version = %s",
                    (entity_id, version),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return _dict_to_entity(json.loads(row[0]), row[1])
        finally:
            self._release(conn)

    def delete_entity(self, entity_id: str) -> None:
        conn = self._require()
        try:
            now = datetime.now(UTC).isoformat()
            with self._lock:
                with conn.cursor() as cur:
                    entity = self.get_entity(entity_id)
                    if entity:
                        cur.execute("UPDATE entities SET is_latest = 0 WHERE id = %s", (entity_id,))
                        cur.execute(
                            """INSERT INTO entity_versions
                               (id, version, entity_type, data, confidence_score, trust_score, created_at, updated_at, operation)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'DELETE')""",
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
        finally:
            self._release(conn)

    def list_entities(self, entity_type: str | None = None) -> list[BaseEntity]:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                if entity_type:
                    cur.execute(
                        "SELECT data, entity_type FROM entities WHERE entity_type = %s AND is_latest = 1",
                        (entity_type,),
                    )
                else:
                    cur.execute("SELECT data, entity_type FROM entities WHERE is_latest = 1")
                return [_dict_to_entity(json.loads(r[0]), r[1]) for r in cur.fetchall()]
        finally:
            self._release(conn)

    def list_entity_versions(self, entity_id: str) -> list[dict[str, Any]]:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM entity_versions WHERE id = %s ORDER BY version DESC",
                    (entity_id,),
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            self._release(conn)

    # ── Relationship CRUD ──

    def put_relationship(self, relationship: Relationship, operation: str = "CREATE") -> None:
        conn = self._require()
        try:
            data = _relationship_to_dict(relationship)
            now = datetime.now(UTC).isoformat()
            with self._lock:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO relationships
                           (id, type, source_id, target_id, version, data, confidence_score, trust_weight, created_at, is_latest)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                           ON CONFLICT (id) DO UPDATE SET
                           version = EXCLUDED.version, data = EXCLUDED.data,
                           confidence_score = EXCLUDED.confidence_score, trust_weight = EXCLUDED.trust_weight,
                           created_at = EXCLUDED.created_at, is_latest = 1""",
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
                    cur.execute(
                        """INSERT INTO relationship_versions
                           (id, version, type, source_id, target_id, data, confidence_score, trust_weight, created_at, operation)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
        finally:
            self._release(conn)

    def get_relationship(self, relationship_id: str) -> Relationship | None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT data, type FROM relationships WHERE id = %s AND is_latest = 1",
                    (relationship_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return _dict_to_relationship(json.loads(row[0]), row[1])
        finally:
            self._release(conn)

    def delete_relationship(self, relationship_id: str) -> None:
        conn = self._require()
        try:
            now = datetime.now(UTC).isoformat()
            with self._lock:
                with conn.cursor() as cur:
                    rel = self.get_relationship(relationship_id)
                    if rel:
                        cur.execute(
                            "UPDATE relationships SET is_latest = 0 WHERE id = %s",
                            (relationship_id,),
                        )
                        cur.execute(
                            """INSERT INTO relationship_versions
                               (id, version, type, source_id, target_id, data, confidence_score, trust_weight, created_at, operation)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'DELETE')""",
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
        finally:
            self._release(conn)

    def list_relationships(
        self, source_id: str | None = None, target_id: str | None = None
    ) -> list[Relationship]:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                if source_id:
                    cur.execute(
                        "SELECT data, type FROM relationships WHERE source_id = %s AND is_latest = 1",
                        (source_id,),
                    )
                elif target_id:
                    cur.execute(
                        "SELECT data, type FROM relationships WHERE target_id = %s AND is_latest = 1",
                        (target_id,),
                    )
                else:
                    cur.execute("SELECT data, type FROM relationships WHERE is_latest = 1")
                return [_dict_to_relationship(json.loads(r[0]), r[1]) for r in cur.fetchall()]
        finally:
            self._release(conn)

    # ── Provenance ──

    def store_provenance(self, entity_id: str, provenance: Provenance) -> None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO provenance
                       (id, entity_id, collection_id, collector_name, collected_at, source_lineage, raw_data_hash)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO NOTHING""",
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
            conn.commit()
        finally:
            self._release(conn)

    def get_provenance(self, entity_id: str) -> list[Provenance]:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM provenance WHERE entity_id = %s", (entity_id,))
                result = []
                for r in cur.fetchall():
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
        finally:
            self._release(conn)

    # ── Collection Evidence ──

    def store_collection_evidence(self, evidence: Evidence, entity_id: str | None = None) -> None:
        conn = self._require()
        try:
            eid = entity_id or evidence.source
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO collection_evidence
                       (id, entity_id, source, content, collected_at, source_tier, trust_score, reliability_score)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO UPDATE SET
                       trust_score = EXCLUDED.trust_score,
                       reliability_score = EXCLUDED.reliability_score""",
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
        finally:
            self._release(conn)

    def get_collection_evidence(self, entity_id: str) -> list[Evidence]:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM collection_evidence WHERE entity_id = %s", (entity_id,))
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
                    for r in cur.fetchall()
                ]
        finally:
            self._release(conn)

    # ── Source Registry ──

    def register_source(self, source: dict[str, Any]) -> None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO source_registry
                       (id, source_name, source_url, source_tier, trust_score, reliability_score, last_validated, classification, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO UPDATE SET
                       source_name = EXCLUDED.source_name, source_url = EXCLUDED.source_url,
                       source_tier = EXCLUDED.source_tier, trust_score = EXCLUDED.trust_score,
                       reliability_score = EXCLUDED.reliability_score,
                       last_validated = EXCLUDED.last_validated""",
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
        finally:
            self._release(conn)

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM source_registry WHERE id = %s", (source_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._release(conn)

    def list_sources(self) -> list[dict[str, Any]]:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM source_registry")
                return [dict(r) for r in cur.fetchall()]
        finally:
            self._release(conn)

    # ── Canonical Map ──

    def put_canonical_map(self, canonical: dict[str, Any]) -> None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO canonical_map
                       (canonical_id, entity_type, canonical_name, linked_entity_ids, aliases, highest_confidence, highest_trust, created_at, updated_at, data)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (canonical_id) DO UPDATE SET
                       linked_entity_ids = EXCLUDED.linked_entity_ids,
                       aliases = EXCLUDED.aliases,
                       highest_confidence = EXCLUDED.highest_confidence,
                       highest_trust = EXCLUDED.highest_trust,
                       updated_at = EXCLUDED.updated_at""",
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
        finally:
            self._release(conn)

    def get_canonical_map(self, entity_id: str) -> dict[str, Any] | None:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM canonical_map WHERE linked_entity_ids::text LIKE %s",
                    (f"%{entity_id}%",),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                result = dict(row)
                result["linked_entity_ids"] = set(json.loads(result["linked_entity_ids"]))
                result["aliases"] = set(json.loads(result.get("aliases", "[]")))
                return result
        finally:
            self._release(conn)

    def list_canonical_maps(self) -> list[dict[str, Any]]:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM canonical_map")
                result = []
                for r in cur.fetchall():
                    d = dict(r)
                    d["linked_entity_ids"] = set(json.loads(d["linked_entity_ids"]))
                    d["aliases"] = set(json.loads(d.get("aliases", "[]")))
                    result.append(d)
                return result
        finally:
            self._release(conn)

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
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO snapshots
                       (id, label, entity_count, relationship_count, data, created_at, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
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
        finally:
            self._release(conn)

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM snapshots WHERE id = %s", (snapshot_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._release(conn)

    def list_snapshots(self) -> list[dict[str, Any]]:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, label, entity_count, relationship_count, created_at FROM snapshots ORDER BY created_at DESC"
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            self._release(conn)

    # ── Audit ──

    def write_audit(self, entry: dict[str, Any]) -> None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO audit_log
                       (id, entity_id, entity_type, operation, old_data, new_data, actor, correlation_id, timestamp)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
        finally:
            self._release(conn)

    def query_audit(self, entity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if entity_id:
                    cur.execute(
                        "SELECT * FROM audit_log WHERE entity_id = %s ORDER BY timestamp DESC LIMIT %s",
                        (entity_id, limit),
                    )
                else:
                    cur.execute(
                        "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT %s",
                        (limit,),
                    )
                return [dict(r) for r in cur.fetchall()]
        finally:
            self._release(conn)

    # ── Cache ──

    def cache_get(self, key: str) -> dict[str, Any] | None:
        conn = self._require()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM cache WHERE key = %s AND (expires_at IS NULL OR expires_at >= %s)",
                    (key, datetime.now(UTC).isoformat()),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._release(conn)

    def cache_set(self, key: str, value: str, expires_at: str | None) -> None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO cache (key, value, expires_at, created_at) VALUES (%s, %s, %s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at",
                    (key, value, expires_at, datetime.now(UTC).isoformat()),
                )
            conn.commit()
        finally:
            self._release(conn)

    def cache_delete(self, key: str) -> None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM cache WHERE key = %s", (key,))
            conn.commit()
        finally:
            self._release(conn)

    def cache_delete_pattern(self, pattern: str) -> None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM cache WHERE key LIKE %s", (f"%{pattern}%",))
            conn.commit()
        finally:
            self._release(conn)

    def cache_clear(self) -> None:
        conn = self._require()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM cache")
            conn.commit()
        finally:
            self._release(conn)

    # ── Internal ──

    def _require(self) -> Any:
        if self._pool is None:
            raise RuntimeError("Storage not connected. Call connect() first.")
        return self._pool.getconn()

    def _release(self, conn: Any) -> None:
        if self._pool is not None and conn is not None:
            self._pool.putconn(conn)


# Serialization helpers from shared module

from intelgraph.core.storage.serializers import (  # noqa: E402, F401
    _dict_to_entity,
    _dict_to_relationship,
    _entity_to_dict,
    _provenance_to_dict,
    _relationship_to_dict,
)
