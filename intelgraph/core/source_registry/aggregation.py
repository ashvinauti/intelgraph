from typing import Any

from intelgraph.core.source_registry.consensus import ConsensusScorer
from intelgraph.core.source_registry.decay import TrustDecayModel


class TrustAggregator:
    def __init__(self) -> None:
        self._decay = TrustDecayModel()

    def aggregate(
        self,
        source_records: list[dict[str, Any]],
        apply_decay: bool = True,
    ) -> dict[str, Any]:
        if not source_records:
            return {
                "aggregated_trust": 0,
                "aggregated_reliability": 0,
                "source_count": 0,
                "tier_distribution": {1: 0, 2: 0, 3: 0},
                "consensus_score": 0.0,
                "agreement_ratio": 0.0,
                "weight": 0.0,
            }

        processed = []
        if apply_decay:
            for record in source_records:
                processed.append(self._decay.apply_decay(dict(record)))
        else:
            processed = [dict(r) for r in source_records]

        trust_scores = [r.get("trust_score", 0) for r in processed]
        reliability_scores = [r.get("reliability_score", 50) for r in processed]
        tiers = [r.get("source_tier", 3) for r in processed]

        tier_dist = {1: tiers.count(1), 2: tiers.count(2), 3: tiers.count(3)}

        consensus = ConsensusScorer.evaluate(trust_scores, reliability_scores)

        weighted_trust = 0.0
        total_rel = 0.0
        for t, r in zip(trust_scores, reliability_scores, strict=False):
            weighted_trust += t * r
            total_rel += r
        aggregated_trust = round(weighted_trust / total_rel) if total_rel > 0 else 0

        aggregated_reliability = round(sum(reliability_scores) / len(reliability_scores))

        boost = ConsensusScorer.agreement_boost(len(trust_scores), consensus.agreement_ratio)
        final_trust = min(100, round(aggregated_trust * boost))

        return {
            "aggregated_trust": final_trust,
            "aggregated_reliability": aggregated_reliability,
            "source_count": len(source_records),
            "tier_distribution": tier_dist,
            "consensus_score": round(consensus.consensus_score, 2),
            "agreement_ratio": round(consensus.agreement_ratio, 4),
            "weight": round(consensus.weight, 4),
            "boost_factor": round(boost, 4),
        }
