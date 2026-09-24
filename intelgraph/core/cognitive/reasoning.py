from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

COGNITIVE_SCHEMA_VERSION = "1.0"


@dataclass
class ReasoningStep:
    step_id: str
    source_node: str
    target_node: str
    relation: str
    confidence: float
    evidence: list[str]
    uncertainty: float
    step_type: str  # direct, multi_hop, causal, temporal, probabilistic
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "relation": self.relation,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
            "uncertainty": round(self.uncertainty, 4),
            "step_type": self.step_type,
        }


@dataclass
class ReasoningPath:
    path_id: str
    steps: list[ReasoningStep]
    total_confidence: float
    total_uncertainty: float
    depth: int
    start_node: str
    end_node: str
    evidence_chain: list[str]
    score: float
    alternatives: list[ReasoningPath] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_id": self.path_id,
            "steps": [s.to_dict() for s in self.steps],
            "total_confidence": round(self.total_confidence, 4),
            "total_uncertainty": round(self.total_uncertainty, 4),
            "depth": self.depth,
            "start_node": self.start_node,
            "end_node": self.end_node,
            "evidence_chain": self.evidence_chain,
            "score": round(self.score, 4),
            "alternative_count": len(self.alternatives),
        }

    def to_alert_metrics(self) -> dict[str, float]:
        return {
            "attack_path_depth": float(self.depth),
            "attack_path_confidence": self.total_confidence,
            "attack_path_score": self.score,
            "attack_path_found": 1.0,
        }

    def to_path_summary(self) -> str:
        node_labels = [self.start_node]
        for s in self.steps:
            node_labels.append(f"--[{s.relation}]-->")
            node_labels.append(s.target_node)
        return " ".join(node_labels)


class ReasoningEngine:
    def __init__(self, graph: Any | None = None, config: dict[str, Any] | None = None) -> None:
        self._graph = graph
        self._cfg = config or {}
        self._max_depth = self._cfg.get("reasoning_max_depth", 5)
        self._min_confidence = self._cfg.get("min_confidence", 0.1)
        self._traces: list[ReasoningPath] = []

    def set_graph(self, graph: Any) -> None:
        self._graph = graph

    def multi_hop_reason(
        self, start: str, end: str, max_depth: int | None = None
    ) -> list[ReasoningPath]:
        depth = max_depth or self._max_depth
        paths: list[ReasoningPath] = []
        visited: set[str] = set()
        self._dfs_paths(start, end, [], visited, paths, depth, 0)
        paths.sort(key=lambda p: -p.score)
        self._traces.extend(paths)
        return paths

    def causal_inference(
        self, node_id: str, relation: str = "causes", max_depth: int | None = None
    ) -> list[ReasoningPath]:
        depth = max_depth or self._max_depth
        paths: list[ReasoningPath] = []
        visited: set[str] = set()
        self._dfs_causal(node_id, relation, [], visited, paths, depth, 0)
        paths.sort(key=lambda p: -p.score)
        self._traces.extend(paths)
        return paths

    def temporal_reason(self, events: list[dict[str, Any]]) -> list[ReasoningPath]:
        sorted_events = sorted(events, key=lambda e: e.get("timestamp", ""))
        paths: list[ReasoningPath] = []
        for i in range(len(sorted_events) - 1):
            a, b = sorted_events[i], sorted_events[i + 1]
            step = ReasoningStep(
                step_id=_step_id(),
                source_node=a.get("entity", "unknown"),
                target_node=b.get("entity", "unknown"),
                relation="followed_by",
                confidence=0.7,
                evidence=[f"Temporal ordering: {a.get('timestamp')} -> {b.get('timestamp')}"],
                uncertainty=0.3,
                step_type="temporal",
            )
            path = ReasoningPath(
                path_id=_path_id(),
                steps=[step],
                total_confidence=step.confidence,
                total_uncertainty=step.uncertainty,
                depth=1,
                start_node=step.source_node,
                end_node=step.target_node,
                evidence_chain=[f"Event {a.get('event_type')} preceded {b.get('event_type')}"],
                score=step.confidence * (1 - step.uncertainty),
            )
            paths.append(path)
        self._traces.extend(paths)
        return paths

    def probabilistic_reason(
        self, start: str, relations: list[tuple[str, str, float]]
    ) -> ReasoningPath:
        steps: list[ReasoningStep] = []
        chain_conf = 1.0
        chain_uncertainty = 0.0
        evidence: list[str] = []
        current = start
        for rel_target, rel_type, conf in relations:
            step = ReasoningStep(
                step_id=_step_id(),
                source_node=current,
                target_node=rel_target,
                relation=rel_type,
                confidence=conf,
                evidence=[f"Probabilistic edge: {current} -[{rel_type}]-> {rel_target} (p={conf})"],
                uncertainty=1.0 - conf,
                step_type="probabilistic",
            )
            steps.append(step)
            chain_conf *= conf
            chain_uncertainty += (1.0 - conf) / len(relations)
            evidence.append(f"{current} -> {rel_target}")
            current = rel_target
        path = ReasoningPath(
            path_id=_path_id(),
            steps=steps,
            total_confidence=chain_conf,
            total_uncertainty=chain_uncertainty,
            depth=len(steps),
            start_node=start,
            end_node=current,
            evidence_chain=evidence,
            score=chain_conf * (1 - chain_uncertainty),
        )
        self._traces.append(path)
        return path

    def evidence_weighted_score(self, path: ReasoningPath) -> float:
        if not path.steps:
            return 0.0
        weight = sum(s.confidence * (1 - s.uncertainty) for s in path.steps) / len(path.steps)
        return weight * path.total_confidence

    def get_traces(self, limit: int = 50) -> list[ReasoningPath]:
        return self._traces[-limit:]

    def get_trace(self, path_id: str) -> ReasoningPath | None:
        for t in self._traces:
            if t.path_id == path_id:
                return t
        return None

    def _dfs_paths(
        self,
        current: str,
        target: str,
        steps: list[ReasoningStep],
        visited: set[str],
        results: list[ReasoningPath],
        max_depth: int,
        depth: int,
    ) -> None:
        if depth > max_depth:
            return
        if current == target and steps:
            self._build_path(steps, results)
            return
        if current in visited and depth > 0:
            return
        visited.add(current)
        if self._graph and hasattr(self._graph, "adjacency"):
            neighbors = self._graph.adjacency.get(current, set())
            self._graph.forward_adjacency.get(current, set())
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                step = ReasoningStep(
                    step_id=_step_id(),
                    source_node=current,
                    target_node=neighbor,
                    relation="connected_to",
                    confidence=0.6,
                    evidence=[f"Graph edge: {current} -> {neighbor}"],
                    uncertainty=0.4,
                    step_type="multi_hop",
                )
                steps.append(step)
                self._dfs_paths(neighbor, target, steps, visited, results, max_depth, depth + 1)
                steps.pop()
        visited.discard(current)

    def _dfs_causal(
        self,
        current: str,
        relation: str,
        steps: list[ReasoningStep],
        visited: set[str],
        results: list[ReasoningPath],
        max_depth: int,
        depth: int,
    ) -> None:
        if depth > max_depth:
            return
        if depth > 0 and steps:
            self._build_path(steps, results, is_causal=True)
        if current in visited and depth > 0:
            return
        visited.add(current)
        if self._graph and hasattr(self._graph, "forward_adjacency"):
            for neighbor in self._graph.forward_adjacency.get(current, set()):
                if neighbor in visited:
                    continue
                step = ReasoningStep(
                    step_id=_step_id(),
                    source_node=current,
                    target_node=neighbor,
                    relation=relation,
                    confidence=0.5,
                    evidence=[f"Causal edge: {current} causes {neighbor}"],
                    uncertainty=0.5,
                    step_type="causal",
                )
                steps.append(step)
                self._dfs_causal(neighbor, relation, steps, visited, results, max_depth, depth + 1)
                steps.pop()
        visited.discard(current)

    def _build_path(
        self, steps: list[ReasoningStep], results: list[ReasoningPath], is_causal: bool = False
    ) -> None:
        conf = 1.0
        unc = 0.0
        ev = []
        for s in steps:
            conf *= s.confidence
            unc += (1.0 - s.confidence) / len(steps)
            ev.append(f"{s.source_node} -[{s.relation}]-> {s.target_node}")
        path = ReasoningPath(
            path_id=_path_id(),
            steps=list(steps),
            total_confidence=conf,
            total_uncertainty=unc,
            depth=len(steps),
            start_node=steps[0].source_node,
            end_node=steps[-1].target_node,
            evidence_chain=ev,
            score=conf * (1 - unc),
        )
        results.append(path)


def _step_id() -> str:
    return f"rs_{uuid.uuid4().hex[:12]}"


def _path_id() -> str:
    return f"rp_{uuid.uuid4().hex[:12]}"
