"""SQLite-backed persistent storage for IntelligenceGraph.

Write-through pattern: every mutation (add_entity, add_relationship,
remove_node, remove_edge) updates both in-memory state and this SQLite
store. On restart, ``load_from_storage()`` rebuilds in-memory state.

Schema:
  graph_nodes       — one row per entity
  graph_edges       — one row per relationship
  previous_versions — version history for merged/overwritten nodes
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from intelgraph.core.entity import BaseEntity
from intelgraph.core.entity.cve import CveEntity
from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.evidence import Evidence, Provenance, SourceLineage
from intelgraph.core.graph.edge import Edge
from intelgraph.core.graph.node import Node
from intelgraph.core.relationship import Relationship
from intelgraph.core.relationship.types import RelationshipType

# Registry: EntityType.name.lower() -> class
_ENTITY_REGISTRY: dict[str, type[BaseEntity]] = {
    "ip_address": IPAddress,
    "domain": Domain,
    "cve": CveEntity,
}

# Registry: dataclass class -> field name -> constructor type hint
# We infer types from the class's __init__ signature instead of dataclass
# annotations (which are strings under `from __future__ import annotations`).

# --- Serialization ---

_DATETIME_FIELDS: dict[type, set[str]] = {}


def _get_datetime_fields(cls: type) -> set[str]:
    """Return names of fields whose type is datetime (heuristic from defaults)."""
    if cls in _DATETIME_FIELDS:
        return _DATETIME_FIELDS[cls]
    result: set[str] = set()
    if is_dataclass(cls):
        for f in fields(cls):
            # annotation is a string under __future__.annotations;
            # check default or default_factory
            if "datetime" in str(f.type) or callable(f.default_factory):
                # default_factory check for datetime
                try:
                    default = f.default_factory() if callable(f.default_factory) else f.default
                    if isinstance(default, datetime):
                        result.add(f.name)
                except Exception:
                    pass
    _DATETIME_FIELDS[cls] = result
    return result


def _serialize(obj: Any) -> Any:
    """Recursively convert a dataclass/nested structure to JSON-safe primitives."""
    if is_dataclass(obj) and not isinstance(obj, type):
        result: dict[str, Any] = {}
        for f in fields(obj):
            if not f.init and f.name == "entity_type":
                result[f.name] = obj.entity_type.name if hasattr(obj, "entity_type") else None
                continue
            if f.name == "entity_type":
                # enum-like, non-init in subclasses
                continue
            result[f.name] = _serialize(getattr(obj, f.name))
        return result
    if isinstance(obj, tuple):
        return [_serialize(i) for i in obj]
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


def serialize_entity(entity: BaseEntity) -> dict[str, Any]:
    return _serialize(entity)


def serialize_evidence(ev: Evidence) -> dict[str, Any]:
    return _serialize(ev)


def serialize_relationship(rel: Relationship) -> dict[str, Any]:
    return _serialize(rel)


# --- Deserialization ---


def _is_datetime_field(cls: type, fname: str) -> bool:
    # Heuristic: probe default
    try:
        import inspect

        sig = inspect.signature(cls.__init__)
        param = sig.parameters.get(fname)
        if param and param.annotation is not inspect.Parameter.empty:
            ann = param.annotation
            if isinstance(ann, type) and issubclass(ann, datetime):
                return True
    except (ValueError, TypeError):
        pass
    # Check default
    for f in fields(cls):
        if f.name == fname:
            if callable(f.default_factory):
                try:
                    d = f.default_factory()
                    if isinstance(d, datetime):
                        return True
                except Exception:
                    pass
    return False


def _str_to_enum(enum_cls: type, name: str) -> Any:
    try:
        return enum_cls[name]
    except KeyError:
        return None


def _coerce_datetime(val: str) -> datetime | None:
    if isinstance(val, str) and val:
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            return None
    return None


def _deserialize(obj: Any, cls: type) -> Any:
    """Recursively convert JSON data back to ``cls`` instance."""
    if cls is Evidence and isinstance(obj, dict):
        kwargs = {}
        init_fields = {f.name for f in fields(Evidence) if f.init}
        for fname in init_fields:
            if fname not in obj:
                continue
            val = obj[fname]
            if fname in ("collected_at",):
                d = _coerce_datetime(val)
                kwargs[fname] = d if d else datetime.now(UTC)
            else:
                kwargs[fname] = val
        return Evidence(**kwargs)
    if cls is Provenance and isinstance(obj, dict):
        kwargs = {}
        init_fields = {f.name for f in fields(Provenance) if f.init}
        for fname in init_fields:
            if fname not in obj:
                continue
            val = obj[fname]
            if fname == "collected_at":
                d = _coerce_datetime(val)
                kwargs[fname] = d if d else datetime.now(UTC)
            elif fname == "source_lineage" and isinstance(val, list):
                kwargs[fname] = tuple(_deserialize(v, SourceLineage) for v in val)
            else:
                kwargs[fname] = val
        return Provenance(**kwargs)
    if cls is SourceLineage and isinstance(obj, dict):
        kwargs = {}
        init_fields = {f.name for f in fields(SourceLineage) if f.init}
        for fname in init_fields:
            if fname not in obj:
                continue
            val = obj[fname]
            if fname == "intermediate_sources" and isinstance(val, list):
                kwargs[fname] = tuple(_deserialize(v, SourceLineage) for v in val)
            else:
                kwargs[fname] = val
        return SourceLineage(**kwargs)
    if cls is Relationship and isinstance(obj, dict):
        kwargs = {}
        init_fields = {f.name for f in fields(Relationship) if f.init}
        for fname in init_fields:
            if fname not in obj:
                continue
            val = obj[fname]
            if fname == "type" and isinstance(val, str):
                kwargs[fname] = _str_to_enum(RelationshipType, val)
            elif fname in ("created_at", "first_seen", "last_seen") and isinstance(val, str):
                d = _coerce_datetime(val)
                kwargs[fname] = d if d else datetime.now(UTC)
            elif fname in ("evidence_chain", "provenance") and isinstance(val, list):
                inner_cls = Evidence if fname == "evidence_chain" else Provenance
                kwargs[fname] = tuple(_deserialize(v, inner_cls) for v in val)
            else:
                kwargs[fname] = val
        return Relationship(**kwargs)
    if is_dataclass(cls) and isinstance(obj, dict):
        kwargs: dict[str, Any] = {}
        import inspect

        sig = inspect.signature(cls.__init__)
        for fname, param in sig.parameters.items():
            if fname == "self":
                continue
            if fname not in obj:
                continue
            val = obj[fname]
            ann = (
                param.annotation if param.annotation is not inspect.Parameter.empty else type(None)
            )
            # datetime field?
            if isinstance(ann, type) and issubclass(ann, datetime):
                d = _coerce_datetime(
                    val
                    if isinstance(val, str)
                    else val.get("isoformat", ("") if isinstance(val, dict) else "")
                )
                kwargs[fname] = d if d is not None else datetime.now(UTC)
            elif fname in (
                "evidence",
                "provenance",
                "aliases",
                "open_ports",
                "evidence_chain",
                "nameservers",
                "ip_addresses",
                "technologies",
                "intermediate_sources",
            ):
                if isinstance(val, list):
                    inner_cls = None
                    if fname == "evidence":
                        inner_cls = Evidence
                    elif fname == "provenance":
                        inner_cls = Provenance
                    elif fname == "evidence_chain":
                        inner_cls = Evidence
                    if inner_cls:
                        items = [_deserialize(v, inner_cls) for v in val]
                    else:
                        items = list(val)
                    kwargs[fname] = tuple(items)
                else:
                    kwargs[fname] = val
            else:
                kwargs[fname] = val
        return cls(**kwargs)
    return obj


def deserialize_entity(entity_type_name: str, data: dict[str, Any]) -> BaseEntity:
    cls = _ENTITY_REGISTRY.get(entity_type_name.lower())
    if cls is None:
        raise ValueError(f"Unknown entity type: {entity_type_name!r}")
    return _deserialize(data, cls)  # type: ignore[arg-type]


def deserialize_evidence(data: dict[str, Any]) -> Evidence:
    return _deserialize(data, Evidence)


def deserialize_relationship(data: dict[str, Any]) -> Relationship:
    return _deserialize(data, Relationship)


class GraphStorage:
    """SQLite write-through storage for IntelligenceGraph."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id         TEXT PRIMARY KEY,
                entity_type     TEXT NOT NULL,
                entity_data     TEXT NOT NULL,
                confidence_score INTEGER DEFAULT 0,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS graph_edges (
                edge_id          TEXT PRIMARY KEY,
                source_node_id   TEXT NOT NULL,
                target_node_id   TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                confidence       INTEGER DEFAULT 0,
                edge_data         TEXT,
                created_at        TEXT NOT NULL,
                FOREIGN KEY (source_node_id) REFERENCES graph_nodes(node_id),
                FOREIGN KEY (target_node_id) REFERENCES graph_nodes(node_id)
            );

            CREATE TABLE IF NOT EXISTS previous_versions (
                version_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id     TEXT NOT NULL,
                version_data TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                saved_at    TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
                node_id,
                entity_type,
                entity_identifier,
                entity_data,
                content='',
                tokenize='unicode61 remove_diacritics 2'
            );
            """)
        self._conn.commit()

    # ── Node operations ──

    def upsert_node(self, node: Node) -> None:
        entity = node.entity
        entity_type_name = entity.entity_type.name.lower()
        entity_data = json.dumps(serialize_entity(entity), ensure_ascii=False)
        now = datetime.now(UTC).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO graph_nodes (node_id, entity_type, entity_data, confidence_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                entity_data = excluded.entity_data,
                confidence_score = excluded.confidence_score,
                updated_at = excluded.updated_at
            """,
            (node.id, entity_type_name, entity_data, entity.confidence_score, now, now),
        )
        # Sync FTS index
        self._sync_fts_node(node.id, entity_type_name, entity, entity_data)
        self._conn.commit()

    def _sync_fts_node(
        self, node_id: str, entity_type_name: str, entity: BaseEntity, entity_data_json: str
    ) -> None:
        identifier = _entity_identifier(entity)
        search_content = _build_fts_content(entity, entity_data_json)
        cur = self._conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO search_index (node_id, entity_type, entity_identifier, entity_data) VALUES (?, ?, ?, ?)",
            (node_id, entity_type_name, identifier, search_content),
        )

    def delete_node(self, node_id: str) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM graph_nodes WHERE node_id = ?", (node_id,))
        cur.execute(
            "DELETE FROM graph_edges WHERE source_node_id = ? OR target_node_id = ?",
            (node_id, node_id),
        )
        cur.execute("DELETE FROM previous_versions WHERE node_id = ?", (node_id,))
        cur.execute("DELETE FROM search_index WHERE node_id = ?", (node_id,))
        self._conn.commit()

    def save_previous_version(self, node_id: str, node: Node) -> None:
        entity = node.entity
        entity_type_name = entity.entity_type.name.lower()
        version_data = json.dumps(serialize_entity(entity), ensure_ascii=False)
        now = datetime.now(UTC).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO previous_versions (node_id, version_data, entity_type, saved_at)
            VALUES (?, ?, ?, ?)
            """,
            (node_id, version_data, entity_type_name, now),
        )
        self._conn.commit()

    def load_nodes(self) -> list[Node]:
        cur = self._conn.cursor()
        cur.execute("SELECT node_id, entity_type, entity_data FROM graph_nodes ORDER BY created_at")
        nodes: list[Node] = []
        for row in cur.fetchall():
            data = json.loads(row["entity_data"])
            entity = deserialize_entity(row["entity_type"], data)
            nodes.append(Node(entity=entity))
        return nodes

    def load_previous_versions(self) -> dict[str, list[Node]]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT node_id, entity_type, version_data FROM previous_versions ORDER BY version_id"
        )
        result: dict[str, list[Node]] = {}
        for row in cur.fetchall():
            data = json.loads(row["version_data"])
            entity = deserialize_entity(row["entity_type"], data)
            node = Node(entity=entity)
            result.setdefault(row["node_id"], []).append(node)
        return result

    # ── Edge operations ──

    def upsert_edge(self, edge: Edge) -> None:
        rel = edge.relationship
        rel_type = rel.type.name
        edge_data = json.dumps(serialize_relationship(rel), ensure_ascii=False)
        now = datetime.now(UTC).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO graph_edges (edge_id, source_node_id, target_node_id, relationship_type, confidence, edge_data, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(edge_id) DO UPDATE SET
                source_node_id = excluded.source_node_id,
                target_node_id = excluded.target_node_id,
                relationship_type = excluded.relationship_type,
                confidence = excluded.confidence,
                edge_data = excluded.edge_data
            """,
            (
                edge.id,
                edge.source_id,
                edge.target_id,
                rel_type,
                rel.confidence_score,
                edge_data,
                now,
            ),
        )
        self._conn.commit()

    def delete_edge(self, edge_id: str) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM graph_edges WHERE edge_id = ?", (edge_id,))
        self._conn.commit()

    def load_edges(self) -> list[Edge]:
        cur = self._conn.cursor()
        cur.execute("SELECT edge_data FROM graph_edges")
        edges: list[Edge] = []
        for row in cur.fetchall():
            data = json.loads(row["edge_data"])
            rel = deserialize_relationship(data)
            edges.append(Edge(relationship=rel))
        return edges

    def close(self) -> None:
        self._conn.close()

    def count_nodes(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM graph_nodes")
        return cur.fetchone()[0]

    def count_edges(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM graph_edges")
        return cur.fetchone()[0]

    # ── FTS5 Search ──

    def search_fts(
        self,
        query: str,
        type_filter: str = "all",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Full-text search over entities using FTS5.

        Returns results ranked by FTS5 BM25 relevance.
        """
        cur = self._conn.cursor()
        # Sanitize query for FTS5: escape special chars, add prefix matching
        fts_query = _fts_sanitize(query)
        if not fts_query:
            return []

        sql = """
            SELECT si.node_id, si.entity_type, si.entity_identifier,
                   rank as relevance, n.confidence_score
            FROM search_index si
            JOIN graph_nodes n ON n.node_id = si.node_id
            WHERE search_index MATCH ?
        """
        params: list[Any] = [fts_query]

        if type_filter != "all":
            sql += " AND si.entity_type = ?"
            params.append(type_filter)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        try:
            rows = cur.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # FTS5 query parse error, fall back to LIKE
            return self._search_like(query, type_filter, limit)

        return [
            {
                "node_id": r["node_id"],
                "entity_type": r["entity_type"],
                "entity_identifier": r["entity_identifier"],
                "confidence": r["confidence_score"],
                "relevance": r["relevance"],
            }
            for r in rows
        ]

    def _search_like(
        self,
        query: str,
        type_filter: str = "all",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Fallback LIKE-based search when FTS5 query fails."""
        cur = self._conn.cursor()
        like = f"%{query}%"
        sql = """
            SELECT si.node_id, si.entity_type, si.entity_identifier,
                   n.confidence_score
            FROM search_index si
            JOIN graph_nodes n ON n.node_id = si.node_id
            WHERE si.entity_data LIKE ?
        """
        params: list[Any] = [like]
        if type_filter != "all":
            sql += " AND si.entity_type = ?"
            params.append(type_filter)
        sql += " ORDER BY n.confidence_score DESC LIMIT ?"
        params.append(limit)
        rows = cur.execute(sql, params).fetchall()
        return [
            {
                "node_id": r["node_id"],
                "entity_type": r["entity_type"],
                "entity_identifier": r["entity_identifier"],
                "confidence": r["confidence_score"],
                "relevance": 0.0,
            }
            for r in rows
        ]

    def rebuild_fts_index(self) -> None:
        """Rebuild the entire FTS index from graph_nodes."""
        cur = self._conn.cursor()
        cur.execute("DELETE FROM search_index")
        rows = cur.execute("SELECT node_id, entity_type, entity_data FROM graph_nodes").fetchall()
        for row in rows:
            node_id = row["node_id"]
            entity_type = row["entity_type"]
            entity_data = row["entity_data"]
            try:
                data = json.loads(entity_data)
            except json.JSONDecodeError:
                continue
            identifier = data.get("ip") or data.get("domain_name") or data.get("cve_id") or node_id
            content = _build_fts_content_raw(data)
            cur.execute(
                "INSERT INTO search_index (node_id, entity_type, entity_identifier, entity_data) VALUES (?, ?, ?, ?)",
                (node_id, entity_type, identifier, content),
            )
        self._conn.commit()


# ── FTS helper functions ──


def _entity_identifier(entity: BaseEntity) -> str:
    return (
        getattr(entity, "ip", None)
        or getattr(entity, "domain_name", None)
        or getattr(entity, "cve_id", None)
        or entity.id
    )


def _build_fts_content(entity: BaseEntity, entity_data_json: str) -> str:
    """Build a flat searchable text blob from entity fields."""
    parts: list[str] = []
    data = json.loads(entity_data_json) if isinstance(entity_data_json, str) else entity_data_json
    for val in data.values():
        if isinstance(val, str) and val:
            parts.append(val)
        elif isinstance(val, (int, float)):
            parts.append(str(val))
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str) and v:
                            parts.append(v)
                elif isinstance(item, str) and item:
                    parts.append(item)
    # Add evidence content
    ev = getattr(entity, "evidence", ())
    for e in ev:
        if e.content:
            parts.append(e.content)
    return " ".join(parts)


def _build_fts_content_raw(data: dict[str, Any]) -> str:
    """Build search content from raw serialized entity data dict."""
    parts: list[str] = []
    for val in data.values():
        if isinstance(val, str) and val:
            parts.append(val)
        elif isinstance(val, (int, float)):
            parts.append(str(val))
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str) and v:
                            parts.append(v)
                elif isinstance(item, str) and item:
                    parts.append(item)
    return " ".join(parts)


def _fts_sanitize(query: str) -> str:
    """Convert a user query to FTS5-safe MATCH expression.

    Supports prefix matching and handles special characters.
    """
    query = query.strip()
    if not query:
        return ""
    # Escape FTS5 special characters and add prefix wildcard
    escaped = re.sub(r"[^\w\s.]", " ", query)
    escaped = re.sub(r"\s+", " ", escaped).strip()
    if not escaped:
        return ""
    # Add prefix matching for each term
    terms = escaped.split()
    fts_terms = []
    for t in terms:
        if t.endswith("."):
            # IP/domain prefix: escape dots
            t = t.rstrip(".")
        fts_terms.append(f'"{t}"*')
    return " AND ".join(fts_terms)
