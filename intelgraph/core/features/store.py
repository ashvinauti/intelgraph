from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FeatureRecord:
    name: str
    value: float
    timestamp: float
    entity_id: str
    source: str = "internal"
    ttl_seconds: float = 3600.0
    schema_version: str = "1.0"
    trust_score: float = 1.0
    lineage: list[str] = field(default_factory=list)

    def is_expired(self, now: float | None = None) -> bool:
        return (now or time.time()) - self.timestamp > self.ttl_seconds

    def freshness_score(self, now: float | None = None) -> float:
        age = (now or time.time()) - self.timestamp
        if age <= 0:
            return 1.0
        ratio = age / self.ttl_seconds
        return max(0.0, 1.0 - ratio)


class FeatureStore:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._features: dict[str, list[FeatureRecord]] = defaultdict(list)
        self._lineage: dict[str, list[str]] = defaultdict(list)
        self._integrity_hashes: dict[str, str] = {}

    def set(
        self,
        entity_id: str,
        name: str,
        value: float,
        source: str = "internal",
        ttl: float = 3600.0,
        lineage: list[str] | None = None,
    ) -> FeatureRecord:
        rec = FeatureRecord(
            name=name,
            value=value,
            timestamp=time.time(),
            entity_id=entity_id,
            source=source,
            ttl_seconds=ttl,
            lineage=lineage or [],
        )
        self._features[entity_id].append(rec)
        key = f"{entity_id}:{name}"
        raw = f"{key}:{value}:{rec.timestamp}:{source}"
        self._integrity_hashes[key] = hashlib.sha256(raw.encode()).hexdigest()[:16]
        if lineage:
            self._lineage[key].extend(lineage)
        return rec

    def get(self, entity_id: str, name: str) -> FeatureRecord | None:
        recs = self._features.get(entity_id, [])
        for rec in reversed(recs):
            if rec.name == name:
                return rec
        return None

    def get_latest(self, entity_id: str, name: str) -> float | None:
        rec = self.get(entity_id, name)
        return rec.value if rec else None

    def get_all(self, entity_id: str) -> list[FeatureRecord]:
        return list(self._features.get(entity_id, []))

    def get_fresh(self, entity_id: str, name: str) -> float | None:
        rec = self.get(entity_id, name)
        if rec is None or rec.is_expired():
            return None
        return rec.value

    def get_freshness_score(self, entity_id: str, name: str) -> float:
        rec = self.get(entity_id, name)
        return rec.freshness_score() if rec else 0.0

    def detect_stale(self, entity_id: str) -> list[str]:
        stale: list[str] = []
        for rec in self._features.get(entity_id, []):
            if rec.is_expired():
                stale.append(rec.name)
        return stale

    def invalidate(self, entity_id: str, name: str) -> bool:
        recs = self._features.get(entity_id, [])
        for rec in recs:
            if rec.name == name:
                rec.ttl_seconds = 0.0
                return True
        return False

    def integrity_hash(self, entity_id: str, name: str) -> str:
        return self._integrity_hashes.get(f"{entity_id}:{name}", "")

    def lineage(self, entity_id: str, name: str) -> list[str]:
        return self._lineage.get(f"{entity_id}:{name}", [])

    def data_quality_score(self, entity_id: str) -> float:
        recs = self._features.get(entity_id, [])
        if not recs:
            return 0.0
        freshness = sum(r.freshness_score() for r in recs) / len(recs)
        trust = sum(r.trust_score for r in recs) / len(recs)
        return round(freshness * 0.6 + trust * 0.4, 4)

    def detect_drift(self, entity_id: str, name: str, recent_window: int = 10) -> float:
        recs = [r for r in self._features.get(entity_id, []) if r.name == name]
        if len(recs) < 2:
            return 0.0
        recent = recs[-recent_window:]
        if len(recent) < 2:
            return 0.0
        values = [r.value for r in recent]
        drift = max(values) - min(values)
        mean = sum(values) / len(values)
        return drift / max(abs(mean), 1e-10)

    def snapshot(self) -> dict[str, Any]:
        return {
            "entity_count": len(self._features),
            "total_features": sum(len(v) for v in self._features.values()),
            "stale_feature_count": sum(len(self.detect_stale(eid)) for eid in self._features),
        }


_feature_store = FeatureStore()


def get_feature_store() -> FeatureStore:
    return _feature_store
