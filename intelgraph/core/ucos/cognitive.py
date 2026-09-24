from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class UnifiedReasoningResult:
    result_id: str
    query: str
    reasoning_type: str
    paths: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    total_confidence: float
    duration_ms: float
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "query": self.query,
            "reasoning_type": self.reasoning_type,
            "path_count": len(self.paths),
            "contradiction_count": len(self.contradictions),
            "hypothesis_count": len(self.hypotheses),
            "total_confidence": round(self.total_confidence, 4),
            "duration_ms": round(self.duration_ms, 2),
        }


class UnifiedCognitiveCore:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._history: list[UnifiedReasoningResult] = []

    def reason(self, query: str, context: dict[str, Any] | None = None) -> UnifiedReasoningResult:
        start = time.perf_counter()
        context = context or {}
        reasoning_type = context.get("type", "multi_hop")
        paths = self._multi_hop_reason(query, context.get("graph", {}))
        contradictions = self._detect_contradictions(paths)
        hypotheses = self._generate_hypotheses(query, paths)
        confidence = self._compute_confidence(paths, contradictions)
        elapsed = (time.perf_counter() - start) * 1000
        result = UnifiedReasoningResult(
            result_id=f"ur_{uuid.uuid4().hex[:12]}",
            query=query,
            reasoning_type=reasoning_type,
            paths=paths,
            contradictions=contradictions,
            hypotheses=hypotheses,
            total_confidence=confidence,
            duration_ms=elapsed,
            created_at=time.time(),
        )
        self._history.append(result)
        return result

    def _multi_hop_reason(self, query: str, graph: dict[str, Any]) -> list[dict[str, Any]]:
        paths = []
        parts = query.split("->")
        if len(parts) >= 2:
            start = parts[0].strip()
            end = parts[-1].strip()
            adj = graph.get("adjacency", {})
            all_paths = self._dfs_paths(start, end, adj, max_depth=5)
            for p in all_paths:
                paths.append(
                    {
                        "nodes": p,
                        "confidence": max(0.1, 1.0 - len(p) * 0.15),
                        "hop_count": len(p) - 1,
                        "type": "deduced",
                    }
                )
        else:
            causal = self._causal_inference(query, graph)
            paths.extend(causal)
        return paths

    def _dfs_paths(
        self, start: str, end: str, adj: dict[str, Any], max_depth: int, visited: set | None = None
    ) -> list[list[str]]:
        if visited is None:
            visited = set()
        if start == end:
            return [[start]]
        if len(visited) >= max_depth:
            return []
        visited.add(start)
        results = []
        for neighbor in adj.get(start, set()):
            if neighbor not in visited:
                for subpath in self._dfs_paths(neighbor, end, adj, max_depth, visited):
                    results.append([start] + subpath)
        visited.discard(start)
        return results

    def _causal_inference(self, source: str, graph: dict[str, Any]) -> list[dict[str, Any]]:
        adj = graph.get("adjacency", {})
        forward = graph.get("forward_adjacency", adj)
        paths = self._dfs_paths(source, "", forward, 3)
        return [
            {"nodes": p, "type": "causal", "confidence": max(0.3, 1.0 - len(p) * 0.2)}
            for p in paths
            if len(p) > 1
        ]

    def _detect_contradictions(self, paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contradictions = []
        for i, p1 in enumerate(paths):
            for p2 in paths[i + 1 :]:
                if set(p1.get("nodes", [])) & set(p2.get("nodes", [])):
                    if abs(p1.get("confidence", 0) - p2.get("confidence", 0)) > 0.5:
                        contradictions.append(
                            {
                                "path_a": p1.get("nodes", []),
                                "path_b": p2.get("nodes", []),
                                "confidence_gap": round(
                                    abs(p1.get("confidence", 0) - p2.get("confidence", 0)), 4
                                ),
                                "severity": "high",
                            }
                        )
        return contradictions

    def _generate_hypotheses(self, query: str, paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
        templates = [
            {"pattern": "command_and_control", "keywords": ["c2", "command", "control"]},
            {"pattern": "data_exfiltration", "keywords": ["exfil", "data", "transfer"]},
            {"pattern": "lateral_movement", "keywords": ["lateral", "movement", "pivot"]},
        ]
        hypotheses = []
        for t in templates:
            if any(kw in query.lower() for kw in t["keywords"]):
                hypotheses.append(
                    {
                        "hypothesis_id": f"h_{uuid.uuid4().hex[:8]}",
                        "pattern": t["pattern"],
                        "confidence": 0.5 + 0.1 * len(paths),
                        "evidence_count": len(paths),
                    }
                )
        return hypotheses

    def _compute_confidence(
        self, paths: list[dict[str, Any]], contradictions: list[dict[str, Any]]
    ) -> float:
        if not paths:
            return 0.0
        avg_conf = sum(p.get("confidence", 0.5) for p in paths) / len(paths)
        penalty = len(contradictions) * 0.1
        return max(0.0, min(1.0, avg_conf - penalty))

    def temporal_reason(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sorted_events = sorted(events, key=lambda e: e.get("timestamp", ""))
        chains = []
        for i in range(len(sorted_events) - 1):
            chains.append(
                {
                    "from": sorted_events[i],
                    "to": sorted_events[i + 1],
                    "temporal_gap": f"{sorted_events[i + 1].get('timestamp', '')} - {sorted_events[i].get('timestamp', '')}",
                }
            )
        return chains

    def probabilistic_reason(self, premises: list[dict[str, Any]]) -> dict[str, Any]:
        if not premises:
            return {"conclusion": None, "confidence": 0.0}
        confidences = [p.get("confidence", 0.5) for p in premises]
        product = 1.0
        for c in confidences:
            product *= c
        return {"conclusion": "deduced", "confidence": product, "premise_count": len(premises)}

    def get_history(self, limit: int = 100) -> list[UnifiedReasoningResult]:
        return self._history[-limit:]
