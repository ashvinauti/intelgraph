from datetime import UTC, datetime
from typing import Any

from intelgraph.core.evidence_chain import ChainManager
from intelgraph.core.human_review.base import ReviewOutcome, ReviewRecord
from intelgraph.core.human_review.queue import ReviewQueue
from intelgraph.core.human_review.review import ReviewEngine
from intelgraph.core.human_review.thresholds import ReviewThresholds, ThresholdResult

REVIEW_TABLE_SQL = """

CREATE TABLE IF NOT EXISTS review_records (
    review_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    entity_type TEXT,
    outcome TEXT NOT NULL,
    reviewer TEXT,
    review_notes TEXT,
    confidence_influence REAL DEFAULT 0.0,
    contradiction_influence REAL DEFAULT 0.0,
    previous_chain_confidence REAL DEFAULT 0.0,
    new_chain_confidence REAL DEFAULT 0.0,
    previous_chain_version INTEGER DEFAULT 0,
    new_chain_version INTEGER DEFAULT 0,
    source_evidence_ids TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_rr_entity ON review_records(entity_id);
CREATE INDEX IF NOT EXISTS idx_rr_outcome ON review_records(outcome);
"""


class ReviewManager:
    def __init__(self, storage_backend: Any) -> None:
        self._storage = storage_backend
        self._chain_mgr = ChainManager(storage_backend)
        self._queue = ReviewQueue(storage_backend)
        self._engine = ReviewEngine()
        self._thresholds = ReviewThresholds()

    def initialize(self) -> None:
        self._chain_mgr.initialize()
        self._queue.initialize_tables()
        conn = self._get_conn()
        conn.executescript(REVIEW_TABLE_SQL)
        conn.commit()

    def evaluate(self, entity_id: str) -> ThresholdResult:
        chain = self._chain_mgr.get_chain_by_entity(entity_id)
        if chain is None:
            return ThresholdResult(
                needs_review=True,
                reason="No evidence chain exists for this entity",
                suggested_action="needs_more_evidence",
            )
        return self._thresholds.evaluate(
            confidence=chain.confidence,
            source_count=chain.source_count,
            contradiction_score=chain.contradiction_score,
            single_source=chain.source_count < 2,
        )

    def enqueue_for_review(self, entity_id: str, entity_type: str = "") -> str | None:
        threshold = self.evaluate(entity_id)
        if not threshold.needs_review:
            return None
        chain = self._chain_mgr.get_chain_by_entity(entity_id)
        confidence = chain.confidence if chain else 0.0
        return self._queue.enqueue(entity_id, entity_type, threshold.reason, confidence)

    def process_review(
        self,
        entity_id: str,
        outcome: ReviewOutcome,
        reviewer: str = "",
        notes: str = "",
        queue_id: str | None = None,
    ) -> ReviewRecord:
        chain = self._chain_mgr.get_chain_by_entity(entity_id)
        if chain is None:
            raise ValueError(f"No evidence chain for entity {entity_id}")

        influence = self._engine.compute_influence(outcome, chain.confidence)
        prev_conf = chain.confidence
        prev_version = chain.version

        self._engine.apply_influence(chain, influence)

        record = ReviewRecord(
            entity_id=entity_id,
            entity_type=chain.entity_id.split("-")[0] if "-" in chain.entity_id else "",
            outcome=outcome,
            reviewer=reviewer,
            review_notes=notes,
            confidence_influence=influence.confidence_delta,
            contradiction_influence=influence.contradiction_delta,
            previous_chain_confidence=prev_conf,
            new_chain_confidence=chain.confidence,
            previous_chain_version=prev_version,
            new_chain_version=chain.version,
            reviewed_at=datetime.now(UTC),
        )

        self._persist_record(record)
        self._chain_mgr._storage.save_chain(chain)
        self._chain_mgr._storage.save_chain_version(chain, f"HUMAN_REVIEW_{outcome.name}")

        if queue_id:
            self._queue.complete(queue_id, outcome)

        self._log_audit(record)
        return record

    def get_reviews(self, entity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._get_conn()
        if entity_id:
            rows = conn.execute(
                "SELECT * FROM review_records WHERE entity_id = ? ORDER BY created_at DESC LIMIT ?",
                (entity_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM review_records ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_pending_reviews(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._queue.list_pending(limit)

    def review_stats(self) -> dict[str, int]:
        queue_stats = self._queue.queue_stats()
        conn = self._get_conn()
        approved = conn.execute(
            "SELECT COUNT(*) as c FROM review_records WHERE outcome = 'approved_review'"
        ).fetchone()["c"]
        rejected = conn.execute(
            "SELECT COUNT(*) as c FROM review_records WHERE outcome = 'rejected_review'"
        ).fetchone()["c"]
        needs_more = conn.execute(
            "SELECT COUNT(*) as c FROM review_records WHERE outcome = 'needs_more_evidence'"
        ).fetchone()["c"]
        return {
            "queue": queue_stats,
            "total_reviewed": approved + rejected + needs_more,
            "approved": approved,
            "rejected": rejected,
            "needs_more_evidence": needs_more,
        }

    def _persist_record(self, record: ReviewRecord) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO review_records
               (review_id, entity_id, entity_type, outcome, reviewer, review_notes,
                confidence_influence, contradiction_influence,
                previous_chain_confidence, new_chain_confidence,
                previous_chain_version, new_chain_version,
                source_evidence_ids, created_at, reviewed_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.review_id,
                record.entity_id,
                record.entity_type,
                record.outcome.name_lower,
                record.reviewer,
                record.review_notes,
                record.confidence_influence,
                record.contradiction_influence,
                record.previous_chain_confidence,
                record.new_chain_confidence,
                record.previous_chain_version,
                record.new_chain_version,
                _serialize(record.source_evidence_ids),
                record.created_at.isoformat(),
                record.reviewed_at.isoformat() if record.reviewed_at else None,
                _serialize(record.metadata),
            ),
        )
        conn.commit()

    def _log_audit(self, record: ReviewRecord) -> None:
        try:
            self._storage.write_audit(
                {
                    "id": str(__import__("ulid").new()),
                    "entity_id": record.entity_id,
                    "entity_type": record.entity_type,
                    "operation": f"HUMAN_REVIEW_{record.outcome.name}",
                    "old_data": _serialize({"confidence": record.previous_chain_confidence}),
                    "new_data": _serialize(
                        {
                            "confidence": record.new_chain_confidence,
                            "outcome": record.outcome.name_lower,
                        }
                    ),
                    "actor": record.reviewer,
                    "correlation_id": record.review_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except Exception:
            pass

    def _get_conn(self) -> Any:
        conn = getattr(self._storage, "_conn", None)
        if conn is None:
            raise RuntimeError("Storage not connected")
        return conn


def _serialize(obj: object) -> str:
    import json

    return json.dumps(obj, default=str) if obj else ""
