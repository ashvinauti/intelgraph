from typing import Any

from intelgraph.core.evidence_chain.base import (
    EvidenceChain,
    EvidenceItem,
    EvidenceStatus,
    SupportType,
)


class ConfidenceComputer:
    @staticmethod
    def compute(chain: EvidenceChain, source_trust_map: dict[str, int] | None = None) -> float:
        if not chain.evidence:
            chain.confidence = 0.0
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0
        explanation: list[dict[str, Any]] = []

        # Only non-NEUTRAL evidence participates in the weighted average.
        # NEUTRAL evidence is "no opinion" — it provides context but doesn't
        # affect the confidence score directly.
        opinion_items = [e for e in chain.evidence if e.support_type != SupportType.NEUTRAL]

        for item in opinion_items:
            base_conf = item.confidence
            source_trust = (source_trust_map or {}).get(item.source_id, 50)
            weight = source_trust / 100.0
            adjusted = base_conf * weight
            weighted_sum += adjusted
            total_weight += weight
            explanation.append(
                {
                    "evidence_id": item.evidence_id,
                    "base_confidence": base_conf,
                    "source_trust": source_trust,
                    "weight": round(weight, 4),
                    "adjusted": round(adjusted, 2),
                }
            )

        base_aggregated = weighted_sum / total_weight if total_weight > 0 else 0.0

        supports = [e for e in opinion_items if e.support_type == SupportType.SUPPORTS]
        contradicts = [e for e in opinion_items if e.support_type == SupportType.CONTRADICTS]
        n = len(opinion_items)
        n_supports = len(supports)
        n_contradicts = len(contradicts)

        agreement_ratio = n_supports / n if n > 0 else 0.0
        contradiction_ratio = n_contradicts / n if n > 0 else 0.0

        consensus_boost = 0.0
        if agreement_ratio > 0.7 and n >= 2:
            consensus_boost = base_aggregated * 0.1

        contradiction_penalty = 0.0
        if contradiction_ratio > 0.3:
            contra_score = min(chain.contradiction_score, 100.0)
            contradiction_penalty = base_aggregated * (contra_score / 300.0)

        final = base_aggregated + consensus_boost - contradiction_penalty
        final = max(0.0, min(100.0, round(final, 2)))

        chain.confidence = final
        # Note: chain.contradiction_score is set by ContradictionDetector.detect(),
        # not here — compute() only reads it for the penalty calculation.

        if n_contradicts > n_supports and n >= 2:
            chain.status = EvidenceStatus.CONTESTED
        elif final >= 80.0 and n >= 2:
            chain.status = EvidenceStatus.VERIFIED
        elif final < 20.0:
            chain.status = EvidenceStatus.DEBUNKED
        else:
            chain.status = EvidenceStatus.UNKNOWN

        return final

    @staticmethod
    def compute_from_items(
        items: list[EvidenceItem],
        source_trust_map: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        from intelgraph.core.evidence_chain.base import EvidenceChain

        chain = EvidenceChain(evidence=list(items))
        conf = ConfidenceComputer.compute(chain, source_trust_map)
        return {
            "confidence": conf,
            "contradiction_score": chain.contradiction_score,
            "status": chain.status.name_lower,
            "evidence_count": len(items),
            "source_count": len({e.source_id for e in items}),
        }
