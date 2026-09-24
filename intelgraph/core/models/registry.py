from __future__ import annotations

import hashlib
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class ModelStatus(Enum):
    PENDING = auto()
    APPROVED = auto()
    DEPLOYED = auto()
    CHAMPION = auto()
    CHALLENGER = auto()
    DEGRADED = auto()
    ROLLED_BACK = auto()
    RETIRED = auto()


@dataclass
class ModelArtifact:
    model_id: str
    name: str
    version: str
    status: ModelStatus
    artifact_hash: str
    created_at: float
    deployed_at: float = 0.0
    performance_metrics: dict[str, float] = field(default_factory=dict)
    parent_id: str = ""
    signature: str = ""
    sla_threshold: float = 0.8

    @property
    def is_active(self) -> bool:
        return self.status in (ModelStatus.DEPLOYED, ModelStatus.CHAMPION, ModelStatus.CHALLENGER)


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, list[ModelArtifact]] = defaultdict(list)
        self._champion: dict[str, str] = {}
        self._challengers: dict[str, list[str]] = defaultdict(list)
        self._lineage: dict[str, list[str]] = defaultdict(list)

    def register(
        self, name: str, version: str, artifact_hash: str = "", parent_id: str = ""
    ) -> ModelArtifact:
        model_id = f"mdl_{uuid.uuid4().hex[:12]}"
        artifact = ModelArtifact(
            model_id=model_id,
            name=name,
            version=version,
            status=ModelStatus.PENDING,
            artifact_hash=artifact_hash
            or hashlib.sha256(name.encode() + version.encode()).hexdigest()[:16],
            created_at=time.time(),
            parent_id=parent_id,
        )
        self._models[name].append(artifact)
        if parent_id:
            self._lineage[name].append(f"{parent_id}->{model_id}")
        return artifact

    def approve(self, model_id: str) -> bool:
        art = self._get(model_id)
        if art is None:
            return False
        art.status = ModelStatus.APPROVED
        return True

    def deploy(self, model_id: str) -> bool:
        art = self._get(model_id)
        if art is None or art.status not in (ModelStatus.APPROVED, ModelStatus.CHALLENGER):
            return False
        art.status = ModelStatus.DEPLOYED
        art.deployed_at = time.time()
        return True

    def set_champion(self, model_id: str) -> bool:
        art = self._get(model_id)
        if art is None:
            return False
        name = art.name
        old = self._champion.get(name)
        if old:
            old_art = self._get(old)
            if old_art:
                old_art.status = ModelStatus.RETIRED
        art.status = ModelStatus.CHAMPION
        self._champion[name] = model_id
        return True

    def add_challenger(self, model_id: str) -> bool:
        art = self._get(model_id)
        if art is None:
            return False
        art.status = ModelStatus.CHALLENGER
        self._challengers[art.name].append(model_id)
        return True

    def rollback(self, model_id: str) -> bool:
        art = self._get(model_id)
        if art is None:
            return False
        art.status = ModelStatus.ROLLED_BACK
        return True

    def get_champion(self, name: str) -> ModelArtifact | None:
        mid = self._champion.get(name)
        if mid is None:
            models = self._models.get(name, [])
            return models[-1] if models else None
        return self._get(mid)

    def get_challengers(self, name: str) -> list[ModelArtifact]:
        return [
            self._get(cid) for cid in self._challengers.get(name, []) if self._get(cid) is not None
        ]

    def get_versions(self, name: str) -> list[ModelArtifact]:
        return list(self._models.get(name, []))

    def record_performance(self, model_id: str, metrics: dict[str, float]) -> bool:
        art = self._get(model_id)
        if art is None:
            return False
        art.performance_metrics.update(metrics)
        return True

    def _get(self, model_id: str) -> ModelArtifact | None:
        for models in self._models.values():
            for m in models:
                if m.model_id == model_id:
                    return m
        return None

    def detect_drift(self, name: str, current_score: float) -> float:
        champ = self.get_champion(name)
        if champ is None:
            return 0.0
        baseline = champ.performance_metrics.get("accuracy", 1.0)
        return baseline - current_score

    def lineage_dag(self, name: str) -> list[str]:
        return list(self._lineage.get(name, []))

    def health_check(self, name: str) -> dict[str, Any]:
        champ = self.get_champion(name)
        if champ is None:
            return {"healthy": False, "error": "no champion model"}
        return {
            "healthy": champ.status == ModelStatus.CHAMPION,
            "model_id": champ.model_id,
            "version": champ.version,
            "status": champ.status.name,
            "performance": champ.performance_metrics,
            "challenger_count": len(self._challengers.get(name, [])),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "model_count": sum(len(v) for v in self._models.values()),
            "champion_count": len(self._champion),
            "challenger_count": sum(len(v) for v in self._challengers.values()),
            "lineage_edges": sum(len(v) for v in self._lineage.values()),
        }


_model_registry = ModelRegistry()


def get_model_registry() -> ModelRegistry:
    return _model_registry
