from typing import Any

from intelgraph.core.constants import (
    HUMAN_REVIEW_APPROVED_BOOST,
    HUMAN_REVIEW_REJECTED_PENALTY,
)
from intelgraph.core.evidence_chain import ChainManager
from intelgraph.core.human_review import ReviewManager
from intelgraph.core.verification.base import VerificationRecord, VerificationState
from intelgraph.core.verification.engine import VerificationEngine
from intelgraph.core.verification.high_impact import HighImpactHandler
from intelgraph.core.verification.safety import SafetyChecker, SafetyReport
from intelgraph.core.verification.storage import VerificationStorage


class VerificationManager:
    def __init__(self, storage_backend: Any) -> None:
        self._storage = VerificationStorage(storage_backend)
        self._engine = VerificationEngine()
        self._chain_mgr = ChainManager(storage_backend)
        self._review_mgr = ReviewManager(storage_backend)
        self._high_impact = HighImpactHandler()
        self._safety = SafetyChecker()

    def initialize(self) -> None:
        self._chain_mgr.initialize()
        self._review_mgr.initialize()
        self._storage.initialize_tables()

    def get_verification(self, entity_id: str) -> VerificationRecord | None:
        return self._storage.load(entity_id)

    def list_verifications(
        self,
        status: str | None = None,
        operational: str | None = None,
        min_confidence: float | None = None,
        high_impact_only: bool = False,
    ) -> list[dict[str, Any]]:
        records = self._storage.load_all()
        if status:
            records = [r for r in records if r.verification_state.name_lower == status.lower()]
        if operational:
            records = [r for r in records if r.operational_state.name_lower == operational.lower()]
        if min_confidence is not None:
            records = [r for r in records if r.confidence >= min_confidence]
        if high_impact_only:
            records = [r for r in records if r.is_high_impact]
        return [r.to_dict() for r in records]

    def recompute(self, entity_id: str) -> VerificationRecord | None:
        chain = self._chain_mgr.get_chain_by_entity(entity_id)
        if chain is None:
            return None

        evidence_item_confidences: list[float] = (
            [e.confidence for e in chain.evidence] if chain.evidence else [0.0]
        )
        # Use flat default trust score (50) for all sources — source-level trust
        # belongs in SourceRegistryService, not in EvidenceItem.confidence
        source_trust_scores = [50 for _ in chain.evidence] if chain.evidence else [50]

        source_domains: list[str] = []
        for e in chain.evidence:
            src = e.source_id
            if src.startswith("http"):
                source_domains.append(src)

        consensus = _compute_consensus(evidence_item_confidences)
        contradiction = chain.contradiction_score
        source_count = chain.source_count
        human_review_boost = self._get_human_review_boost(entity_id)

        existing = self._storage.load(entity_id)
        previous_confidence = existing.confidence if existing else 0.0

        is_high = self._high_impact.is_high_impact(
            entity_type=entity_id.split("-")[0] if "-" in entity_id else "",
            name=entity_id,
        )

        result = self._engine.compute(
            confidence=chain.confidence,
            consensus=consensus,
            contradiction=contradiction,
            source_count=source_count,
            source_trust_scores=source_trust_scores,
            human_review_boost=human_review_boost,
            is_high_impact=is_high,
        )

        safety = self._safety.full_check(
            source_trust_scores=source_trust_scores,
            source_domains=source_domains,
            contradiction=contradiction,
            verification_state=result.verification_state.name_lower,
            previous_confidence=previous_confidence,
            new_confidence=chain.confidence,
        )

        version = (existing.version + 1) if existing else 1
        record = VerificationRecord(
            entity_id=entity_id,
            entity_type=entity_id.split("-")[0] if "-" in entity_id else "",
            verification_state=result.verification_state,
            operational_state=result.operational_state,
            confidence=chain.confidence,
            consensus=consensus,
            contradiction=contradiction,
            source_count=source_count,
            human_review_boost=human_review_boost,
            matched_rules=result.matched_rules,
            reasoning=result.reasoning,
            computation_steps=result.computation_steps,
            version=version,
            is_high_impact=is_high,
        )

        self._storage.save(record)
        self._storage.save_history(record, "RECOMPUTE")

        if not safety.is_safe:
            self._log_safety_warning(entity_id, safety)

        if is_high and result.verification_state != VerificationState.CONFIRMED:
            self._queue_high_impact_review(entity_id)

        return record

    def recompute_all(self) -> int:
        records = self._storage.load_all()
        count = 0
        for r in records:
            try:
                self.recompute(r.entity_id)
                count += 1
            except Exception:
                pass
        return count

    def get_high_impact_unverified(self) -> list[dict[str, Any]]:
        records = self._storage.load_all()
        return [
            r.to_dict()
            for r in records
            if r.is_high_impact and r.verification_state != VerificationState.CONFIRMED
        ]

    def stats(self) -> dict[str, Any]:
        records = self._storage.load_all()
        if not records:
            return {"total": 0}

        confirmed = sum(1 for r in records if r.verification_state == VerificationState.CONFIRMED)
        probable = sum(1 for r in records if r.verification_state == VerificationState.PROBABLE)
        possible = sum(1 for r in records if r.verification_state == VerificationState.POSSIBLE)
        speculative = sum(
            1 for r in records if r.verification_state == VerificationState.SPECULATIVE
        )
        contested = sum(1 for r in records if r.operational_state.name_lower == "contested")
        debunked = sum(1 for r in records if r.operational_state.name_lower == "debunked")
        high_impact_unverified = len(self.get_high_impact_unverified())

        return {
            "total": len(records),
            "confirmed": confirmed,
            "probable": probable,
            "possible": possible,
            "speculative": speculative,
            "contested": contested,
            "debunked": debunked,
            "high_impact_unverified": high_impact_unverified,
            "avg_confidence": (
                round(sum(r.confidence for r in records) / len(records), 2) if records else 0.0
            ),
        }

    def get_history(self, entity_id: str) -> list[dict[str, Any]]:
        return self._storage.load_history(entity_id)

    def update_state(
        self,
        entity_id: str,
        verification_state: str | None = None,
        operational_state: str | None = None,
        reasoning: str = "",
    ) -> VerificationRecord | None:
        record = self._storage.load(entity_id)
        if record is None:
            return None
        from intelgraph.core.verification.base import OperationalState, VerificationState

        if verification_state:
            record.verification_state = VerificationState[verification_state.upper()]
        if operational_state:
            record.operational_state = OperationalState[operational_state.upper()]
        if reasoning:
            record.reasoning = reasoning
        self._storage.save(record)
        self._storage.save_history(record, "MANUAL_SET")
        return record

    def get_chain_by_entity(self, entity_id: str) -> dict[str, Any] | None:
        chain = self._chain_mgr.get_chain_by_entity(entity_id)
        if chain is None:
            return None
        return chain.to_dict()

    def _get_human_review_boost(self, entity_id: str) -> float:
        try:
            reviews = self._review_mgr.get_reviews(entity_id, limit=10)
            boost = 0.0
            for r in reviews:
                if r.get("outcome") == "approved_review":
                    boost += HUMAN_REVIEW_APPROVED_BOOST
                elif r.get("outcome") == "rejected_review":
                    boost -= HUMAN_REVIEW_REJECTED_PENALTY
            return boost
        except Exception:
            return 0.0

    def _queue_high_impact_review(self, entity_id: str) -> None:
        try:
            self._review_mgr.enqueue_for_review(entity_id, "high_impact")
        except Exception:
            pass

    def _log_safety_warning(self, entity_id: str, safety: SafetyReport) -> None:
        try:
            self._review_mgr._get_conn()
        except Exception:
            pass


def _compute_consensus(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0] * 0.5
    mean = sum(values) / len(values)
    deviations = sum(abs(v - mean) for v in values) / len(values)
    agreement = 1.0 - (deviations / 100.0)
    return round(mean * (0.5 + agreement * 0.5), 2)
