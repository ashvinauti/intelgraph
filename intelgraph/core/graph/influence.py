from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any

from intelgraph.core.enterprise.observability import get_metrics
from intelgraph.core.graph.graph import IntelligenceGraph


class InfluencePropagation:
    def __init__(
        self,
        graph: IntelligenceGraph,
        weight_fn: Callable[[Any], float] | None = None,
    ) -> None:
        self._graph = graph
        self._weight_fn = weight_fn or (lambda e: 1.0)
        self._metrics = get_metrics()

    def _record_duration(self, name: str, duration_ns: int) -> None:
        self._metrics.set_gauge(f"influence_{name}_duration_ms", duration_ns / 1_000_000)
        n = self._graph.node_count
        e = self._graph.edge_count
        self._metrics.set_gauge(f"influence_{name}_graph_nodes", float(n))
        self._metrics.set_gauge(f"influence_{name}_graph_edges", float(e))

    def _get_edge_weight(self, edge_id: str) -> float:
        edge = self._graph.edges.get(edge_id)
        if edge is None:
            return 1.0
        return self._weight_fn(edge)

    def page_rank(
        self,
        damping: float = 0.85,
        max_iterations: int = 100,
        tolerance: float = 1e-8,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = sorted(self._graph.nodes.keys())
        n = len(node_ids)
        if n == 0:
            return {"scores": {}, "iterations": 0, "converged": True, "execution_time_ms": 0.0}
        rank: dict[str, float] = dict.fromkeys(node_ids, 1.0 / n)
        out_degree: dict[str, int] = {}
        for nid in node_ids:
            out_degree[nid] = len(self._graph.forward_adjacency.get(nid, set()))
        for iteration in range(max_iterations):
            dangling = (
                damping * sum(rank[nid] for nid in node_ids if out_degree.get(nid, 0) == 0) / n
            )
            new_rank: dict[str, float] = {}
            for nid in node_ids:
                incoming_sum = 0.0
                for pred in self._graph.reverse_adjacency.get(nid, set()):
                    deg = out_degree.get(pred, 0)
                    if deg > 0:
                        incoming_sum += rank[pred] / deg
                new_rank[nid] = (1.0 - damping) / n + damping * incoming_sum + dangling
            diff = sum(abs(new_rank[nid] - rank[nid]) for nid in node_ids)
            rank = new_rank
            if diff < tolerance:
                duration = time.perf_counter_ns() - t0
                self._record_duration("page_rank", duration)
                sorted_scores = dict(sorted(rank.items(), key=lambda x: -x[1]))
                return {
                    "scores": {k: round(v, 8) for k, v in sorted_scores.items()},
                    "iterations": iteration + 1,
                    "converged": True,
                    "tolerance": tolerance,
                    "execution_time_ms": round(duration / 1_000_000, 2),
                }
        duration = time.perf_counter_ns() - t0
        self._record_duration("page_rank", duration)
        sorted_scores = dict(sorted(rank.items(), key=lambda x: -x[1]))
        return {
            "scores": {k: round(v, 8) for k, v in sorted_scores.items()},
            "iterations": max_iterations,
            "converged": False,
            "tolerance": tolerance,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def weighted_page_rank(
        self,
        damping: float = 0.85,
        max_iterations: int = 100,
        tolerance: float = 1e-8,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = sorted(self._graph.nodes.keys())
        n = len(node_ids)
        if n == 0:
            return {"scores": {}, "iterations": 0, "converged": True, "execution_time_ms": 0.0}
        out_weight: dict[str, float] = {}
        for nid in node_ids:
            total = 0.0
            for eid in self._graph.node_edges.get(nid, set()):
                src_tgt = self._graph.edge_node_map.get(eid)
                if src_tgt and src_tgt[0] == nid:
                    total += self._get_edge_weight(eid)
            out_weight[nid] = total
        rank: dict[str, float] = dict.fromkeys(node_ids, 1.0 / n)
        for iteration in range(max_iterations):
            dangling = (
                damping * sum(rank[nid] for nid in node_ids if out_weight.get(nid, 0.0) == 0.0) / n
            )
            new_rank: dict[str, float] = {}
            for nid in node_ids:
                incoming_sum = 0.0
                for pred in self._graph.reverse_adjacency.get(nid, set()):
                    w = out_weight.get(pred, 0.0)
                    if w > 0.0:
                        edge_w = 1.0
                        for eid in self._graph.node_edges.get(pred, set()):
                            src_tgt = self._graph.edge_node_map.get(eid)
                            if src_tgt and src_tgt[0] == pred and src_tgt[1] == nid:
                                edge_w = self._get_edge_weight(eid)
                                break
                        incoming_sum += rank[pred] * edge_w / w
                new_rank[nid] = (1.0 - damping) / n + damping * incoming_sum + dangling
            diff = sum(abs(new_rank[nid] - rank[nid]) for nid in node_ids)
            rank = new_rank
            if diff < tolerance:
                duration = time.perf_counter_ns() - t0
                self._record_duration("weighted_page_rank", duration)
                sorted_scores = dict(sorted(rank.items(), key=lambda x: -x[1]))
                return {
                    "scores": {k: round(v, 8) for k, v in sorted_scores.items()},
                    "iterations": iteration + 1,
                    "converged": True,
                    "tolerance": tolerance,
                    "execution_time_ms": round(duration / 1_000_000, 2),
                }
        duration = time.perf_counter_ns() - t0
        self._record_duration("weighted_page_rank", duration)
        sorted_scores = dict(sorted(rank.items(), key=lambda x: -x[1]))
        return {
            "scores": {k: round(v, 8) for k, v in sorted_scores.items()},
            "iterations": max_iterations,
            "converged": False,
            "tolerance": tolerance,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def influence_propagation(
        self,
        seed_nodes: dict[str, float],
        threshold: float = 0.5,
        decay_factor: float = 0.5,
        max_depth: int = 10,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = sorted(self._graph.nodes.keys())
        if not node_ids or not seed_nodes:
            return {
                "influence": {},
                "propagation_tree": {},
                "max_depth": 0,
                "nodes_activated": 0,
                "execution_time_ms": 0.0,
            }
        influence: dict[str, float] = {}
        propagation_tree: dict[str, list[dict[str, Any]]] = {}
        activated: set[str] = set()
        for nid, val in seed_nodes.items():
            if nid in self._graph.nodes:
                influence[nid] = val
                activated.add(nid)
                propagation_tree[nid] = []
        queue: deque[tuple[str, int]] = deque()
        for nid in seed_nodes:
            if nid in self._graph.nodes:
                queue.append((nid, 0))
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            current_influence = influence.get(current, 0.0)
            for neighbor in self._graph.forward_adjacency.get(current, set()):
                edge_influence = 1.0
                for eid in self._graph.node_edges.get(current, set()):
                    src_tgt = self._graph.edge_node_map.get(eid)
                    if src_tgt and src_tgt[0] == current and src_tgt[1] == neighbor:
                        edge_w = self._get_edge_weight(eid)
                        edge_influence = 1.0 / (1.0 + edge_w)
                        break
                neighbor_boost = current_influence * edge_influence * (decay_factor**depth)
                existing = influence.get(neighbor, 0.0)
                new_val = max(existing, neighbor_boost)
                if new_val > existing and neighbor not in seed_nodes:
                    influence[neighbor] = new_val
                    if neighbor_boost >= threshold and neighbor not in activated:
                        activated.add(neighbor)
                        queue.append((neighbor, depth + 1))
                        propagation_tree.setdefault(current, []).append(
                            {
                                "target": neighbor,
                                "influence": round(neighbor_boost, 6),
                                "depth": depth + 1,
                            }
                        )
        duration = time.perf_counter_ns() - t0
        self._metrics.set_gauge("influence_propagation_depth", float(max_depth))
        self._record_duration("influence_propagation", duration)
        sorted_influence = dict(sorted(influence.items(), key=lambda x: -x[1]))
        return {
            "influence": {k: round(v, 6) for k, v in sorted_influence.items()},
            "propagation_tree": propagation_tree,
            "max_depth": max(depth for _, depth in queue) if queue else 0,
            "nodes_activated": len(activated),
            "seed_count": len(seed_nodes),
            "threshold": threshold,
            "decay_factor": decay_factor,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def influence_scores(
        self,
        damping: float = 0.85,
        max_iterations: int = 100,
        tolerance: float = 1e-8,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = sorted(self._graph.nodes.keys())
        n = len(node_ids)
        if n == 0:
            return {"scores": {}, "execution_time_ms": 0.0}
        pr = self.page_rank(damping, max_iterations, tolerance)
        pagerank_scores = pr["scores"]
        max_deg = max((len(self._graph.adjacency.get(nid, set())) for nid in node_ids), default=1)
        total_influence: dict[str, float] = {}
        for nid in node_ids:
            pr_score = pagerank_scores.get(nid, 0.0)
            deg = len(self._graph.adjacency.get(nid, set()))
            deg_norm = deg / max_deg if max_deg > 0 else 0.0
            out_influence = 0.0
            for neighbor in self._graph.forward_adjacency.get(nid, set()):
                for eid in self._graph.node_edges.get(nid, set()):
                    src_tgt = self._graph.edge_node_map.get(eid)
                    if src_tgt and src_tgt[0] == nid and src_tgt[1] == neighbor:
                        out_influence += self._get_edge_weight(eid)
                        break
            total_influence[nid] = (
                0.5 * pr_score + 0.3 * deg_norm + 0.2 * min(out_influence / max(deg, 1), 1.0)
            )
        duration = time.perf_counter_ns() - t0
        self._record_duration("influence_scores", duration)
        sorted_scores = dict(sorted(total_influence.items(), key=lambda x: -x[1]))
        return {
            "scores": {k: round(v, 6) for k, v in sorted_scores.items()},
            "components": {
                "page_rank_weight": 0.5,
                "degree_weight": 0.3,
                "outbound_influence_weight": 0.2,
            },
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def top_influence_nodes(
        self,
        n: int = 10,
        damping: float = 0.85,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        scores_result = self.influence_scores(damping=damping)
        scores = scores_result["scores"]
        top_n = dict(list(scores.items())[:n])
        duration = time.perf_counter_ns() - t0
        return {
            "top_nodes": top_n,
            "count": len(top_n),
            "total_nodes": len(scores),
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def influence_distribution_by_community(
        self,
        communities: dict[str, list[str]],
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        scores_result = self.influence_scores()
        scores = scores_result["scores"]
        distribution: dict[str, dict[str, Any]] = {}
        for community_id, members in communities.items():
            member_scores = {m: scores.get(m, 0.0) for m in members if m in scores}
            if not member_scores:
                continue
            values = list(member_scores.values())
            distribution[community_id] = {
                "member_count": len(members),
                "mean_influence": round(sum(values) / len(values), 6),
                "max_influence": round(max(values), 6),
                "min_influence": round(min(values), 6),
                "total_influence": round(sum(values), 6),
                "top_member": max(member_scores, key=member_scores.get),
            }
        duration = time.perf_counter_ns() - t0
        return {
            "distribution": distribution,
            "community_count": len(distribution),
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def influence_chain(
        self,
        node_id: str,
        max_depth: int = 10,
        min_influence: float = 0.01,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if node_id not in self._graph.nodes:
            return {"chain": [], "node_id": node_id, "found": False, "execution_time_ms": 0.0}
        scores_result = self.influence_scores()
        scores = scores_result["scores"]
        chain: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue: deque[tuple[str, int, float]] = deque()
        queue.append((node_id, 0, scores.get(node_id, 0.0)))
        visited.add(node_id)
        while queue:
            current, depth, score = queue.popleft()
            if depth > max_depth:
                continue
            chain.append(
                {
                    "node_id": current,
                    "depth": depth,
                    "influence_score": round(score, 6),
                }
            )
            for neighbor in self._graph.forward_adjacency.get(current, set()):
                if neighbor in visited:
                    continue
                neighbor_score = scores.get(neighbor, 0.0)
                if neighbor_score < min_influence:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, depth + 1, neighbor_score))
        duration = time.perf_counter_ns() - t0
        self._record_duration("influence_chain", duration)
        return {
            "chain": chain,
            "node_id": node_id,
            "found": True,
            "chain_length": len(chain),
            "max_depth": max_depth,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def influence_decay_model(
        self,
        node_id: str,
        distance: int = 5,
        decay_factor: float = 0.5,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if node_id not in self._graph.nodes:
            return {"decay_curve": [], "node_id": node_id, "found": False, "execution_time_ms": 0.0}
        scores_result = self.influence_scores()
        base_score = scores_result["scores"].get(node_id, 0.0)
        if base_score == 0.0:
            return {"decay_curve": [], "node_id": node_id, "found": True, "execution_time_ms": 0.0}
        decay_curve: list[dict[str, Any]] = []
        for d in range(distance + 1):
            decayed = base_score * (decay_factor**d)
            decay_curve.append(
                {
                    "distance": d,
                    "raw_influence": round(base_score, 6),
                    "decayed_influence": round(decayed, 6),
                    "decay_factor": decay_factor,
                }
            )
        duration = time.perf_counter_ns() - t0
        return {
            "decay_curve": decay_curve,
            "node_id": node_id,
            "base_score": round(base_score, 6),
            "decay_factor": decay_factor,
            "found": True,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }
