from dataclasses import dataclass

from intelgraph.core.constants import (
    APPROVED_CONFIDENCE_BOOST,
    APPROVED_CONTRADICTION_REDUCTION,
    NEEDS_MORE_NO_CHANGE,
    REJECTED_CONFIDENCE_PENALTY,
    REJECTED_CONTRADICTION_INCREASE,
)
from intelgraph.core.evidence_chain import EvidenceChain
from intelgraph.core.human_review.base import ReviewOutcome


@dataclass
class ReviewInfluence:
    confidence_delta: float = 0.0
    contradiction_delta: float = 0.0
    description: str = ""


class ReviewEngine:
    APPROVED_CONFIDENCE_BOOST: float = APPROVED_CONFIDENCE_BOOST
    APPROVED_CONTRADICTION_REDUCTION: float = APPROVED_CONTRADICTION_REDUCTION
    REJECTED_CONFIDENCE_PENALTY: float = REJECTED_CONFIDENCE_PENALTY
    REJECTED_CONTRADICTION_INCREASE: float = REJECTED_CONTRADICTION_INCREASE
    NEEDS_MORE_NO_CHANGE: float = NEEDS_MORE_NO_CHANGE

    @staticmethod
    def compute_influence(outcome: ReviewOutcome, current_confidence: float) -> ReviewInfluence:
        if outcome == ReviewOutcome.APPROVED_REVIEW:
            return ReviewInfluence(
                confidence_delta=ReviewEngine.APPROVED_CONFIDENCE_BOOST,
                contradiction_delta=-ReviewEngine.APPROVED_CONTRADICTION_REDUCTION,
                description=f"Human review approved: +{ReviewEngine.APPROVED_CONFIDENCE_BOOST} confidence, -{ReviewEngine.APPROVED_CONTRADICTION_REDUCTION} contradiction",
            )
        elif outcome == ReviewOutcome.REJECTED_REVIEW:
            return ReviewInfluence(
                confidence_delta=-ReviewEngine.REJECTED_CONFIDENCE_PENALTY,
                contradiction_delta=ReviewEngine.REJECTED_CONTRADICTION_INCREASE,
                description=f"Human review rejected: -{ReviewEngine.REJECTED_CONFIDENCE_PENALTY} confidence, +{ReviewEngine.REJECTED_CONTRADICTION_INCREASE} contradiction",
            )
        else:
            return ReviewInfluence(
                confidence_delta=0.0,
                contradiction_delta=0.0,
                description="Human review requested more evidence: no immediate confidence change",
            )

    @staticmethod
    def apply_influence(chain: EvidenceChain, influence: ReviewInfluence) -> EvidenceChain:
        new_conf = chain.confidence + influence.confidence_delta
        new_contra = chain.contradiction_score + influence.contradiction_delta

        chain.confidence = max(0.0, min(100.0, round(new_conf, 2)))
        chain.contradiction_score = max(0.0, min(100.0, round(new_contra, 2)))
        chain.version += 1
        return chain
