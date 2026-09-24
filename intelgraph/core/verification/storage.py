import json
from datetime import UTC, datetime
from typing import Any

from intelgraph.core.verification.base import (
    OperationalState,
    VerificationRecord,
    VerificationState,
)

VERIFICATION_SCHEMA_SQL = """

CREATE TABLE IF NOT EXISTS verifications (
    verification_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    entity_type TEXT,
    verification_state TEXT NOT NULL,
    operational_state TEXT NOT NULL DEFAULT 'active',
    confidence REAL NOT NULL DEFAULT 0.0,
    consensus REAL NOT NULL DEFAULT 0.0,
    contradiction REAL NOT NULL DEFAULT 0.0,
    source_count INTEGER NOT NULL DEFAULT 0,
    human_review_boost REAL NOT NULL DEFAULT 0.0,
    matched_rules TEXT,
    reasoning TEXT,
    computation_steps TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    is_high_impact INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_history (
    verification_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    entity_id TEXT NOT NULL,
    verification_state TEXT NOT NULL,
    operational_state TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    reasoning TEXT,
    created_at TEXT NOT NULL,
    operation TEXT NOT NULL,
    PRIMARY KEY (verification_id, version)
);

CREATE INDEX IF NOT EXISTS idx_v_entity ON verifications(entity_id);
CREATE INDEX IF NOT EXISTS idx_v_state ON verifications(verification_state);
CREATE INDEX IF NOT EXISTS idx_v_confidence ON verifications(confidence);
CREATE INDEX IF NOT EXISTS idx_vh_entity ON verification_history(entity_id);
"""


class VerificationStorage:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def initialize_tables(self) -> None:
        conn = self._get_conn()
        conn.executescript(VERIFICATION_SCHEMA_SQL)
        conn.commit()

    def save(self, record: VerificationRecord) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO verifications
               (verification_id, entity_id, entity_type, verification_state, operational_state,
                confidence, consensus, contradiction, source_count, human_review_boost,
                matched_rules, reasoning, computation_steps, version, is_high_impact,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.verification_id,
                record.entity_id,
                record.entity_type,
                record.verification_state.name_lower,
                record.operational_state.name_lower,
                record.confidence,
                record.consensus,
                record.contradiction,
                record.source_count,
                record.human_review_boost,
                _serialize(record.matched_rules),
                record.reasoning,
                _serialize(record.computation_steps),
                record.version,
                1 if record.is_high_impact else 0,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            ),
        )
        conn.commit()

    def save_history(self, record: VerificationRecord, operation: str) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO verification_history
               (verification_id, version, entity_id, verification_state, operational_state,
                confidence, reasoning, created_at, operation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.verification_id,
                record.version,
                record.entity_id,
                record.verification_state.name_lower,
                record.operational_state.name_lower,
                record.confidence,
                record.reasoning,
                datetime.now(UTC).isoformat(),
                operation,
            ),
        )
        conn.commit()

    def load(self, entity_id: str) -> VerificationRecord | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM verifications WHERE entity_id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def load_all(self) -> list[VerificationRecord]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM verifications").fetchall()
        return [self._row_to_record(r) for r in rows]

    def load_history(self, entity_id: str) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM verification_history WHERE entity_id = ? ORDER BY version DESC",
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, entity_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM verifications WHERE entity_id = ?", (entity_id,))
        conn.execute("DELETE FROM verification_history WHERE entity_id = ?", (entity_id,))
        conn.commit()

    def _get_conn(self) -> Any:
        conn = getattr(self._backend, "_conn", None)
        if conn is None:
            raise RuntimeError("Storage not connected")
        return conn

    @staticmethod
    def _row_to_record(row: Any) -> VerificationRecord:
        d = dict(row)
        return VerificationRecord(
            verification_id=d.get("verification_id", ""),
            entity_id=d.get("entity_id", ""),
            entity_type=d.get("entity_type", ""),
            verification_state=VerificationState[d["verification_state"].upper()],
            operational_state=OperationalState[d["operational_state"].upper()],
            confidence=d.get("confidence", 0.0),
            consensus=d.get("consensus", 0.0),
            contradiction=d.get("contradiction", 0.0),
            source_count=d.get("source_count", 0),
            human_review_boost=d.get("human_review_boost", 0.0),
            matched_rules=_deserialize(d.get("matched_rules", "[]")),
            reasoning=d.get("reasoning", ""),
            computation_steps=_deserialize(d.get("computation_steps", "[]")),
            version=d.get("version", 1),
            is_high_impact=bool(d.get("is_high_impact", 0)),
            created_at=datetime.fromisoformat(d["created_at"]),
            updated_at=datetime.fromisoformat(d["updated_at"]),
        )


def _serialize(obj: object) -> str:
    return json.dumps(obj, default=str) if obj else "[]"


def _deserialize(s: str) -> Any:
    try:
        return json.loads(s) if s else []
    except (json.JSONDecodeError, ValueError):
        return []
