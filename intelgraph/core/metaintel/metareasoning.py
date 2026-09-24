from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass
class MetaHypothesis:
    hypothesis_id: str
    description: str
    target_layer: str
    confidence: float
    evidence: list[dict[str, Any]]
    suggested_improvement: str
    priority: int
    generated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "description": self.description,
            "target_layer": self.target_layer,
            "confidence": round(self.confidence, 4),
            "evidence_count": len(self.evidence),
            "suggested_improvement": self.suggested_improvement,
            "priority": self.priority,
        }


class MetaReasoningEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._hypotheses: list[MetaHypothesis] = []
        self._efficiency_metrics: dict[str, list[float]] = defaultdict(list)
        self._system_reflections: list[dict[str, Any]] = []

    def evaluate_reasoning_quality(self, reasoning_traces: list[dict[str, Any]]) -> float:
        if not reasoning_traces:
            return 0.5
        confidence_scores = [t.get("confidence", 0.5) for t in reasoning_traces]
        if not confidence_scores:
            return 0.5
        return sum(confidence_scores) / len(confidence_scores)

    def detect_inefficiencies(self, layers: dict[str, Any]) -> list[dict[str, Any]]:
        inefficiencies = []
        for layer_id, metrics in layers.items():
            latency = metrics.get("latency_ms", 0)
            error_rate = metrics.get("error_rate", 0)
            if latency > 2000:
                inefficiencies.append(
                    {"layer": layer_id, "type": "latency", "value": latency, "severity": "high"}
                )
            if error_rate > 0.15:
                inefficiencies.append(
                    {
                        "layer": layer_id,
                        "type": "error_rate",
                        "value": error_rate,
                        "severity": "high",
                    }
                )
            consistency = metrics.get("consistency", 1.0)
            if consistency < 0.7:
                inefficiencies.append(
                    {
                        "layer": layer_id,
                        "type": "inconsistency",
                        "value": consistency,
                        "severity": "medium",
                    }
                )
        return inefficiencies

    def generate_system_hypothesis(
        self, observation: str, target_layer: str, evidence: list[dict[str, Any]] | None = None
    ) -> MetaHypothesis:
        hypothesis = MetaHypothesis(
            hypothesis_id=f"mh_{uuid.uuid4().hex[:12]}",
            description=observation,
            target_layer=target_layer,
            confidence=self._compute_confidence(evidence),
            evidence=evidence or [],
            suggested_improvement=self._suggest_improvement(target_layer, observation),
            priority=self._assign_priority(target_layer, observation),
            generated_at=time.time(),
        )
        self._hypotheses.append(hypothesis)
        return hypothesis

    def _compute_confidence(self, evidence: list[dict[str, Any]] | None) -> float:
        if not evidence:
            return 0.3
        strengths = [e.get("strength", 0.5) for e in evidence]
        return min(1.0, sum(strengths) / len(strengths) + 0.1)

    def _suggest_improvement(self, layer: str, observation: str) -> str:
        suggestions = {
            "nlp": "Optimize entity extraction pipeline or upgrade model",
            "reasoning": "Increase reasoning depth or adjust confidence thresholds",
            "execution": "Improve tool dispatch latency or add retry logic",
            "governance": "Tighten policy enforcement or reduce conflict resolution overhead",
            "metaintel": "Adjust meta-reasoning sampling rate or hypothesis generation frequency",
        }
        return suggestions.get(layer, "Review layer configuration and metrics")

    def _assign_priority(self, layer: str, observation: str) -> int:
        high_priority_keywords = ["degrading", "failure", "crash", "drift", "collapse"]
        if any(kw in observation.lower() for kw in high_priority_keywords):
            return 5
        return 3

    def reflect(self, global_state: dict[str, Any]) -> dict[str, Any]:
        reflection = {
            "reflection_id": f"ref_{uuid.uuid4().hex[:12]}",
            "timestamp": time.time(),
            "state_summary": dict(list(global_state.items())[:10]),
            "active_hypotheses": len(self._hypotheses),
            "suggestion": self._generate_reflection_suggestion(global_state),
        }
        self._system_reflections.append(reflection)
        return reflection

    def _generate_reflection_suggestion(self, state: dict[str, Any]) -> str:
        layers = state.get("layers", {})
        for lid, ldata in layers.items():
            if isinstance(ldata, dict) and ldata.get("score", 1.0) < 0.4:
                return f"Investigate degradation in {lid} layer"
        return "System state nominal"

    def get_hypotheses(self, limit: int = 20) -> list[MetaHypothesis]:
        return sorted(self._hypotheses, key=lambda h: (-h.priority, -h.confidence))[:limit]
