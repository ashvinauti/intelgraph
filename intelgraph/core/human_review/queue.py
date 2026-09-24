from datetime import UTC, datetime
from typing import Any

import ulid

from intelgraph.core.human_review.base import ReviewOutcome


class ReviewQueue:
    def __init__(self, storage_backend: Any) -> None:
        self._storage = storage_backend

    def initialize_tables(self) -> None:
        conn = self._get_conn()
        conn.executescript(REVIEW_QUEUE_SQL)
        conn.commit()

    def enqueue(
        self, entity_id: str, entity_type: str, reason: str, chain_confidence: float
    ) -> str:
        queue_id = str(ulid.new())
        now = datetime.now(UTC).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO review_queue
               (queue_id, entity_id, entity_type, reason, chain_confidence, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (queue_id, entity_id, entity_type, reason, chain_confidence, now, now),
        )
        conn.commit()
        return queue_id

    def dequeue(self, queue_id: str, reviewer: str) -> dict[str, Any] | None:
        conn = self._get_conn()
        now = datetime.now(UTC).isoformat()
        row = conn.execute(
            "SELECT * FROM review_queue WHERE queue_id = ? AND status = 'pending'",
            (queue_id,),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE review_queue SET status = 'in_review', reviewer = ?, updated_at = ? WHERE queue_id = ?",
            (reviewer, now, queue_id),
        )
        conn.commit()
        return dict(row)

    def complete(self, queue_id: str, outcome: ReviewOutcome) -> None:
        conn = self._get_conn()
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "UPDATE review_queue SET status = ?, updated_at = ? WHERE queue_id = ?",
            (outcome.name_lower, now, queue_id),
        )
        conn.commit()

    def list_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM review_queue WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_entity(self, entity_id: str) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM review_queue WHERE entity_id = ? ORDER BY created_at DESC",
            (entity_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def queue_stats(self) -> dict[str, int]:
        conn = self._get_conn()
        pending = conn.execute(
            "SELECT COUNT(*) as c FROM review_queue WHERE status = 'pending'"
        ).fetchone()["c"]
        in_review = conn.execute(
            "SELECT COUNT(*) as c FROM review_queue WHERE status = 'in_review'"
        ).fetchone()["c"]
        completed = conn.execute(
            "SELECT COUNT(*) as c FROM review_queue WHERE status != 'pending' AND status != 'in_review'"
        ).fetchone()["c"]
        return {
            "pending": pending,
            "in_review": in_review,
            "completed": completed,
            "total": pending + in_review + completed,
        }

    def _get_conn(self) -> Any:
        conn = getattr(self._storage, "_conn", None)
        if conn is None:
            raise RuntimeError("Storage not connected")
        return conn


REVIEW_QUEUE_SQL = """

CREATE TABLE IF NOT EXISTS review_queue (
    queue_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    reason TEXT,
    chain_confidence REAL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rq_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_rq_entity ON review_queue(entity_id);
"""
