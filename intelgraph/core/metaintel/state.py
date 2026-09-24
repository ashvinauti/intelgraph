from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class SystemStateSnapshot:
    snapshot_id: str
    version: int
    layers: dict[str, Any]
    hash: str
    parent_hash: str
    created_at: float = 0.0
    immutable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "version": self.version,
            "layer_count": len(self.layers),
            "hash": self.hash,
            "parent_hash": self.parent_hash,
        }


class VersionedSystemState:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._snapshots: list[SystemStateSnapshot] = []
        self._ledger: list[dict[str, Any]] = []
        self._current_state: dict[str, Any] = {}

    def snapshot(self, layers: dict[str, Any]) -> SystemStateSnapshot:
        state_json = json.dumps(layers, sort_keys=True, default=str)
        state_hash = hashlib.sha256(state_json.encode()).hexdigest()[:32]
        parent_hash = self._snapshots[-1].hash if self._snapshots else ""
        snapshot = SystemStateSnapshot(
            snapshot_id=f"ss_{uuid.uuid4().hex[:12]}",
            version=len(self._snapshots) + 1,
            layers=layers,
            hash=state_hash,
            parent_hash=parent_hash,
            created_at=time.time(),
        )
        self._snapshots.append(snapshot)
        self._current_state = dict(layers)
        self._ledger.append(
            {
                "snapshot_id": snapshot.snapshot_id,
                "version": snapshot.version,
                "hash": state_hash,
                "parent_hash": parent_hash,
                "timestamp": time.time(),
            }
        )
        return snapshot

    def restore(self, snapshot_id: str) -> bool:
        for snapshot in self._snapshots:
            if snapshot.snapshot_id == snapshot_id:
                self._current_state = dict(snapshot.layers)
                return True
        return False

    def verify_integrity(self) -> bool:
        for i, snapshot in enumerate(self._snapshots):
            expected_hash = hashlib.sha256(
                json.dumps(snapshot.layers, sort_keys=True, default=str).encode()
            ).hexdigest()[:32]
            if snapshot.hash != expected_hash:
                return False
            if i > 0:
                if snapshot.parent_hash != self._snapshots[i - 1].hash:
                    return False
        return True

    def get_timeline(self) -> list[dict[str, Any]]:
        return [
            {
                "snapshot_id": s.snapshot_id,
                "version": s.version,
                "hash": s.hash,
                "parent_hash": s.parent_hash,
                "time": s.created_at,
            }
            for s in self._snapshots
        ]

    def get_current_state(self) -> dict[str, Any]:
        return dict(self._current_state)

    def get_snapshot(self, snapshot_id: str) -> SystemStateSnapshot | None:
        for s in self._snapshots:
            if s.snapshot_id == snapshot_id:
                return s
        return None

    def get_ledger(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._ledger[-limit:]
