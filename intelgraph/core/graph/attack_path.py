from __future__ import annotations

import hashlib
import heapq
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from intelgraph.core.enterprise.observability import get_metrics
from intelgraph.core.graph.graph import IntelligenceGraph

ATTACK_PATH_SCHEMA_VERSION = "1.0"


class AttackPathCache:
    def __init__(self) -> None:
        self._sub_paths: dict[str, list[dict[str, Any]]] = {}
        self._graph_versions: dict[str, str] = {}

    def _make_key(self, source: str, target: str, max_depth: int) -> str:
        raw = f"{source}|{target}|{max_depth}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(
        self, source: str, target: str, max_depth: int, graph_version: str
    ) -> list[dict[str, Any]] | None:
        key = self._make_key(source, target, max_depth)
        if key in self._sub_paths and self._graph_versions.get(key) == graph_version:
            return self._sub_paths[key]
        return None

    def set(
        self,
        source: str,
        target: str,
        max_depth: int,
        graph_version: str,
        paths: list[dict[str, Any]],
    ) -> None:
        key = self._make_key(source, target, max_depth)
        self._sub_paths[key] = paths
        self._graph_versions[key] = graph_version

    def clear(self) -> None:
        self._sub_paths.clear()
        self._graph_versions.clear()


class AttackPathAnalyzer:
    def __init__(
        self,
        graph: IntelligenceGraph,
        config: dict[str, Any] | None = None,
        weight_fn: Callable[[Any], float] | None = None,
        deterministic: bool = True,
        cache: AttackPathCache | None = None,
    ) -> None:
        self._graph = graph
        self._config = config or {}
        self._weight_fn = weight_fn or (lambda e: 1.0)
        self._deterministic = deterministic
        self._cache = cache or AttackPathCache()
        self._metrics = get_metrics()
        self._graph_version = self._compute_graph_version()
        self._path_counter: int = 0

    def _compute_graph_version(self) -> str:
        node_ids = sorted(self._graph.nodes.keys())
        edge_ids = sorted(self._graph.edges.keys())
        raw = "|".join(node_ids) + "||" + "|".join(edge_ids)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _record_duration(self, name: str, duration_ns: int) -> None:
        self._metrics.set_gauge(f"attack_path_{name}_duration_ms", duration_ns / 1_000_000)
        self._metrics.set_gauge(f"attack_path_{name}_graph_nodes", float(self._graph.node_count))
        self._metrics.set_gauge(f"attack_path_{name}_graph_edges", float(self._graph.edge_count))

    def _next_path_id(self) -> str:
        self._path_counter += 1
        return f"path_{self._path_counter}_{int(time.time() * 1_000_000)}"

    def _get_edge_weight(self, edge_id: str) -> float:
        edge = self._graph.edges.get(edge_id)
        if edge is None:
            return 1.0
        return self._weight_fn(edge)

    def _edge_confidence(self, edge_id: str) -> float:
        edge = self._graph.edges.get(edge_id)
        if edge is None or not edge.relationship:
            return 0.5
        return float(getattr(edge.relationship, "confidence_score", 50)) / 100.0

    def _edge_trust(self, edge_id: str) -> float:
        edge = self._graph.edges.get(edge_id)
        if edge is None or not edge.relationship:
            return 0.5
        return float(getattr(edge.relationship, "trust_weight", 50)) / 100.0

    def _node_influence(self, node_id: str) -> float:
        try:
            from intelgraph.core.graph.influence import InfluencePropagation

            infl = InfluencePropagation(self._graph, weight_fn=self._weight_fn)
            result = infl.influence_scores()
            return result.get("scores", {}).get(node_id, 0.0)
        except Exception:
            deg = len(self._graph.adjacency.get(node_id, set()))
            return min(deg / max(self._graph.node_count, 1), 1.0)

    def _edge_risk_weight(self, edge_id: str) -> float:
        conf = self._edge_confidence(edge_id)
        trust = self._edge_trust(edge_id)
        if conf <= 0 or trust <= 0:
            return float("inf")
        return 1.0 / (conf * trust)

    def _path_risk_score(self, edge_ids: list[str]) -> dict[str, Any]:
        if not edge_ids:
            return {
                "score": 0.0,
                "confidence_product": 0.0,
                "trust_product": 0.0,
                "mean_edge_confidence": 0.0,
                "mean_edge_trust": 0.0,
            }
        conf_prod = 1.0
        trust_prod = 1.0
        confs: list[float] = []
        trusts: list[float] = []
        for eid in edge_ids:
            c = self._edge_confidence(eid)
            t = self._edge_trust(eid)
            conf_prod *= c
            trust_prod *= t
            confs.append(c)
            trusts.append(t)
        mean_conf = sum(confs) / len(confs)
        mean_trust = sum(trusts) / len(trusts)
        influence_scores = [
            self._node_influence(self._graph.edge_node_map.get(eid, ("", ""))[1])
            for eid in edge_ids
        ]
        mean_influence = sum(influence_scores) / max(len(influence_scores), 1)
        composite = conf_prod * trust_prod * (1.0 + mean_influence)
        return {
            "score": round(min(composite, 1.0), 6),
            "confidence_product": round(conf_prod, 6),
            "trust_product": round(trust_prod, 6),
            "mean_edge_confidence": round(mean_conf, 4),
            "mean_edge_trust": round(mean_trust, 4),
            "mean_target_influence": round(mean_influence, 6),
        }

    def _build_path_dict(
        self, path_id: str, node_ids: list[str], edge_ids: list[str]
    ) -> dict[str, Any]:
        risk = self._path_risk_score(edge_ids)
        return {
            "path_id": path_id,
            "node_ids": node_ids,
            "edge_ids": edge_ids,
            "length": len(edge_ids),
            "risk_score": risk["score"],
            "risk_decomposition": risk,
        }

    def find_shortest_path(self, source: str, target: str) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if source not in self._graph.nodes:
            return {
                "found": False,
                "source": source,
                "target": target,
                "error": "source not found",
                "execution_time_ms": 0.0,
            }
        if target not in self._graph.nodes:
            return {
                "found": False,
                "source": source,
                "target": target,
                "error": "target not found",
                "execution_time_ms": 0.0,
            }
        if source == target:
            return {
                "found": True,
                "source": source,
                "target": target,
                "path_id": self._next_path_id(),
                "node_ids": [source],
                "edge_ids": [],
                "length": 0,
                "risk_score": 1.0,
                "risk_decomposition": self._path_risk_score([]),
                "schema_version": ATTACK_PATH_SCHEMA_VERSION,
                "graph_version": self._graph_version,
                "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
                "execution_time_ms": 0.0,
            }
        dist: dict[str, float] = {source: 0.0}
        prev_node: dict[str, str | None] = {source: None}
        prev_edge: dict[str, str | None] = {source: None}
        pq: list[tuple[float, str]] = [(0.0, source)]
        visited: set[str] = set()
        while pq:
            d, cur = heapq.heappop(pq)
            if cur in visited:
                continue
            visited.add(cur)
            if cur == target:
                break
            for neighbor in self._graph.forward_adjacency.get(cur, set()):
                for eid in self._graph.node_edges.get(cur, set()):
                    src_tgt = self._graph.edge_node_map.get(eid)
                    if src_tgt and src_tgt[0] == cur and src_tgt[1] == neighbor:
                        w = self._edge_risk_weight(eid)
                        nd = d + w
                        if neighbor not in dist or nd < dist[neighbor]:
                            dist[neighbor] = nd
                            prev_node[neighbor] = cur
                            prev_edge[neighbor] = eid
                            heapq.heappush(pq, (nd, neighbor))
                        break
        if target not in prev_node or prev_node[target] is None:
            duration = time.perf_counter_ns() - t0
            self._record_duration("find_shortest", duration)
            return {
                "found": False,
                "source": source,
                "target": target,
                "error": "no path exists",
                "schema_version": ATTACK_PATH_SCHEMA_VERSION,
                "graph_version": self._graph_version,
                "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
                "execution_time_ms": round(duration / 1_000_000, 2),
            }
        node_ids: list[str] = []
        edge_ids: list[str] = []
        cur: str | None = target
        while cur is not None:
            node_ids.append(cur)
            pe = prev_edge.get(cur)
            if pe:
                edge_ids.append(pe)
            cur = prev_node.get(cur)
        node_ids.reverse()
        edge_ids.reverse()
        path_id = self._next_path_id()
        path_dict = self._build_path_dict(path_id, node_ids, edge_ids)
        duration = time.perf_counter_ns() - t0
        self._record_duration("find_shortest", duration)
        self._metrics.set_gauge("attack_path_find_shortest_duration_ms", duration / 1_000_000)
        self._metrics.set_gauge("attack_path_find_shortest_length", float(len(edge_ids)))
        self._metrics.set_gauge("attack_path_find_shortest_risk", path_dict["risk_score"])
        return {
            "found": True,
            "source": source,
            "target": target,
            "path": path_dict,
            "schema_version": ATTACK_PATH_SCHEMA_VERSION,
            "graph_version": self._graph_version,
            "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def find_all_paths(
        self,
        source: str,
        target: str | None = None,
        max_depth: int = 5,
        max_paths: int = 100,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if source not in self._graph.nodes:
            return {
                "found": False,
                "source": source,
                "error": "source not found",
                "execution_time_ms": 0.0,
            }
        cache_key_source = source
        cache_key_target = target or ""
        cached = self._cache.get(cache_key_source, cache_key_target, max_depth, self._graph_version)
        if cached is not None:
            duration = time.perf_counter_ns() - t0
            self._metrics.set_gauge("attack_path_all_paths_count", float(len(cached)))
            return {
                "found": bool(cached),
                "source": source,
                "target": target,
                "paths": cached,
                "path_count": len(cached),
                "cached": True,
                "schema_version": ATTACK_PATH_SCHEMA_VERSION,
                "graph_version": self._graph_version,
                "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
                "execution_time_ms": round(duration / 1_000_000, 2),
            }
        found_paths: list[dict[str, Any]] = []
        stack: list[tuple[str, list[str], list[str], set[str]]] = [(source, [source], [], {source})]
        while stack and len(found_paths) < max_paths:
            cur, nodes, edges, visited = stack.pop()
            if target is not None and cur == target and len(edges) > 0:
                path_id = self._next_path_id()
                found_paths.append(self._build_path_dict(path_id, list(nodes), list(edges)))
                continue
            if target is None and len(edges) > 0:
                path_id = self._next_path_id()
                found_paths.append(self._build_path_dict(path_id, list(nodes), list(edges)))
            if len(edges) >= max_depth:
                continue
            neighbors = (
                sorted(self._graph.forward_adjacency.get(cur, set()))
                if self._deterministic
                else list(self._graph.forward_adjacency.get(cur, set()))
            )
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                edge_found = None
                for eid in self._graph.node_edges.get(cur, set()):
                    src_tgt = self._graph.edge_node_map.get(eid)
                    if src_tgt and src_tgt[0] == cur and src_tgt[1] == neighbor:
                        edge_found = eid
                        break
                if edge_found is None:
                    continue
                new_visited = visited | {neighbor}
                stack.append((neighbor, nodes + [neighbor], edges + [edge_found], new_visited))
        self._cache.set(
            cache_key_source, cache_key_target, max_depth, self._graph_version, found_paths
        )
        duration = time.perf_counter_ns() - t0
        self._record_duration("all_paths", duration)
        self._metrics.set_gauge("attack_path_all_paths_count", float(len(found_paths)))
        return {
            "found": bool(found_paths) if target else True,
            "source": source,
            "target": target,
            "paths": found_paths,
            "path_count": len(found_paths),
            "max_depth": max_depth,
            "max_paths": max_paths,
            "cached": False,
            "schema_version": ATTACK_PATH_SCHEMA_VERSION,
            "graph_version": self._graph_version,
            "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def _analyze_paths(self, paths: list[dict[str, Any]]) -> dict[str, Any]:
        if not paths:
            return {
                "risk_distribution": {},
                "critical_node_frequency": {},
                "path_length_stats": {},
                "bottleneck_nodes": [],
            }
        risk_scores = [p["risk_score"] for p in paths]
        path_lengths = [p["length"] for p in paths]
        sorted_risks = sorted(risk_scores)
        n = len(sorted_risks)
        node_frequency: dict[str, int] = defaultdict(int)
        for p in paths:
            for nid in p["node_ids"]:
                node_frequency[nid] += 1
        bottleneck_nodes = sorted(
            [(nid, freq) for nid, freq in node_frequency.items() if freq > max(1, n // 5)],
            key=lambda x: -x[1],
        )
        return {
            "risk_distribution": {
                "min": round(min(risk_scores), 6),
                "max": round(max(risk_scores), 6),
                "mean": round(sum(risk_scores) / n, 6),
                "median": round(sorted_risks[n // 2], 6),
                "q1": round(sorted_risks[n // 4], 6),
                "q3": round(sorted_risks[(3 * n) // 4], 6),
            },
            "critical_node_frequency": dict(
                sorted(node_frequency.items(), key=lambda x: -x[1])[:20]
            ),
            "bottleneck_nodes": [
                {"node_id": nid, "path_frequency": freq} for nid, freq in bottleneck_nodes[:10]
            ],
            "path_length_stats": {
                "min": min(path_lengths),
                "max": max(path_lengths),
                "mean": round(sum(path_lengths) / len(path_lengths), 2),
                "median": sorted(path_lengths)[len(path_lengths) // 2],
            },
        }

    def critical_nodes(self, max_depth: int = 5) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = (
            sorted(self._graph.nodes.keys())
            if self._deterministic
            else list(self._graph.nodes.keys())
        )
        if not node_ids:
            return {"critical_nodes": [], "execution_time_ms": 0.0}
        all_paths: list[dict[str, Any]] = []
        sampled_sources = node_ids[: min(20, len(node_ids))]
        for src in sampled_sources:
            result = self.find_all_paths(src, max_depth=max_depth, max_paths=50)
            all_paths.extend(result.get("paths", []))
        analytics = self._analyze_paths(all_paths)
        node_degree: dict[str, int] = {}
        for nid in node_ids:
            node_degree[nid] = len(self._graph.adjacency.get(nid, set()))
        centrality_scores: dict[str, float] = {}
        for nid in node_ids:
            betweenness = sum(1 for p in all_paths if nid in p["node_ids"][1:-1])
            deg_norm = node_degree.get(nid, 0) / max(self._graph.node_count, 1)
            centrality_scores[nid] = round(betweenness * 0.6 + deg_norm * 0.4, 6)
        sorted_centrality = sorted(centrality_scores.items(), key=lambda x: -x[1])
        duration = time.perf_counter_ns() - t0
        self._record_duration("critical_nodes", duration)
        self._metrics.set_gauge("attack_path_critical_nodes_duration_ms", duration / 1_000_000)
        self._metrics.set_gauge("attack_path_critical_nodes_count", float(len(sorted_centrality)))
        return {
            "critical_nodes": [
                {"node_id": nid, "centrality_score": score, "degree": node_degree.get(nid, 0)}
                for nid, score in sorted_centrality[:20]
            ],
            "analytics": analytics,
            "graph_version": self._graph_version,
            "schema_version": ATTACK_PATH_SCHEMA_VERSION,
            "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def attack_surface(self, entity_id: str, max_depth: int = 4) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if entity_id not in self._graph.nodes:
            return {
                "found": False,
                "entity_id": entity_id,
                "error": "entity not found",
                "execution_time_ms": 0.0,
            }
        node = self._graph.nodes[entity_id]
        entity_type = getattr(node, "entity_type", "unknown")
        reachable_nodes: set[str] = set()
        reachable_edges: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(entity_id, 0)])
        visited: set[str] = {entity_id}
        while queue:
            cur, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor in self._graph.forward_adjacency.get(cur, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    reachable_nodes.add(neighbor)
                    queue.append((neighbor, depth + 1))
                for eid in self._graph.node_edges.get(cur, set()):
                    src_tgt = self._graph.edge_node_map.get(eid)
                    if src_tgt and src_tgt[0] == cur and src_tgt[1] == neighbor:
                        reachable_edges.add(eid)
        surface_by_type: dict[str, int] = defaultdict(int)
        for nid in reachable_nodes:
            n = self._graph.nodes.get(nid)
            nt = getattr(n, "entity_type", "unknown") if n else "unknown"
            surface_by_type[nt] += 1
        surface_risk = 0.0
        total_conf = 0.0
        for eid in reachable_edges:
            surface_risk += self._edge_risk_weight(eid)
            total_conf += self._edge_confidence(eid)
        avg_risk = surface_risk / max(len(reachable_edges), 1)
        avg_conf = total_conf / max(len(reachable_edges), 1)
        duration = time.perf_counter_ns() - t0
        self._record_duration("attack_surface", duration)
        self._metrics.set_gauge("attack_path_surface_duration_ms", duration / 1_000_000)
        self._metrics.set_gauge("attack_path_surface_node_count", float(len(reachable_nodes)))
        return {
            "found": True,
            "entity_id": entity_id,
            "entity_type": entity_type,
            "surface_size": {
                "nodes": len(reachable_nodes),
                "edges": len(reachable_edges),
            },
            "surface_by_type": dict(surface_by_type),
            "max_depth": max_depth,
            "average_edge_risk": round(avg_risk, 4),
            "average_edge_confidence": round(avg_conf, 4),
            "reachable_node_ids": sorted(reachable_nodes)[:100] if reachable_nodes else [],
            "schema_version": ATTACK_PATH_SCHEMA_VERSION,
            "graph_version": self._graph_version,
            "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def explain_path(
        self, path_id: str, paths_result: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if paths_result is None:
            return {
                "found": False,
                "path_id": path_id,
                "error": "no path result provided",
                "execution_time_ms": 0.0,
            }
        all_paths = paths_result.get("paths", [])
        if not all_paths:
            single = paths_result.get("path")
            if single:
                all_paths = [single]
        target_path = None
        for p in all_paths:
            if p.get("path_id") == path_id:
                target_path = p
                break
        if target_path is None:
            return {
                "found": False,
                "path_id": path_id,
                "error": "path not found in result",
                "execution_time_ms": 0.0,
            }
        edge_ids = target_path.get("edge_ids", [])
        node_ids = target_path.get("node_ids", [])
        segment_breakdown: list[dict[str, Any]] = []
        for i, eid in enumerate(edge_ids):
            src = node_ids[i] if i < len(node_ids) else "?"
            tgt = node_ids[i + 1] if i + 1 < len(node_ids) else "?"
            conf = self._edge_confidence(eid)
            trust = self._edge_trust(eid)
            influence = self._node_influence(tgt)
            w = self._edge_risk_weight(eid)
            segment_breakdown.append(
                {
                    "segment_index": i,
                    "source": src,
                    "target": tgt,
                    "edge_id": eid,
                    "confidence": round(conf, 4),
                    "trust": round(trust, 4),
                    "target_influence": round(influence, 6),
                    "risk_weight": round(w, 4),
                    "contribution": round(conf * trust * (1.0 + influence), 6),
                }
            )
        total_contribution = sum(s["contribution"] for s in segment_breakdown) or 1.0
        for s in segment_breakdown:
            s["normalized_contribution"] = round(s["contribution"] / total_contribution, 4)
        duration = time.perf_counter_ns() - t0
        return {
            "found": True,
            "path_id": path_id,
            "source": node_ids[0] if node_ids else "?",
            "target": node_ids[-1] if node_ids else "?",
            "length": len(edge_ids),
            "overall_risk_score": target_path.get("risk_score", 0.0),
            "segment_breakdown": segment_breakdown,
            "graph_version": self._graph_version,
            "schema_version": ATTACK_PATH_SCHEMA_VERSION,
            "execution_mode": "deterministic" if self._deterministic else "non-deterministic",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def get_path_by_id(self, path_id: str, paths_list: list[dict[str, Any]]) -> dict[str, Any]:
        for p in paths_list:
            if p.get("path_id") == path_id:
                return {
                    "found": True,
                    "path": p,
                    "schema_version": ATTACK_PATH_SCHEMA_VERSION,
                    "graph_version": self._graph_version,
                }
        return {
            "found": False,
            "path_id": path_id,
            "error": "path not found",
            "schema_version": ATTACK_PATH_SCHEMA_VERSION,
        }
