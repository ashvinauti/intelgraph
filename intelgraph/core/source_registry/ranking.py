from typing import Any

from intelgraph.core.source_registry.decay import TrustDecayModel


class SourceRanking:
    def __init__(self) -> None:
        self._decay = TrustDecayModel()

    def rank(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scored = []
        for src in sources:
            decayed = self._decay.apply_decay(dict(src))
            score = self._composite_score(decayed)
            decayed["_composite_score"] = round(score, 4)
            scored.append(decayed)
        scored.sort(key=lambda x: x["_composite_score"], reverse=True)
        return scored

    @staticmethod
    def query(
        sources: list[dict[str, Any]],
        min_trust: int | None = None,
        max_trust: int | None = None,
        tier: int | None = None,
        domain: str | None = None,
        verified_only: bool = False,
    ) -> list[dict[str, Any]]:
        result = list(sources)
        if min_trust is not None:
            result = [s for s in result if s.get("trust_score", 0) >= min_trust]
        if max_trust is not None:
            result = [s for s in result if s.get("trust_score", 0) <= max_trust]
        if tier is not None:
            result = [s for s in result if s.get("source_tier") == tier]
        if domain is not None:
            result = [s for s in result if domain in s.get("source_url", "")]
        if verified_only:
            result = [s for s in result if s.get("last_validated")]
        return result

    def _composite_score(self, record: dict[str, Any]) -> float:
        trust = record.get("trust_score", 0)
        reliability = record.get("reliability_score", 50)
        tier = record.get("source_tier", 3)
        validation_count = record.get("validation_count", 0)

        tier_bonus = {1: 10, 2: 5, 3: 0}.get(tier, 0)
        validation_bonus = min(validation_count * 2, 10)

        return (trust * 0.5) + (reliability * 0.3) + tier_bonus + validation_bonus
