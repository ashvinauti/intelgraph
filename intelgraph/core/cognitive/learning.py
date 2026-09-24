from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class FeedbackEntry:
    feedback_id: str
    query_id: str
    analyst_id: str
    feedback_type: str
    score: float
    correction: dict[str, Any]
    original_output: dict[str, Any]
    created_at: float = 0.0
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "query_id": self.query_id,
            "analyst_id": self.analyst_id,
            "feedback_type": self.feedback_type,
            "score": round(self.score, 4),
            "correction": self.correction,
            "applied": self.applied,
            "created_at": self.created_at,
        }


@dataclass
class ModelPerformance:
    model_id: str
    task: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    sample_count: int
    last_updated: float = 0.0


class SelfLearningLoop:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._feedback: list[FeedbackEntry] = []
        self._model_performance: dict[str, ModelPerformance] = {}
        self._improvement_scores: list[float] = []
        self._callbacks: list[Callable] = []
        self._reinforcement_buffer: list[dict[str, Any]] = []
        self._weak_signals: list[dict[str, Any]] = []
        self._learning_rate = self._cfg.get("learning_rate", 0.1)

    def ingest_feedback(
        self,
        query_id: str,
        analyst_id: str,
        feedback_type: str,
        score: float,
        correction: dict[str, Any],
        original: dict[str, Any],
    ) -> FeedbackEntry:
        entry = FeedbackEntry(
            feedback_id=f"fb_{uuid.uuid4().hex[:12]}",
            query_id=query_id,
            analyst_id=analyst_id,
            feedback_type=feedback_type,
            score=score,
            correction=correction,
            original_output=original,
            created_at=time.time(),
        )
        self._feedback.append(entry)
        self._apply_correction(entry)
        self._improvement_scores.append(score)
        return entry

    def _apply_correction(self, entry: FeedbackEntry) -> None:
        entry.applied = True
        for cb in self._callbacks:
            cb(entry)

    def on_correction(self, callback: Callable) -> None:
        self._callbacks.append(callback)

    def reinforcement_score(self, correct_count: int, total_count: int) -> float:
        if total_count == 0:
            return 0.0
        accuracy = correct_count / total_count
        score = accuracy * (1 + self._learning_rate * (accuracy - 0.5))
        self._improvement_scores.append(score)
        return score

    def learn_weak_signal(self, signal: dict[str, Any]) -> None:
        signal["detected_at"] = time.time()
        signal["signal_id"] = f"ws_{uuid.uuid4().hex[:12]}"
        self._weak_signals.append(signal)

    def get_feedback(self, limit: int = 100) -> list[FeedbackEntry]:
        return self._feedback[-limit:]

    def improvement_rate(self, window: int = 50) -> float:
        recent = self._improvement_scores[-window:]
        if len(recent) < 2:
            return 0.0
        return (recent[-1] - recent[0]) / len(recent)

    def mean_improvement(self) -> float:
        if not self._improvement_scores:
            return 0.0
        return sum(self._improvement_scores) / len(self._improvement_scores)

    def adaptive_model_select(self, task: str, models: list[dict[str, Any]]) -> str | None:
        candidates = [m for m in models if m.get("task") == task]
        if not candidates:
            return None
        best = max(
            candidates,
            key=lambda m: (
                self._model_performance.get(
                    m["model_id"],
                    ModelPerformance(
                        model_id=m["model_id"],
                        task=task,
                        accuracy=0.5,
                        precision=0.5,
                        recall=0.5,
                        f1_score=0.5,
                        sample_count=0,
                    ),
                ).accuracy
            ),
        )
        return best["model_id"]

    def record_model_performance(
        self, model_id: str, task: str, accuracy: float, precision: float, recall: float
    ) -> None:
        accuracy * precision / max(accuracy + precision, 0.001)
        f1 = 2 * (precision * recall) / max(precision + recall, 0.001)
        existing = self._model_performance.get(model_id)
        if existing:
            n = existing.sample_count
            existing.accuracy = (existing.accuracy * n + accuracy) / (n + 1)
            existing.precision = (existing.precision * n + precision) / (n + 1)
            existing.recall = (existing.recall * n + recall) / (n + 1)
            existing.f1_score = (existing.f1_score * n + f1) / (n + 1)
            existing.sample_count += 1
            existing.last_updated = time.time()
        else:
            self._model_performance[model_id] = ModelPerformance(
                model_id=model_id,
                task=task,
                accuracy=accuracy,
                precision=precision,
                recall=recall,
                f1_score=f1,
                sample_count=1,
                last_updated=time.time(),
            )

    def get_model_performance(self, model_id: str) -> ModelPerformance | None:
        return self._model_performance.get(model_id)

    def get_weak_signals(self, min_frequency: int = 1) -> list[dict[str, Any]]:
        return [s for s in self._weak_signals if s.get("frequency", 0) >= min_frequency]
