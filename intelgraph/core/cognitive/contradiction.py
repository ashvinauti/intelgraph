from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class Contradiction:
    contradiction_id: str
    fact_a: dict[str, Any]
    fact_b: dict[str, Any]
    contradiction_type: str
    severity: str
    confidence: float
    explanation: str
    resolution: str = "unresolved"
    detected_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "fact_a": self.fact_a,
            "fact_b": self.fact_b,
            "contradiction_type": self.contradiction_type,
            "severity": self.severity,
            "confidence": round(self.confidence, 4),
            "explanation": self.explanation,
            "resolution": self.resolution,
            "detected_at": self.detected_at,
        }


class ContradictionDetector:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._contradictions: list[Contradiction] = []
        self._threshold = self._cfg.get("contradiction_confidence_threshold", 0.5)

    def detect(self, facts: list[dict[str, Any]]) -> list[Contradiction]:
        detected: list[Contradiction] = []
        # Group by entity key — only compare within same entity (O(k * m²) vs O(n²))
        by_entity: dict[str, list[dict[str, Any]]] = {}
        for f in facts:
            ek = str(f.get("entity", ""))
            if not ek:
                continue
            if ek not in by_entity:
                by_entity[ek] = []
            by_entity[ek].append(f)
        for entity_facts in by_entity.values():
            m = len(entity_facts)
            for i in range(m):
                for j in range(i + 1, m):
                    contradiction = self._check_pair(entity_facts[i], entity_facts[j])
                    if contradiction:
                        detected.append(contradiction)
        self._contradictions.extend(detected)
        return detected

    def _check_pair(self, fa: dict[str, Any], fb: dict[str, Any]) -> Contradiction | None:
        if fa.get("entity") != fb.get("entity"):
            return None
        if fa.get("attribute") != fb.get("attribute"):
            return None
        if fa.get("value") == fb.get("value"):
            return None
        if not (
            fa.get("confidence", 0) > self._threshold and fb.get("confidence", 0) > self._threshold
        ):
            return None
        severity = (
            "critical"
            if abs(float(fa.get("value", 0)) - float(fb.get("value", 0))) > 50
            else "warning"
        )
        return Contradiction(
            contradiction_id=f"ct_{uuid.uuid4().hex[:12]}",
            fact_a=fa,
            fact_b=fb,
            contradiction_type="attribute_mismatch",
            severity=severity,
            confidence=min(fa.get("confidence", 0), fb.get("confidence", 0)),
            explanation=f"Entity '{fa.get('entity')}' attribute '{fa.get('attribute')}' has conflicting values: {fa.get('value')} vs {fb.get('value')}",
            detected_at=time.time(),
        )

    def get_all(self, limit: int = 100) -> list[Contradiction]:
        return self._contradictions[-limit:]

    def resolve(self, contradiction_id: str, resolution: str) -> bool:
        for c in self._contradictions:
            if c.contradiction_id == contradiction_id:
                c.resolution = resolution
                return True
        return False

    def contradiction_rate(self) -> float:
        if not self._contradictions:
            return 0.0
        resolved = sum(1 for c in self._contradictions if c.resolution != "unresolved")
        return resolved / len(self._contradictions)
