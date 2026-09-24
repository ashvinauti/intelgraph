from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

# UTE import — SSOT delegates storage to UnifiedTruthEngine
from intelgraph.core.ucos.truth import UnifiedTruthEngine


@dataclass
class UnifiedStateEntry:
    entry_id: str
    key: str
    value: Any
    source: str
    confidence: float
    timestamp: float
    immutable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "key": self.key,
            "source": self.source,
            "confidence": round(self.confidence, 4),
            "timestamp": self.timestamp,
            "immutable": self.immutable,
        }


class SingleSourceOfTruth:
    def __init__(
        self, config: dict[str, Any] | None = None, truth_engine: UnifiedTruthEngine | None = None
    ) -> None:
        self._cfg = config or {}
        self._engine = truth_engine or UnifiedTruthEngine(config)
        self._state: dict[str, UnifiedStateEntry] = {}
        self._snapshots: list[dict[str, Any]] = []
        self._rejected: list[dict[str, Any]] = []
        self._conflict_count = 0

    def set(self, key: str, value: Any, source: str, confidence: float = 0.5) -> dict[str, Any]:
        # Delegate write to UnifiedTruthEngine (single source of truth)
        engine_result = self._engine.write(
            key=key, value=value, source=source, confidence=confidence
        )
        # Map UTE action names to SSOT action names for backward compat
        action_map = {"written": "set", "overwritten": "reconciled"}
        if engine_result.get("action") in action_map:
            engine_result = {**engine_result, "action": action_map[engine_result["action"]]}
        return engine_result

    def get(self, key: str) -> UnifiedStateEntry | None:
        # Delegate read to UnifiedTruthEngine; wrap in UnifiedStateEntry
        raw = self._engine.read(key)
        if raw is None:
            return self._state.get(key) or None
        existing = self._state.get(key)
        if existing:
            return existing
        entry = UnifiedStateEntry(
            entry_id=f"us_{uuid.uuid4().hex[:12]}",
            key=key,
            value=raw.get("value"),
            source=raw.get("source", "unknown"),
            confidence=raw.get("confidence", 0.0),
            timestamp=raw.get("updated_at", time.time()),
        )
        self._state[key] = entry
        return entry

    def set_immutable(self, key: str) -> bool:
        entry = self._state.get(key)
        if entry:
            entry.immutable = True
            return True
        return False

    def get_all(self) -> dict[str, UnifiedStateEntry]:
        all_raw = self._engine.query()
        result = {}
        for k, v in all_raw.items():
            entry = UnifiedStateEntry(
                entry_id=f"us_{uuid.uuid4().hex[:12]}",
                key=k,
                value=v.get("value"),
                source=v.get("source", "unknown"),
                confidence=v.get("confidence", 0.0),
                timestamp=v.get("updated_at", time.time()),
            )
            result[k] = entry
            self._state[k] = entry
        return result

    def snapshot(self) -> dict[str, Any]:
        snap = {
            "snapshot_id": f"ss_{uuid.uuid4().hex[:12]}",
            "timestamp": time.time(),
            "entries": {k: v.to_dict() for k, v in self.get_all().items()},
            "entry_count": len(self._state),
            "conflict_count": self._conflict_count,
            "rejected_count": len(self._rejected),
        }
        self._snapshots.append(snap)
        return snap

    def get_snapshots(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._snapshots[-limit:]
