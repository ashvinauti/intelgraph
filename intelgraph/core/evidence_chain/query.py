from typing import Any

from intelgraph.core.evidence_chain.base import EvidenceChain, EvidenceStatus


class ChainQueryEngine:
    def __init__(self, chains: dict[str, EvidenceChain] | None = None) -> None:
        self._chains = chains or {}

    def get_chain(self, chain_id: str) -> EvidenceChain | None:
        return self._chains.get(chain_id)

    def get_chain_by_entity(self, entity_id: str) -> EvidenceChain | None:
        for chain in self._chains.values():
            if chain.entity_id == entity_id:
                return chain
        return None

    def list_chains(
        self,
        status: EvidenceStatus | None = None,
        min_confidence: float | None = None,
        max_confidence: float | None = None,
        min_contradiction: float | None = None,
        has_contradictions: bool | None = None,
        limit: int = 100,
    ) -> list[EvidenceChain]:
        result = list(self._chains.values())

        if status is not None:
            result = [c for c in result if c.status == status]
        if min_confidence is not None:
            result = [c for c in result if c.confidence >= min_confidence]
        if max_confidence is not None:
            result = [c for c in result if c.confidence <= max_confidence]
        if min_contradiction is not None:
            result = [c for c in result if c.contradiction_score >= min_contradiction]
        if has_contradictions is not None:
            if has_contradictions:
                result = [c for c in result if c.contradiction_score > 0]
            else:
                result = [c for c in result if c.contradiction_score == 0]

        return result[:limit]

    def rank_by_confidence(self, chains: list[EvidenceChain] | None = None) -> list[EvidenceChain]:
        targets = chains or list(self._chains.values())
        return sorted(targets, key=lambda c: c.confidence, reverse=True)

    def rank_by_source_count(
        self, chains: list[EvidenceChain] | None = None
    ) -> list[EvidenceChain]:
        targets = chains or list(self._chains.values())
        return sorted(targets, key=lambda c: c.source_count, reverse=True)

    def rank_by_consensus(self, chains: list[EvidenceChain] | None = None) -> list[EvidenceChain]:
        targets = chains or list(self._chains.values())
        return sorted(
            targets,
            key=lambda c: c.confidence * (1.0 - c.contradiction_score / 100.0),
            reverse=True,
        )

    def get_contradictions(self) -> list[EvidenceChain]:
        return [
            c
            for c in self._chains.values()
            if c.contradiction_score > 0 and c.status == EvidenceStatus.CONTESTED
        ]

    def stats(self) -> dict[str, Any]:
        chains = list(self._chains.values())
        if not chains:
            return {"total": 0}

        verified = sum(1 for c in chains if c.status == EvidenceStatus.VERIFIED)
        contested = sum(1 for c in chains if c.status == EvidenceStatus.CONTESTED)
        unknown = sum(1 for c in chains if c.status == EvidenceStatus.UNKNOWN)
        debunked = sum(1 for c in chains if c.status == EvidenceStatus.DEBUNKED)

        return {
            "total": len(chains),
            "verified": verified,
            "contested": contested,
            "unknown": unknown,
            "debunked": debunked,
            "avg_confidence": (
                round(sum(c.confidence for c in chains) / len(chains), 2) if chains else 0.0
            ),
            "avg_contradiction": (
                round(sum(c.contradiction_score for c in chains) / len(chains), 2)
                if chains
                else 0.0
            ),
            "multi_source_chains": sum(1 for c in chains if c.source_count >= 2),
            "single_source_chains": sum(1 for c in chains if c.source_count < 2),
        }
