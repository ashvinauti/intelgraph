from dataclasses import dataclass, field
from datetime import UTC, datetime

import ulid

from intelgraph.core.evidence_chain.base import EvidenceChain, EvidenceItem, SupportType


@dataclass
class ContradictionRecord:
    id: str = field(default_factory=lambda: str(ulid.new()))
    chain_id: str = ""
    evidence_id_a: str = ""
    evidence_id_b: str = ""
    contradiction_type: str = ""
    score: float = 0.0
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolution: str = ""


class ContradictionDetector:
    def __init__(self) -> None:
        self._records: list[ContradictionRecord] = []

    def detect(self, chain: EvidenceChain, existing_count: int = 0) -> list[ContradictionRecord]:
        self._records = []
        chain.contradiction_score = 0.0  # reset — recomputed from scratch each call
        items = chain.evidence
        n = len(items)

        if 0 < existing_count < n:
            # Incremental mode: only compare NEW items (from existing_count onwards)
            # with ALL items, avoiding re-comparison of already-compared pairs.
            for i in range(existing_count, n):
                for j in range(n):
                    if i == j:
                        continue
                    record = self._compare(items[i], items[j], chain.chain_id)
                    if record is not None:
                        self._records.append(record)
        else:
            # Full scan mode: compare all pairs (first call or reset)
            for i in range(n):
                for b in items[i + 1 :]:
                    record = self._compare(items[i], b, chain.chain_id)
                    if record is not None:
                        self._records.append(record)

        if self._records:
            new_max = max(r.score for r in self._records)
            chain.contradiction_score = max(chain.contradiction_score, new_max)

        return list(self._records)

    def _compare(
        self, a: EvidenceItem, b: EvidenceItem, chain_id: str
    ) -> ContradictionRecord | None:
        # NEUTRAL evidence has "no opinion" — it can't contradict or be contradicted.
        if a.support_type == SupportType.NEUTRAL or b.support_type == SupportType.NEUTRAL:
            return None

        if a.support_type != b.support_type:
            return self._direct_contradiction(a, b, chain_id)

        if a.claim.strip().lower() == b.claim.strip().lower():
            return None

        if self._claims_conflict(a.claim, b.claim):
            return self._partial_conflict(a, b, chain_id)

        return None

    def _direct_contradiction(
        self, a: EvidenceItem, b: EvidenceItem, chain_id: str
    ) -> ContradictionRecord:
        return ContradictionRecord(
            chain_id=chain_id,
            evidence_id_a=a.evidence_id,
            evidence_id_b=b.evidence_id,
            contradiction_type="direct",
            score=100.0,
        )

    def _partial_conflict(
        self, a: EvidenceItem, b: EvidenceItem, chain_id: str
    ) -> ContradictionRecord | None:
        words_a = set(a.claim.lower().split())
        words_b = set(b.claim.lower().split())
        if not words_a or not words_b:
            return None

        jaccard = len(words_a & words_b) / len(words_a | words_b)
        if jaccard < 0.3:
            return None

        conflict_score = round((1.0 - jaccard) * 100.0, 2)
        if conflict_score < 20.0:
            return None

        ctype = "partial"
        if conflict_score >= 70:
            ctype = "direct"

        return ContradictionRecord(
            chain_id=chain_id,
            evidence_id_a=a.evidence_id,
            evidence_id_b=b.evidence_id,
            contradiction_type=ctype,
            score=conflict_score,
        )

    @staticmethod
    def _claims_conflict(claim_a: str, claim_b: str) -> bool:
        if not claim_a or not claim_b:
            return False
        return claim_a.strip().lower() != claim_b.strip().lower()

    @property
    def records(self) -> list[ContradictionRecord]:
        return list(self._records)
