from __future__ import annotations

import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

NLP_MODEL_SCHEMA_VERSION = "1.0"


class ModelTask(Enum):
    NER = auto()
    RELATIONSHIP = auto()
    EVENT = auto()
    CLASSIFICATION = auto()
    SUMMARIZATION = auto()


@dataclass
class NLPModelRecord:
    model_id: str
    name: str
    version: str
    task: ModelTask
    status: str = "registered"  # registered, active, inactive, deprecated
    accuracy: float = 0.0
    latency_ms: float = 0.0
    created_at: float = 0.0
    deployed_at: float = 0.0
    artifact_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "version": self.version,
            "task": self.task.name.lower(),
            "status": self.status,
            "accuracy": round(self.accuracy, 4),
            "latency_ms": round(self.latency_ms, 2),
            "created_at": self.created_at,
            "deployed_at": self.deployed_at,
            "artifact_path": self.artifact_path,
        }


class NLPModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, NLPModelRecord] = {}
        self._active_models: dict[ModelTask, str] = {}
        self._callbacks: list[Callable[[str, str], None]] = []

    def register(self, name: str, version: str, task: ModelTask, **kw) -> NLPModelRecord:
        model_id = f"nlp_{uuid.uuid4().hex[:12]}"
        record = NLPModelRecord(
            model_id=model_id,
            name=name,
            version=version,
            task=task,
            **kw,
        )
        self._models[model_id] = record
        return record

    def deploy(self, model_id: str) -> bool:
        model = self._models.get(model_id)
        if not model:
            return False
        old_active = self._active_models.get(model.task)
        model.status = "active"
        model.deployed_at = time.time()
        self._active_models[model.task] = model_id
        if old_active and old_active in self._models:
            self._models[old_active].status = "inactive"
        for cb in self._callbacks:
            cb(model_id, "deploy")
        return True

    def hot_swap(self, model_id: str) -> bool:
        return self.deploy(model_id)

    def get_active(self, task: ModelTask) -> NLPModelRecord | None:
        mid = self._active_models.get(task)
        if mid:
            return self._models.get(mid)
        return None

    def get(self, model_id: str) -> NLPModelRecord | None:
        return self._models.get(model_id)

    def list(self, task: ModelTask | None = None) -> list[NLPModelRecord]:
        models = list(self._models.values())
        if task:
            models = [m for m in models if m.task == task]
        return sorted(models, key=lambda m: m.created_at, reverse=True)

    def deprecate(self, model_id: str) -> bool:
        model = self._models.get(model_id)
        if not model:
            return False
        model.status = "deprecated"
        return True

    def on_swap(self, callback: Callable[[str, str], None]) -> None:
        self._callbacks.append(callback)


# ---------------------------------------------------------------------------
# NLP Analytics
# ---------------------------------------------------------------------------


class NLPAnalytics:
    def __init__(self) -> None:
        self._entity_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._relationship_counts: dict[str, int] = defaultdict(int)
        self._event_timeline: list[dict[str, Any]] = []
        self._cooccurrence: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def record_entities(self, doc_id: str, entities: list[dict[str, Any]]) -> None:
        for e in entities:
            label = e.get("label", "UNKNOWN")
            text = e.get("text", "")
            self._entity_counts[label][text] += 1

    def record_relationships(self, relationships: list[dict[str, Any]]) -> None:
        for r in relationships:
            rel = r.get("relation", "unknown")
            self._relationship_counts[rel] += 1

    def record_event(self, event: dict[str, Any]) -> None:
        self._event_timeline.append(event)

    def record_cooccurrence(self, entity_a: str, entity_b: str) -> None:
        self._cooccurrence[entity_a][entity_b] += 1
        self._cooccurrence[entity_b][entity_a] += 1

    def entity_frequency(
        self, label: str | None = None, top_n: int = 10
    ) -> dict[str, dict[str, int]]:
        if label:
            return {
                label: dict(sorted(self._entity_counts[label].items(), key=lambda x: -x[1])[:top_n])
            }
        return {
            lbl: dict(sorted(cnt.items(), key=lambda x: -x[1])[:top_n])
            for lbl, cnt in self._entity_counts.items()
        }

    def relationship_distribution(self) -> dict[str, int]:
        return dict(sorted(self._relationship_counts.items(), key=lambda x: -x[1]))

    def event_timeline(
        self, event_type: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        events = self._event_timeline[:]
        if event_type:
            events = [e for e in events if e.get("event_type") == event_type]
        return events[-limit:]

    def cooccurrence_matrix(self, entity: str, top_n: int = 10) -> dict[str, int]:
        return dict(sorted(self._cooccurrence.get(entity, {}).items(), key=lambda x: -x[1])[:top_n])

    def threat_patterns(self, min_frequency: int = 3) -> list[dict[str, Any]]:
        patterns: list[dict[str, Any]] = []
        for event_type, events in self._group_events().items():
            if len(events) >= min_frequency:
                common_actors = self._most_common([e.get("actors", []) for e in events], 3)
                common_targets = self._most_common([e.get("targets", []) for e in events], 3)
                patterns.append(
                    {
                        "event_type": event_type,
                        "frequency": len(events),
                        "common_actors": common_actors,
                        "common_targets": common_targets,
                        "recurring": len(events) >= min_frequency * 2,
                    }
                )
        return patterns

    def _group_events(self) -> dict[str, list[dict[str, Any]]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in self._event_timeline:
            groups[event.get("event_type", "unknown")].append(event)
        return groups

    def _most_common(self, lists: list[list[str]], top_n: int) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for lst in lists:
            for item in lst:
                counts[item] = counts.get(item, 0) + 1
        return sorted(counts.items(), key=lambda x: -x[1])[:top_n]
