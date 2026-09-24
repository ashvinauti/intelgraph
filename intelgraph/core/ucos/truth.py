from __future__ import annotations

import time
import uuid
from typing import Any


class UnifiedTruthEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._state: dict[str, dict[str, Any]] = {}
        self._snapshots: list[dict[str, Any]] = []
        self._contradictions: list[dict[str, Any]] = []
        self._conflict_count = 0

    def write(self, key: str, value: Any, source: str, confidence: float = 0.5) -> dict[str, Any]:
        existing = self._state.get(key)
        if existing:
            diff = abs(existing.get("confidence", 0) - confidence)
            if diff > 0.5 and existing.get("value") != value:
                self._contradictions.append(
                    {
                        "key": key,
                        "existing": dict(existing),
                        "incoming": {"value": value, "source": source, "confidence": confidence},
                        "resolved_at": time.time(),
                    }
                )
                self._conflict_count += 1
                if confidence > existing.get("confidence", 0):
                    self._state[key] = {
                        "value": value,
                        "source": source,
                        "confidence": confidence,
                        "updated_at": time.time(),
                    }
                    return {
                        "key": key,
                        "action": "overwritten",
                        "previous_source": existing.get("source"),
                    }
                return {"key": key, "action": "rejected", "reason": "existing_higher_confidence"}
        self._state[key] = {
            "value": value,
            "source": source,
            "confidence": confidence,
            "updated_at": time.time(),
        }
        return {"key": key, "action": "written", "source": source}

    def read(self, key: str) -> dict[str, Any] | None:
        return self._state.get(key)

    def query(self, pattern: str = "") -> dict[str, Any]:
        if not pattern:
            return dict(self._state)
        return {k: v for k, v in self._state.items() if pattern.lower() in k.lower()}

    def snapshot(self) -> dict[str, Any]:
        snapshot = {
            "snapshot_id": f"us_{uuid.uuid4().hex[:12]}",
            "timestamp": time.time(),
            "entries": dict(self._state),
            "entry_count": len(self._state),
            "contradiction_count": self._conflict_count,
        }
        self._snapshots.append(snapshot)
        return snapshot

    def reconcile(self, sources: list[dict[str, Any]]) -> dict[str, Any]:
        unified = {}
        for source in sources:
            for key, entry in source.items():
                if isinstance(entry, dict) and "value" in entry:
                    conf = entry.get("confidence", 0.5)
                    if key not in unified or conf > unified[key]["confidence"]:
                        unified[key] = {
                            "value": entry["value"],
                            "source": entry.get("source", "unknown"),
                            "confidence": conf,
                        }
        return unified

    def get_contradictions(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._contradictions[-limit:]

    def get_snapshots(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._snapshots[-limit:]
