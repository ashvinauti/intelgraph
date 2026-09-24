import json
from datetime import UTC, datetime
from typing import Any

from intelgraph.core.evidence_chain.base import (
    EvidenceChain,
    EvidenceItem,
    EvidenceStatus,
    SupportType,
)

EVIDENCE_CHAIN_SCHEMA_SQL = """

CREATE TABLE IF NOT EXISTS evidence_chains (
    chain_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    contradiction_score REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'unknown',
    version INTEGER NOT NULL DEFAULT 1,
    source_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id TEXT PRIMARY KEY,
    chain_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    claim TEXT NOT NULL,
    support_type TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    extracted_at TEXT NOT NULL,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS chain_versions (
    chain_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    operation TEXT NOT NULL,
    PRIMARY KEY (chain_id, version)
);

CREATE TABLE IF NOT EXISTS contradictions (
    id TEXT PRIMARY KEY,
    chain_id TEXT NOT NULL,
    evidence_id_a TEXT NOT NULL,
    evidence_id_b TEXT NOT NULL,
    contradiction_type TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0.0,
    detected_at TEXT NOT NULL,
    resolved_at TEXT,
    resolution TEXT
);

CREATE INDEX IF NOT EXISTS idx_ec_entity ON evidence_chains(entity_id);
CREATE INDEX IF NOT EXISTS idx_ec_status ON evidence_chains(status);
CREATE INDEX IF NOT EXISTS idx_ei_chain ON evidence_items(chain_id);
CREATE INDEX IF NOT EXISTS idx_cv_chain ON chain_versions(chain_id);
CREATE INDEX IF NOT EXISTS idx_contra_chain ON contradictions(chain_id);
"""


class EvidenceChainStorage:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def initialize_tables(self) -> None:
        conn = self._get_conn()
        conn.executescript(EVIDENCE_CHAIN_SCHEMA_SQL)
        conn.commit()

    def save_chain(self, chain: EvidenceChain) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO evidence_chains
               (chain_id, entity_id, confidence, contradiction_score, status, version, source_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chain.chain_id,
                chain.entity_id,
                chain.confidence,
                chain.contradiction_score,
                chain.status.name_lower,
                chain.version,
                chain.source_count,
                chain.created_at.isoformat(),
                chain.updated_at.isoformat(),
            ),
        )
        for item in chain.evidence:
            conn.execute(
                """INSERT OR REPLACE INTO evidence_items
                   (evidence_id, chain_id, source_id, document_id, claim, support_type, confidence, extracted_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.evidence_id,
                    chain.chain_id,
                    item.source_id,
                    item.document_id,
                    item.claim,
                    item.support_type.name_lower,
                    item.confidence,
                    item.extracted_at.isoformat(),
                    json.dumps(item.metadata, default=str),
                ),
            )
        conn.commit()

    def save_chain_version(self, chain: EvidenceChain, operation: str) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO chain_versions
               (chain_id, version, data, created_at, operation)
               VALUES (?, ?, ?, ?, ?)""",
            (
                chain.chain_id,
                chain.version,
                json.dumps(chain.to_dict(), default=str),
                datetime.now(UTC).isoformat(),
                operation,
            ),
        )
        conn.commit()

    def save_contradictions(self, records: list[Any]) -> None:
        conn = self._get_conn()
        for r in records:
            conn.execute(
                """INSERT OR REPLACE INTO contradictions
                   (id, chain_id, evidence_id_a, evidence_id_b, contradiction_type, score, detected_at, resolved_at, resolution)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r.id,
                    r.chain_id,
                    r.evidence_id_a,
                    r.evidence_id_b,
                    r.contradiction_type,
                    r.score,
                    r.detected_at.isoformat(),
                    r.resolved_at.isoformat() if r.resolved_at else None,
                    r.resolution or "",
                ),
            )
        conn.commit()

    def load_chain(self, chain_id: str) -> EvidenceChain | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM evidence_chains WHERE chain_id = ?", (chain_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_chain(row)

    def load_chain_by_entity(self, entity_id: str) -> EvidenceChain | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM evidence_chains WHERE entity_id = ? ORDER BY updated_at DESC LIMIT 1",
            (entity_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_chain(row)

    def load_all_chains(self) -> list[EvidenceChain]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM evidence_chains").fetchall()
        return [self._row_to_chain(r) for r in rows]

    def load_items(self, chain_id: str) -> list[EvidenceItem]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM evidence_items WHERE chain_id = ?", (chain_id,)
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def load_contradictions(self, chain_id: str) -> list[Any]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM contradictions WHERE chain_id = ?", (chain_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_chain(self, chain_id: str) -> bool:
        conn = self._get_conn()
        conn.execute("DELETE FROM contradictions WHERE chain_id = ?", (chain_id,))
        conn.execute("DELETE FROM evidence_items WHERE chain_id = ?", (chain_id,))
        conn.execute("DELETE FROM chain_versions WHERE chain_id = ?", (chain_id,))
        conn.execute("DELETE FROM evidence_chains WHERE chain_id = ?", (chain_id,))
        conn.commit()
        return True

    def _get_conn(self) -> Any:
        conn = (
            getattr(self._backend, "_conn", None)
            or getattr(self._backend, "_require", lambda: None)()
        )
        if conn is None:
            raise RuntimeError("Backend not connected")
        return conn

    def _row_to_chain(self, row: Any) -> EvidenceChain:
        chain = EvidenceChain(
            chain_id=row["chain_id"],
            entity_id=row["entity_id"],
            confidence=row["confidence"],
            contradiction_score=row["contradiction_score"],
            status=EvidenceStatus[row["status"].upper()],
            version=row["version"],
            source_count=row["source_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
        chain.evidence = self.load_items(chain.chain_id)
        return chain

    @staticmethod
    def _row_to_item(row: Any) -> EvidenceItem:
        meta = {}
        try:
            raw = row["metadata"]
            if raw:
                meta = json.loads(raw)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            meta = {}
        return EvidenceItem(
            evidence_id=row["evidence_id"],
            source_id=row["source_id"],
            document_id=row["document_id"],
            claim=row["claim"],
            support_type=SupportType[row["support_type"].upper()],
            confidence=row["confidence"],
            extracted_at=datetime.fromisoformat(row["extracted_at"]),
            metadata=meta,
        )
