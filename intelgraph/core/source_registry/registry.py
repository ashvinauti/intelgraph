from datetime import UTC, datetime
from typing import Any

import ulid

from intelgraph.core.source_registry.aggregation import TrustAggregator
from intelgraph.core.source_registry.anti_poisoning import AntiPoisoningEngine
from intelgraph.core.source_registry.consensus import ConsensusScorer
from intelgraph.core.source_registry.decay import TrustDecayModel
from intelgraph.core.source_registry.ranking import SourceRanking
from intelgraph.core.source_registry.scoring import TrustScorer


class SourceRegistryService:
    def __init__(self, storage_backend: Any) -> None:
        self._storage = storage_backend
        self._scorer = TrustScorer()
        self._decay = TrustDecayModel()
        self._consensus = ConsensusScorer()
        self._aggregator = TrustAggregator()
        self._anti_poisoning = AntiPoisoningEngine()
        self._ranking = SourceRanking()

    # ── CRUD ──

    def add_source(
        self,
        source_url: str,
        source_name: str | None = None,
        source_tier: int = 3,
        classification: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        source_id = str(ulid.new())

        trust_score = self._scorer.compute(
            source_tier=source_tier,
            source_url=source_url,
            validation_count=0,
            days_since_first_seen=0.0,
        )
        reliability = self._scorer.reliability_score(source_tier, 0)

        entry = {
            "id": source_id,
            "source_name": source_name or source_url,
            "source_url": source_url,
            "source_tier": source_tier,
            "trust_score": trust_score,
            "reliability_score": reliability,
            "last_validated": now,
            "classification": classification or "",
            "metadata": _dumps(
                {
                    "first_seen": now,
                    "last_used": now,
                    "validation_count": 1,
                    "flags": [],
                    **(metadata or {}),
                }
            ),
        }
        self._storage.register_source(entry)
        return self.get_source(source_id)

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        raw = self._storage.get_source(source_id)
        if raw is None:
            return None
        return self._enrich(raw)

    def update_source(self, source_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        raw = self._storage.get_source(source_id)
        if raw is None:
            return None
        meta = _loads(raw.get("metadata", "{}"))
        meta.update(updates.get("metadata", {}))
        raw["metadata"] = _dumps(meta)
        for key in ("source_name", "source_url", "source_tier", "classification"):
            if key in updates:
                raw[key] = updates[key]
        if "source_tier" in updates:
            raw["trust_score"] = self._scorer.compute(
                source_tier=updates["source_tier"],
                source_url=raw.get("source_url", ""),
                validation_count=meta.get("validation_count", 0),
            )
            raw["reliability_score"] = self._scorer.reliability_score(
                updates["source_tier"], meta.get("validation_count", 0)
            )
        self._storage.register_source(raw)
        return self.get_source(source_id)

    def delete_source(self, source_id: str) -> bool:
        raw = self._storage.get_source(source_id)
        if raw is None:
            return False
        raw["trust_score"] = 0
        raw["reliability_score"] = 0
        meta = _loads(raw.get("metadata", "{}"))
        meta["flags"] = meta.get("flags", []) + ["DELETED"]
        meta["deleted_at"] = datetime.now(UTC).isoformat()
        raw["metadata"] = _dumps(meta)
        self._storage.register_source(raw)
        return True

    def list_sources(self, apply_rank: bool = True) -> list[dict[str, Any]]:
        sources = self._storage.list_sources()
        enriched = [self._enrich(s) for s in sources]
        if apply_rank:
            return self._ranking.rank(enriched)
        return enriched

    def query_sources(
        self,
        min_trust: int | None = None,
        max_trust: int | None = None,
        tier: int | None = None,
        domain: str | None = None,
        verified_only: bool = False,
    ) -> list[dict[str, Any]]:
        sources = self.list_sources(apply_rank=False)
        return self._ranking.query(
            sources,
            min_trust=min_trust,
            max_trust=max_trust,
            tier=tier,
            domain=domain,
            verified_only=verified_only,
        )

    # ── Trust management ──

    def update_trust_score(self, source_id: str, new_trust: int) -> dict[str, Any] | None:
        raw = self._storage.get_source(source_id)
        if raw is None:
            return None
        raw["trust_score"] = max(0, min(100, new_trust))
        meta = _loads(raw.get("metadata", "{}"))
        meta["trust_updated_at"] = datetime.now(UTC).isoformat()
        meta["flags"] = [f for f in meta.get("flags", []) if f != "TRUST_OVERRIDDEN"]
        raw["metadata"] = _dumps(meta)
        self._storage.register_source(raw)
        return self.get_source(source_id)

    def verify_source(self, source_id: str) -> dict[str, Any] | None:
        raw = self._storage.get_source(source_id)
        if raw is None:
            return None
        now = datetime.now(UTC).isoformat()
        raw["last_validated"] = now
        meta = _loads(raw.get("metadata", "{}"))
        meta["validation_count"] = meta.get("validation_count", 0) + 1
        meta["last_validated"] = now
        raw["trust_score"] = self._scorer.compute(
            source_tier=raw.get("source_tier", 3),
            source_url=raw.get("source_url", ""),
            validation_count=meta["validation_count"],
        )
        raw["reliability_score"] = self._scorer.reliability_score(
            raw.get("source_tier", 3), meta["validation_count"]
        )
        raw["metadata"] = _dumps(meta)
        self._storage.register_source(raw)
        return self.get_source(source_id)

    def record_usage(self, source_id: str) -> None:
        raw = self._storage.get_source(source_id)
        if raw is None:
            return
        meta = _loads(raw.get("metadata", "{}"))
        meta["last_used"] = datetime.now(UTC).isoformat()
        raw["metadata"] = _dumps(meta)
        self._storage.register_source(raw)

    # ── Analysis ──

    def get_source_stats(self) -> dict[str, Any]:
        sources = self.list_sources(apply_rank=False)
        total = len(sources)
        if total == 0:
            return {"total": 0, "avg_trust": 0, "avg_reliability": 0, "tier_distribution": {}}

        tier_dist = {1: 0, 2: 0, 3: 0}
        for s in sources:
            t = s.get("source_tier", 3)
            tier_dist[t] = tier_dist.get(t, 0) + 1

        return {
            "total": total,
            "avg_trust": round(sum(s.get("trust_score", 0) for s in sources) / total, 1),
            "avg_reliability": round(
                sum(s.get("reliability_score", 0) for s in sources) / total, 1
            ),
            "tier_distribution": tier_dist,
            "needs_revalidation": sum(1 for s in sources if self._decay.needs_revalidation(s)),
            "flagged": sum(
                1 for s in sources if "DELETED" in _loads(s.get("metadata", "{}")).get("flags", [])
            ),
        }

    def aggregate_trust(self, source_ids: list[str]) -> dict[str, Any]:
        records = []
        for sid in source_ids:
            raw = self._storage.get_source(sid)
            if raw:
                records.append(self._decay.apply_decay(raw))
        return self._aggregator.aggregate(records)

    def evaluate_entity_sources(self, source_records: list[dict[str, Any]]) -> dict[str, Any]:
        aggregation = self._aggregator.aggregate(source_records)
        poisoning = self._anti_poisoning.evaluate(
            source_records, aggregation.get("aggregated_trust")
        )
        return {
            **aggregation,
            "poisoning_flags": [f.name for f in poisoning.flags],
            "poisoning_severity": poisoning.severity,
            "poisoning_details": poisoning.details,
            "is_poisoned": poisoning.is_poisoned,
        }

    # ── Internal ──

    def _enrich(self, raw: dict[str, Any]) -> dict[str, Any]:
        meta = _loads(raw.get("metadata", "{}"))
        raw["first_seen"] = meta.get("first_seen", raw.get("last_validated"))
        raw["last_used"] = meta.get("last_used")
        raw["validation_count"] = meta.get("validation_count", 0)
        raw["flags"] = meta.get("flags", [])
        raw["decayed"] = self._decay.apply_decay(dict(raw))
        raw["needs_revalidation"] = self._decay.needs_revalidation(raw)
        raw["effective_trust"] = self._decay.effective_trust(raw)
        return raw


def _dumps(obj: dict[str, Any]) -> str:
    import json

    return json.dumps(obj, default=str)


def _loads(s: str) -> dict[str, Any]:
    import json

    if not s:
        return {}
    return json.loads(s)
