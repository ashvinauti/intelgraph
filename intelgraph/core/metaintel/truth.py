from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class TruthSnapshot:
    snapshot_id: str
    timestamp: float
    confidence_weighted_state: dict[str, Any]
    contradictions_resolved: int
    source_count: int
    hash: str
    immutable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "contradictions_resolved": self.contradictions_resolved,
            "source_count": self.source_count,
            "hash": self.hash,
            "immutable": self.immutable,
        }


class TruthConsistencyGovernor:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._snapshots: list[TruthSnapshot] = []
        self._contradictions: list[dict[str, Any]] = []
        self._unified_state: dict[str, Any] = {}
        self._evidence_registry: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._temporal_history: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def resolve_contradiction(
        self, claim_a: dict[str, Any], claim_b: dict[str, Any]
    ) -> dict[str, Any]:
        conf_a = claim_a.get("confidence", 0.5)
        conf_b = claim_b.get("confidence", 0.5)
        evidence_a = claim_a.get("evidence", [])
        evidence_b = claim_b.get("evidence", [])
        resolved = claim_a if conf_a >= conf_b else claim_b
        if conf_a == conf_b:
            resolved = claim_a if len(evidence_a) >= len(evidence_b) else claim_b
        contradiction = {
            "contradiction_id": f"ctd_{uuid.uuid4().hex[:12]}",
            "claim_a": claim_a,
            "claim_b": claim_b,
            "resolution": resolved,
            "resolved_at": time.time(),
            "method": "confidence_weighted",
        }
        self._contradictions.append(contradiction)
        return resolved

    def reconcile(
        self,
        knowledge_state: dict[str, Any],
        reasoning_state: dict[str, Any],
        execution_state: dict[str, Any],
    ) -> dict[str, Any]:
        unified = {}
        all_keys = (
            set(knowledge_state.keys()) | set(reasoning_state.keys()) | set(execution_state.keys())
        )
        for key in all_keys:
            values = []
            if key in knowledge_state:
                values.append(
                    (
                        "knowledge",
                        knowledge_state[key],
                        knowledge_state.get(f"{key}_confidence", 0.5),
                    )
                )
            if key in reasoning_state:
                values.append(
                    (
                        "reasoning",
                        reasoning_state[key],
                        reasoning_state.get(f"{key}_confidence", 0.5),
                    )
                )
            if key in execution_state:
                values.append(
                    (
                        "execution",
                        execution_state[key],
                        execution_state.get(f"{key}_confidence", 0.5),
                    )
                )
            if len(values) > 1:
                best = max(values, key=lambda v: v[2])
                unified[key] = {"value": best[1], "source": best[0], "confidence": best[2]}
            elif values:
                unified[key] = {
                    "value": values[0][1],
                    "source": values[0][0],
                    "confidence": values[0][2],
                }
        return unified

    def snapshot(self, unified_state: dict[str, Any]) -> TruthSnapshot:
        state_json = json.dumps(unified_state, sort_keys=True, default=str)
        state_hash = hashlib.sha256(state_json.encode()).hexdigest()[:16]
        snapshot = TruthSnapshot(
            snapshot_id=f"ts_{uuid.uuid4().hex[:12]}",
            timestamp=time.time(),
            confidence_weighted_state=dict(unified_state),
            contradictions_resolved=len(self._contradictions),
            source_count=3,
            hash=state_hash,
        )
        self._snapshots.append(snapshot)
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> TruthSnapshot | None:
        for s in self._snapshots:
            if s.snapshot_id == snapshot_id:
                return s
        return None

    def get_temporal_state(self, key: str) -> list[dict[str, Any]]:
        return list(self._temporal_history.get(key, []))

    def record_temporal(self, key: str, value: Any, confidence: float) -> None:
        self._temporal_history[key].append(
            {"value": value, "confidence": confidence, "time": time.time()}
        )
        if len(self._temporal_history[key]) > 100:
            self._temporal_history[key] = self._temporal_history[key][-100:]

    def register_evidence(self, claim_id: str, evidence: dict[str, Any]) -> None:
        self._evidence_registry[claim_id].append(evidence)

    def arbitrate_multi_source(self, claims: list[dict[str, Any]]) -> dict[str, Any]:
        if not claims:
            return {}
        if len(claims) == 1:
            return claims[0]
        best = max(
            claims, key=lambda c: c.get("confidence", 0.0) * (1 + len(c.get("evidence", [])) * 0.1)
        )
        return best

    def get_contradictions(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._contradictions[-limit:]

    def get_snapshots(self, limit: int = 10) -> list[TruthSnapshot]:
        return self._snapshots[-limit:]
