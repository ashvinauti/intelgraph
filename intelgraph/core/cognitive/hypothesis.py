from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class Hypothesis:
    hypothesis_id: str
    description: str
    confidence: float
    supporting_evidence: list[dict[str, Any]]
    missing_links: list[dict[str, Any]]
    scenario_type: str
    alternative_interpretations: list[dict[str, Any]]
    score: float
    created_at: float = 0.0
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "description": self.description,
            "confidence": round(self.confidence, 4),
            "supporting_evidence": self.supporting_evidence,
            "missing_links": self.missing_links,
            "scenario_type": self.scenario_type,
            "alternative_interpretations": self.alternative_interpretations,
            "score": round(self.score, 4),
            "created_at": self.created_at,
            "status": self.status,
        }


class HypothesisGenerator:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._max_hypotheses = self._cfg.get("max_hypotheses", 50)
        self._hypotheses: list[Hypothesis] = []
        self._scenario_templates = self._cfg.get(
            "scenario_templates",
            [
                "command_and_control",
                "data_exfiltration",
                "lateral_movement",
                "privilege_escalation",
                "persistence",
                "defense_evasion",
                "initial_access",
                "impact",
            ],
        )

    def generate(self, graph: Any | None = None) -> list[Hypothesis]:
        hypotheses: list[Hypothesis] = []
        if graph is None:
            return hypotheses
        nodes = graph.nodes if hasattr(graph, "nodes") else {}
        edges = graph.edges if hasattr(graph, "edges") else {}
        if len(nodes) < 2:
            return hypotheses
        template = self._scenario_templates[int(time.time()) % len(self._scenario_templates)]
        node_ids = list(nodes.keys())
        missing_links = self._detect_missing_links(nodes, edges, graph)
        for i in range(min(3, max(1, len(node_ids) // 2))):
            if i >= len(node_ids) - 1:
                break
            src, tgt = node_ids[i], node_ids[i + 1]
            evidence = [
                {
                    "source": src,
                    "target": tgt,
                    "relation": "suspected_connection",
                    "confidence": 0.5,
                }
            ]
            hypothesis = Hypothesis(
                hypothesis_id=f"hy_{uuid.uuid4().hex[:12]}",
                description=f"Potential {template} scenario: {src} may be connected to {tgt}",
                confidence=0.5 + (0.1 * min(i, 4)),
                supporting_evidence=evidence,
                missing_links=missing_links[:3],
                scenario_type=template,
                alternative_interpretations=self._generate_alternatives(src, tgt, template),
                score=0.5 * (1 + 0.1 * min(i, 4)),
                created_at=time.time(),
            )
            hypotheses.append(hypothesis)
        hypotheses.sort(key=lambda h: -h.score)
        self._hypotheses.extend(hypotheses)
        return hypotheses[: self._max_hypotheses]

    def _detect_missing_links(self, nodes: dict, edges: dict, graph: Any) -> list[dict[str, Any]]:
        missing = []
        node_ids = list(nodes.keys())
        adjacency = graph.adjacency if hasattr(graph, "adjacency") else {}
        for i in range(min(10, len(node_ids))):
            for j in range(i + 1, min(10, len(node_ids))):
                a, b = node_ids[i], node_ids[j]
                if a == b:
                    continue
                if b not in adjacency.get(a, set()) and a not in adjacency.get(b, set()):
                    missing.append(
                        {
                            "source": a,
                            "target": b,
                            "reason": "No direct edge between entities with shared context",
                            "confidence": 0.3,
                        }
                    )
        return missing

    def _generate_alternatives(self, src: str, tgt: str, template: str) -> list[dict[str, Any]]:
        return [
            {
                "interpretation": f"{src} is indirectly related to {tgt} through intermediate entities",
                "confidence": 0.4,
            },
            {
                "interpretation": f"The relationship between {src} and {tgt} is coincidental",
                "confidence": 0.3,
            },
            {"interpretation": f"{src} and {tgt} share a common unknown actor", "confidence": 0.5},
        ]

    def get_active(self, limit: int = 20) -> list[Hypothesis]:
        active = sorted(
            [h for h in self._hypotheses if h.status == "active"], key=lambda h: -h.score
        )
        return active[:limit]

    def get(self, hypothesis_id: str) -> Hypothesis | None:
        for h in self._hypotheses:
            if h.hypothesis_id == hypothesis_id:
                return h
        return None

    def validate(self, hypothesis_id: str, new_confidence: float) -> bool:
        h = self.get(hypothesis_id)
        if not h:
            return False
        h.confidence = new_confidence
        h.score = new_confidence
        return True
