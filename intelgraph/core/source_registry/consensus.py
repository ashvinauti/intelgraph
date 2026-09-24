from dataclasses import dataclass


@dataclass
class AgreementResult:
    source_count: int = 0
    agreement_ratio: float = 0.0
    consensus_score: float = 0.0
    weight: float = 0.0


class ConsensusScorer:
    @staticmethod
    def evaluate(
        source_trust_scores: list[int],
        source_reliability_scores: list[int] | None = None,
    ) -> AgreementResult:
        n = len(source_trust_scores)
        if n == 0:
            return AgreementResult()

        reliabilities = source_reliability_scores or [50] * n

        total_weight = sum(r for r in reliabilities) or 1
        weighted_sum = sum(t * r for t, r in zip(source_trust_scores, reliabilities, strict=False))
        consensus_score = weighted_sum / total_weight

        if n == 1:
            agreement_ratio = 0.5
        else:
            mean_score = sum(source_trust_scores) / n
            deviations = [abs(s - mean_score) for s in source_trust_scores]
            max_dev = 100.0
            avg_dev = sum(deviations) / n
            agreement_ratio = 1.0 - (avg_dev / max_dev)

        weight = agreement_ratio * (1 - 1.0 / (n + 1))

        return AgreementResult(
            source_count=n,
            agreement_ratio=round(agreement_ratio, 4),
            consensus_score=round(consensus_score, 2),
            weight=round(weight, 4),
        )

    @staticmethod
    def agreement_boost(count: int, agreement_ratio: float) -> float:
        if count < 2:
            return 1.0
        return 1.0 + (agreement_ratio * min(count - 1, 5) * 0.05)

    @staticmethod
    def contradiction_penalty(count: int, agreement_ratio: float) -> float:
        if count < 2:
            return 0.0
        if agreement_ratio >= 0.8:
            return 0.0
        return (1.0 - agreement_ratio) * min(count, 5) * 0.1
