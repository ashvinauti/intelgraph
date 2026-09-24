from __future__ import annotations

import hashlib
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from intelgraph.core.enterprise.observability import get_metrics
from intelgraph.core.graph.graph import IntelligenceGraph

CAUSAL_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class CausalEdge:
    cause_id: str
    effect_id: str
    confidence: float
    temporal_order_confirmed: bool
    influence_contribution: float
    hop_distance: int = 1
    edge_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "cause_id": self.cause_id,
            "effect_id": self.effect_id,
            "confidence": round(self.confidence, 4),
            "temporal_order_confirmed": self.temporal_order_confirmed,
            "influence_contribution": round(self.influence_contribution, 6),
            "hop_distance": self.hop_distance,
            "edge_id": self.edge_id,
        }


@dataclass
class CausalPath:
    path_id: str
    node_ids: list[str]
    edges: list[CausalEdge]
    confidence: float
    uncertainty: float
    lineage: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_id": self.path_id,
            "node_ids": self.node_ids,
            "edges": [e.to_dict() for e in self.edges],
            "confidence": round(self.confidence, 4),
            "uncertainty": round(self.uncertainty, 4),
            "length": len(self.edges),
            "lineage": self.lineage,
        }


class CausalGraph:
    def __init__(self) -> None:
        self._edges: dict[str, list[CausalEdge]] = defaultdict(list)
        self._reverse_edges: dict[str, list[CausalEdge]] = defaultdict(list)
        self._nodes: set[str] = set()

    def add_edge(self, edge: CausalEdge) -> bool:
        if self._would_create_cycle(edge.cause_id, edge.effect_id):
            return False
        self._edges[edge.cause_id].append(edge)
        self._reverse_edges[edge.effect_id].append(edge)
        self._nodes.add(edge.cause_id)
        self._nodes.add(edge.effect_id)
        return True

    def _would_create_cycle(self, cause: str, effect: str) -> bool:
        if cause == effect:
            return True
        visited: set[str] = set()
        queue: deque[str] = deque([effect])
        while queue:
            cur = queue.popleft()
            if cur == cause:
                return True
            if cur in visited:
                continue
            visited.add(cur)
            for edge in self._edges.get(cur, []):
                queue.append(edge.effect_id)
        return False

    def get_causes(self, node_id: str) -> list[CausalEdge]:
        return list(self._reverse_edges.get(node_id, []))

    def get_effects(self, node_id: str) -> list[CausalEdge]:
        return list(self._edges.get(node_id, []))

    def get_all_edges(self) -> list[CausalEdge]:
        result: list[CausalEdge] = []
        for edges in self._edges.values():
            result.extend(edges)
        return result

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return sum(len(edges) for edges in self._edges.values())

    def to_network(self) -> dict[str, Any]:
        return {
            "nodes": sorted(self._nodes),
            "edges": [e.to_dict() for e in self.get_all_edges()],
            "node_count": self.node_count(),
            "edge_count": self.edge_count(),
        }


class CausalReasoner:
    def __init__(
        self,
        graph: IntelligenceGraph,
        config: dict[str, Any] | None = None,
        weight_fn: Callable[[Any], float] | None = None,
        deterministic: bool = True,
        anomaly_scores: dict[str, float] | None = None,
        communities: dict[str, list[str]] | None = None,
        influence_scores: dict[str, float] | None = None,
    ) -> None:
        self._graph = graph
        self._config = config or {}
        self._weight_fn = weight_fn or (lambda e: 1.0)
        self._deterministic = deterministic
        self._anomaly_scores = anomaly_scores or {}
        self._communities = communities or {}
        self._influence_scores = influence_scores or {}
        self._metrics = get_metrics()
        self._graph_version = self._compute_graph_version()
        self._causal_graph: CausalGraph = CausalGraph()
        self._lineage_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._trace_counter: int = 0

    def _compute_graph_version(self) -> str:
        node_ids = sorted(self._graph.nodes.keys())
        edge_ids = sorted(self._graph.edges.keys())
        raw = "|".join(node_ids) + "||" + "|".join(edge_ids)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _generate_trace_id(self) -> str:
        self._trace_counter += 1
        return f"ct_{self._trace_counter}_{uuid.uuid4().hex[:8]}"

    def _record_duration(self, name: str, duration_ns: int) -> None:
        self._metrics.set_gauge(f"causal_{name}_duration_ms", duration_ns / 1_000_000)
        self._metrics.set_gauge(f"causal_{name}_graph_nodes", float(self._graph.node_count))
        self._metrics.set_gauge(f"causal_{name}_graph_edges", float(self._graph.edge_count))

    def _get_edge_weight(self, edge_id: str) -> float:
        edge = self._graph.edges.get(edge_id)
        if edge is None:
            return 1.0
        return self._weight_fn(edge)

    def _entity_timestamp(self, node_id: str) -> float:
        node = self._graph.nodes.get(node_id)
        if node and hasattr(node.entity, "created_at"):
            dt = node.entity.created_at
            if isinstance(dt, datetime):
                return dt.timestamp()
        return 0.0

    def _influence_score(self, node_id: str) -> float:
        if node_id in self._influence_scores:
            return self._influence_scores[node_id]
        try:
            from intelgraph.core.graph.influence import InfluencePropagation

            infl = InfluencePropagation(self._graph, weight_fn=self._weight_fn)
            result = infl.influence_scores()
            self._influence_scores = result.get("scores", {})
            return self._influence_scores.get(node_id, 0.0)
        except Exception:
            deg = len(self._graph.adjacency.get(node_id, set()))
            return min(deg / max(self._graph.node_count, 1), 1.0)

    def _anomaly_score(self, node_id: str) -> float:
        if node_id in self._anomaly_scores:
            return self._anomaly_scores[node_id]
        return 0.0

    def _community_id(self, node_id: str) -> str:
        for cid, members in self._communities.items():
            if node_id in members:
                return cid
        visited: set[str] = set()
        queue: deque[str] = deque([node_id])
        visited.add(node_id)
        while queue:
            cur = queue.popleft()
            if cur in self._communities.get("__components", {}):
                return self._communities["__components"][cur]
            for nb in self._graph.adjacency.get(cur, set()):
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        return "default"

    def _build_causal_graph(self) -> CausalGraph:
        if self._causal_graph.edge_count() > 0:
            return self._causal_graph
        cg = CausalGraph()
        node_ids = (
            sorted(self._graph.nodes.keys())
            if self._deterministic
            else list(self._graph.nodes.keys())
        )
        for nid in node_ids:
            neighbors = (
                sorted(self._graph.forward_adjacency.get(nid, set()))
                if self._deterministic
                else list(self._graph.forward_adjacency.get(nid, set()))
            )
            for neighbor in neighbors:
                src_time = self._entity_timestamp(nid)
                tgt_time = self._entity_timestamp(neighbor)
                temporal_ok = tgt_time == 0 or src_time == 0 or src_time <= tgt_time
                if not temporal_ok:
                    continue
                edge_confidence = 0.0
                for eid in self._graph.node_edges.get(nid, set()):
                    src_tgt = self._graph.edge_node_map.get(eid)
                    if src_tgt and src_tgt[0] == nid and src_tgt[1] == neighbor:
                        conf = self._get_edge_weight(eid)
                        edge_confidence = max(edge_confidence, conf)
                src_influence = self._influence_score(nid)
                tgt_influence = self._influence_score(neighbor)
                causal_dir_score = src_influence - tgt_influence
                if causal_dir_score >= 0:
                    influence_contrib = src_influence
                    confidence = edge_confidence * 0.5 + min(influence_contrib, 1.0) * 0.3 + 0.2
                    ce = CausalEdge(
                        cause_id=nid,
                        effect_id=neighbor,
                        confidence=min(confidence, 1.0),
                        temporal_order_confirmed=temporal_ok,
                        influence_contribution=influence_contrib,
                    )
                    cg.add_edge(ce)
        self._causal_graph = cg
        self._metrics.set_gauge("causal_graph_size_nodes", float(cg.node_count()))
        self._metrics.set_gauge("causal_graph_size_edges", float(cg.edge_count()))
        return cg

    def _causal_decay(self, hop: int) -> float:
        decay = self._config.get("causal_decay_factor", 0.7)
        return decay**hop

    def _uncertainty_propagation(self, confidences: list[float]) -> float:
        if not confidences:
            return 0.0
        product = 1.0
        for c in confidences:
            product *= c
        return 1.0 - product

    def _build_path(
        self, node_ids: list[str], confidences: list[float], edges: list[CausalEdge]
    ) -> CausalPath:
        path_id = f"cp_{uuid.uuid4().hex[:12]}"
        uncertainty = self._uncertainty_propagation(confidences)
        lineage: list[dict[str, Any]] = []
        for i, ce in enumerate(edges):
            lineage.append(
                {
                    "hop": i + 1,
                    "cause": ce.cause_id,
                    "effect": ce.effect_id,
                    "confidence": ce.confidence,
                    "influence_contribution": ce.influence_contribution,
                    "temporal_order_confirmed": ce.temporal_order_confirmed,
                }
            )
        self._lineage_store[path_id] = lineage
        conf = sum(confidences) / max(len(confidences), 1) if confidences else 0.0
        return CausalPath(
            path_id=path_id,
            node_ids=node_ids,
            edges=edges,
            confidence=conf,
            uncertainty=uncertainty,
            lineage=lineage,
        )

    def root_cause_analysis(
        self,
        anomaly_node: str,
        max_depth: int = 5,
        max_causes: int = 10,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        trace_id = self._generate_trace_id()
        if anomaly_node not in self._graph.nodes:
            return {
                "found": False,
                "trace_id": trace_id,
                "error": "node not found",
                "execution_time_ms": 0.0,
            }
        cg = self._build_causal_graph()
        causes: list[CausalPath] = []
        visited: set[str] = set()
        stack: list[tuple[str, list[str], list[float], list[CausalEdge], set[str]]] = [
            (anomaly_node, [anomaly_node], [], [], {anomaly_node})
        ]
        while stack and len(causes) < max_causes * 2:
            cur, nodes, confs, edges, vis = stack.pop()
            if len(edges) > 0 and tuple(nodes) not in visited:
                visited.add(tuple(nodes))
                path = self._build_path(list(nodes), list(confs), list(edges))
                causes.append(path)
            if len(edges) >= max_depth:
                continue
            causal_edges = cg.get_causes(cur)
            sorted_edges = (
                sorted(causal_edges, key=lambda e: -e.confidence)
                if self._deterministic
                else causal_edges
            )
            for ce in sorted_edges:
                if ce.cause_id in vis:
                    continue
                decay = self._causal_decay(len(edges))
                adjusted_conf = ce.confidence * decay
                new_vis = vis | {ce.cause_id}
                stack.append(
                    (
                        ce.cause_id,
                        [ce.cause_id] + nodes,
                        [adjusted_conf] + confs,
                        [ce] + edges,
                        new_vis,
                    )
                )
        causes.sort(key=lambda p: -p.confidence)
        top_causes = causes[:max_causes]
        root_cause_ranking: list[dict[str, Any]] = []
        for cp in top_causes:
            root_cause = cp.node_ids[0]
            root_cause_ranking.append(
                {
                    "root_cause_node": root_cause,
                    "path": cp.node_ids,
                    "confidence": round(cp.confidence, 4),
                    "uncertainty": round(cp.uncertainty, 4),
                    "path_id": cp.path_id,
                    "length": len(cp.edges),
                    "lineage": cp.lineage,
                }
            )
        duration = time.perf_counter_ns() - t0
        self._record_duration("root_cause", duration)
        self._metrics.set_gauge("causal_root_cause_duration_ms", duration / 1_000_000)
        self._metrics.set_gauge("causal_root_cause_count", float(len(root_cause_ranking)))
        return {
            "found": True,
            "trace_id": trace_id,
            "anomaly_node": anomaly_node,
            "root_causes": root_cause_ranking,
            "total_paths_found": len(causes),
            "max_depth": max_depth,
            "schema_version": CAUSAL_SCHEMA_VERSION,
            "graph_version": self._graph_version,
            "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def causal_path(
        self,
        source: str,
        target: str,
        max_depth: int = 5,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        trace_id = self._generate_trace_id()
        if source not in self._graph.nodes:
            return {
                "found": False,
                "trace_id": trace_id,
                "error": "source not found",
                "execution_time_ms": 0.0,
            }
        if target not in self._graph.nodes:
            return {
                "found": False,
                "trace_id": trace_id,
                "error": "target not found",
                "execution_time_ms": 0.0,
            }
        if source == target:
            return {
                "found": True,
                "trace_id": trace_id,
                "source": source,
                "target": target,
                "paths": [],
                "execution_time_ms": 0.0,
            }
        cg = self._build_causal_graph()
        found_paths: list[CausalPath] = []
        stack: list[tuple[str, list[str], list[float], list[CausalEdge], set[str]]] = [
            (source, [source], [], [], {source})
        ]
        while stack and len(found_paths) < 100:
            cur, nodes, confs, edges, vis = stack.pop()
            if cur == target and len(edges) > 0:
                path = self._build_path(list(nodes), list(confs), list(edges))
                found_paths.append(path)
                continue
            if len(edges) >= max_depth:
                continue
            causal_edges = cg.get_effects(cur)
            sorted_edges = (
                sorted(causal_edges, key=lambda e: -e.confidence)
                if self._deterministic
                else causal_edges
            )
            for ce in sorted_edges:
                if ce.effect_id in vis:
                    continue
                decay = self._causal_decay(len(edges))
                adjusted_conf = ce.confidence * decay
                new_vis = vis | {ce.effect_id}
                stack.append(
                    (
                        ce.effect_id,
                        nodes + [ce.effect_id],
                        confs + [adjusted_conf],
                        edges + [ce],
                        new_vis,
                    )
                )
        found_paths.sort(key=lambda p: -p.confidence)
        duration = time.perf_counter_ns() - t0
        self._record_duration("causal_path", duration)
        self._metrics.set_gauge("causal_path_duration_ms", duration / 1_000_000)
        self._metrics.set_gauge("causal_path_count", float(len(found_paths)))
        return {
            "found": bool(found_paths),
            "trace_id": trace_id,
            "source": source,
            "target": target,
            "paths": [p.to_dict() for p in found_paths],
            "path_count": len(found_paths),
            "max_depth": max_depth,
            "schema_version": CAUSAL_SCHEMA_VERSION,
            "graph_version": self._graph_version,
            "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def explain(self, node_id: str, max_depth: int = 5) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        trace_id = self._generate_trace_id()
        if node_id not in self._graph.nodes:
            return {
                "found": False,
                "trace_id": trace_id,
                "error": "node not found",
                "execution_time_ms": 0.0,
            }
        cg = self._build_causal_graph()
        causes = cg.get_causes(node_id)
        effects = cg.get_effects(node_id)
        anomaly_score = self._anomaly_score(node_id)
        influence_score = self._influence_score(node_id)
        ancestors: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        visited.add(node_id)
        while queue:
            cur, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for ce in cg.get_causes(cur):
                if ce.cause_id not in visited:
                    visited.add(ce.cause_id)
                    ancestors.append(
                        {
                            "node_id": ce.cause_id,
                            "depth": depth + 1,
                            "confidence": ce.confidence,
                            "influence_contribution": ce.influence_contribution,
                        }
                    )
                    queue.append((ce.cause_id, depth + 1))
        descendants: list[dict[str, Any]] = []
        visited2: set[str] = {node_id}
        queue2: deque[tuple[str, int]] = deque([(node_id, 0)])
        while queue2:
            cur, depth = queue2.popleft()
            if depth >= max_depth:
                continue
            for ce in cg.get_effects(cur):
                if ce.effect_id not in visited2:
                    visited2.add(ce.effect_id)
                    descendants.append(
                        {
                            "node_id": ce.effect_id,
                            "depth": depth + 1,
                            "confidence": ce.confidence,
                            "influence_contribution": ce.influence_contribution,
                        }
                    )
                    queue2.append((ce.effect_id, depth + 1))
        duration = time.perf_counter_ns() - t0
        self._record_duration("explain", duration)
        return {
            "found": True,
            "trace_id": trace_id,
            "node_id": node_id,
            "anomaly_score": round(anomaly_score, 6),
            "influence_score": round(influence_score, 6),
            "direct_causes": [ce.to_dict() for ce in causes],
            "direct_effects": [ce.to_dict() for ce in effects],
            "ancestor_chain": ancestors,
            "descendant_chain": descendants,
            "causal_graph": cg.to_network(),
            "schema_version": CAUSAL_SCHEMA_VERSION,
            "graph_version": self._graph_version,
            "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def chains(self, node_id: str, max_depth: int = 5) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        trace_id = self._generate_trace_id()
        if node_id not in self._graph.nodes:
            return {
                "found": False,
                "trace_id": trace_id,
                "error": "node not found",
                "execution_time_ms": 0.0,
            }
        cg = self._build_causal_graph()
        cause_chains: list[dict[str, Any]] = []
        effect_chains: list[dict[str, Any]] = []
        stack_causes: list[tuple[str, list[str], list[float], set[str]]] = [
            (node_id, [node_id], [], {node_id})
        ]
        while stack_causes:
            cur, nodes, confs, vis = stack_causes.pop()
            causal_edges = cg.get_causes(cur)
            if not causal_edges and len(nodes) > 1:
                cause_chains.append(
                    {
                        "path": list(nodes),
                        "confidence": round(sum(confs) / max(len(confs), 1), 4),
                        "length": len(nodes) - 1,
                    }
                )
            if len(nodes) - 1 >= max_depth:
                continue
            for ce in causal_edges:
                if ce.cause_id in vis:
                    continue
                new_vis = vis | {ce.cause_id}
                stack_causes.append(
                    (
                        ce.cause_id,
                        [ce.cause_id] + nodes,
                        [ce.confidence] + confs,
                        new_vis,
                    )
                )
        stack_effects: list[tuple[str, list[str], list[float], set[str]]] = [
            (node_id, [node_id], [], {node_id})
        ]
        while stack_effects:
            cur, nodes, confs, vis = stack_effects.pop()
            causal_edges = cg.get_effects(cur)
            if not causal_edges and len(nodes) > 1:
                effect_chains.append(
                    {
                        "path": list(nodes),
                        "confidence": round(sum(confs) / max(len(confs), 1), 4),
                        "length": len(nodes) - 1,
                    }
                )
            if len(nodes) - 1 >= max_depth:
                continue
            for ce in causal_edges:
                if ce.effect_id in vis:
                    continue
                new_vis = vis | {ce.effect_id}
                stack_effects.append(
                    (
                        ce.effect_id,
                        nodes + [ce.effect_id],
                        confs + [ce.confidence],
                        new_vis,
                    )
                )
        duration = time.perf_counter_ns() - t0
        self._record_duration("chains", duration)
        self._metrics.set_gauge(
            "causal_chains_depth", float(max(len(cause_chains), len(effect_chains)))
        )
        return {
            "found": True,
            "trace_id": trace_id,
            "node_id": node_id,
            "cause_chains": cause_chains,
            "effect_chains": effect_chains,
            "cause_chain_count": len(cause_chains),
            "effect_chain_count": len(effect_chains),
            "max_depth": max_depth,
            "schema_version": CAUSAL_SCHEMA_VERSION,
            "graph_version": self._graph_version,
            "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def causal_graph_network(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        trace_id = self._generate_trace_id()
        cg = self._build_causal_graph()
        network = cg.to_network()
        community_stats: dict[str, dict[str, Any]] = {}
        for cid, members in self._communities.items():
            community_stats[cid] = {
                "size": len(members),
                "member_count": len(members),
            }
        duration = time.perf_counter_ns() - t0
        self._record_duration("causal_graph", duration)
        return {
            "trace_id": trace_id,
            "causal_graph": network,
            "community_stats": community_stats,
            "schema_version": CAUSAL_SCHEMA_VERSION,
            "graph_version": self._graph_version,
            "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def top_causes(self, node_id: str, max_depth: int = 5, top_n: int = 10) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        trace_id = self._generate_trace_id()
        root_cause_result = self.root_cause_analysis(node_id, max_depth, top_n)
        if not root_cause_result.get("found"):
            root_cause_result["trace_id"] = trace_id
            return root_cause_result
        root_causes = root_cause_result.get("root_causes", [])
        cross_community_propagation: list[dict[str, Any]] = []
        for rc in root_causes:
            rc_node = rc["root_cause_node"]
            rc_community = self._community_id(rc_node)
            anomaly_community = self._community_id(node_id)
            cross_community_propagation.append(
                {
                    "root_cause_node": rc_node,
                    "root_cause_community": rc_community,
                    "anomaly_community": anomaly_community,
                    "cross_community": rc_community != anomaly_community,
                    "confidence": rc["confidence"],
                }
            )
        duration = time.perf_counter_ns() - t0
        root_cause_result["trace_id"] = trace_id
        root_cause_result["cross_community_propagation"] = cross_community_propagation
        root_cause_result["execution_time_ms"] = round(duration / 1_000_000, 2)
        return root_cause_result
