from __future__ import annotations

import heapq
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from intelgraph.core.enterprise.observability import get_metrics
from intelgraph.core.graph.graph import IntelligenceGraph


class _DSU:
    def __init__(self, n: int) -> None:
        self._parent = list(range(n))
        self._rank = [0] * n

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x: int, y: int) -> bool:
        xr = self.find(x)
        yr = self.find(y)
        if xr == yr:
            return False
        if self._rank[xr] < self._rank[yr]:
            self._parent[xr] = yr
        elif self._rank[xr] > self._rank[yr]:
            self._parent[yr] = xr
        else:
            self._parent[yr] = xr
            self._rank[xr] += 1
        return True


def _default_weight(edge: Any) -> float:
    rel = edge.relationship
    return float(101 - rel.confidence_score)


class GraphAlgorithms:
    def __init__(
        self,
        graph: IntelligenceGraph,
        weight_fn: Callable[[Any], float] | None = None,
    ) -> None:
        self._graph = graph
        self._weight_fn = weight_fn or _default_weight
        self._metrics = get_metrics()

    def _record_duration(self, name: str, duration_ns: int) -> None:
        self._metrics.set_gauge(f"algorithm_{name}_duration_ms", duration_ns / 1_000_000)
        n = self._graph.node_count
        e = self._graph.edge_count
        self._metrics.set_gauge(f"algorithm_{name}_graph_nodes", float(n))
        self._metrics.set_gauge(f"algorithm_{name}_graph_edges", float(e))

    def _get_edge_weight(self, edge_id: str) -> float:
        edge = self._graph.edges.get(edge_id)
        if edge is None:
            return 1.0
        return self._weight_fn(edge)

    def _enumerate_weighted_edges(self) -> list[tuple[float, str, str, str]]:
        result: list[tuple[float, str, str, str]] = []
        for eid, _edge in self._graph.edges.items():
            src_tgt = self._graph.edge_node_map.get(eid)
            if src_tgt is None:
                continue
            src, tgt = src_tgt
            weight = self._get_edge_weight(eid)
            result.append((weight, eid, src, tgt))
        return result

    def mst_kruskal(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = sorted(self._graph.nodes.keys())
        n = len(node_ids)
        index_of = {nid: i for i, nid in enumerate(node_ids)}
        edges_by_weight = sorted(self._enumerate_weighted_edges(), key=lambda x: x[0])
        dsu = _DSU(n)
        mst_edges: list[dict[str, Any]] = []
        total_weight = 0.0
        for weight, eid, src, tgt in edges_by_weight:
            ui = index_of[src]
            vi = index_of[tgt]
            if dsu.union(ui, vi):
                mst_edges.append(
                    {
                        "edge_id": eid,
                        "source": src,
                        "target": tgt,
                        "weight": round(weight, 4),
                    }
                )
                total_weight += weight
        duration = time.perf_counter_ns() - t0
        self._record_duration("mst_kruskal", duration)
        return {
            "algorithm": "kruskal",
            "edges": mst_edges,
            "edge_count": len(mst_edges),
            "total_weight": round(total_weight, 4),
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def mst_prim(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = list(self._graph.nodes.keys())
        n = len(node_ids)
        if n == 0:
            return {
                "algorithm": "prim",
                "edges": [],
                "edge_count": 0,
                "total_weight": 0.0,
                "execution_time_ms": 0.0,
            }
        visited: set[str] = set()
        pq: list[tuple[float, str, str | None, str | None]] = []
        start = node_ids[0]
        visited.add(start)
        for nb in self._graph.adjacency.get(start, set()):
            for eid in self._graph.node_edges.get(start, set()):
                src_tgt = self._graph.edge_node_map.get(eid)
                if src_tgt is None:
                    continue
                s, t = src_tgt
                if (s == start and t == nb) or (t == start and s == nb):
                    w = self._get_edge_weight(eid)
                    heapq.heappush(pq, (w, eid, start, nb))
                    break
        mst_edges: list[dict[str, Any]] = []
        total_weight = 0.0
        while pq and len(visited) < n:
            weight, eid, src, tgt = heapq.heappop(pq)
            if tgt in visited:
                continue
            visited.add(tgt)
            mst_edges.append(
                {
                    "edge_id": eid,
                    "source": src,
                    "target": tgt,
                    "weight": round(weight, 4),
                }
            )
            total_weight += weight
            node = tgt
            for nb in self._graph.adjacency.get(node, set()):
                if nb in visited:
                    continue
                for eid2 in self._graph.node_edges.get(node, set()):
                    src_tgt2 = self._graph.edge_node_map.get(eid2)
                    if src_tgt2 is None:
                        continue
                    s2, t2 = src_tgt2
                    if (s2 == node and t2 == nb) or (t2 == node and s2 == nb):
                        w2 = self._get_edge_weight(eid2)
                        heapq.heappush(pq, (w2, eid2, node, nb))
                        break
        duration = time.perf_counter_ns() - t0
        self._record_duration("mst_prim", duration)
        return {
            "algorithm": "prim",
            "edges": mst_edges,
            "edge_count": len(mst_edges),
            "total_weight": round(total_weight, 4),
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def scc_tarjan(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = sorted(self._graph.nodes.keys())
        index: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        on_stack: dict[str, bool] = {}
        stack: list[str] = []
        components: list[list[str]] = []
        idx_counter = 0

        def strongconnect(v: str) -> None:
            nonlocal idx_counter
            index[v] = idx_counter
            lowlink[v] = idx_counter
            idx_counter += 1
            stack.append(v)
            on_stack[v] = True
            for w in sorted(self._graph.forward_adjacency.get(v, set())):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif on_stack.get(w, False):
                    lowlink[v] = min(lowlink[v], index[w])
            if lowlink[v] == index[v]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp.append(w)
                    if w == v:
                        break
                components.append(comp)

        for v in node_ids:
            if v not in index:
                strongconnect(v)

        component_map: dict[str, list[str]] = {}
        for i, comp in enumerate(components):
            label = f"scc_{i}"
            component_map[label] = sorted(comp)

        duration = time.perf_counter_ns() - t0
        self._record_duration("scc_tarjan", duration)
        return {
            "algorithm": "tarjan",
            "components": component_map,
            "count": len(components),
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def diameter(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = list(self._graph.nodes.keys())
        n = len(node_ids)
        if n <= 1:
            duration = time.perf_counter_ns() - t0
            self._record_duration("diameter", duration)
            return {"diameter": 0, "path": [], "execution_time_ms": round(duration / 1_000_000, 2)}

        def bfs_farthest(start: str) -> tuple[str, int, list[str]]:
            dist: dict[str, int] = {start: 0}
            prev: dict[str, str | None] = {start: None}
            q: deque[str] = deque([start])
            farthest = start
            while q:
                v = q.popleft()
                for w in self._graph.adjacency.get(v, set()):
                    if w not in dist:
                        dist[w] = dist[v] + 1
                        prev[w] = v
                        q.append(w)
                        if dist[w] > dist[farthest]:
                            farthest = w
            path: list[str] = []
            cur: str | None = farthest
            while cur is not None:
                path.append(cur)
                cur = prev.get(cur)
            path.reverse()
            return farthest, dist[farthest], path

        farthest_a, _, _ = bfs_farthest(node_ids[0])
        farthest_b, diam_len, diam_path = bfs_farthest(farthest_a)

        duration = time.perf_counter_ns() - t0
        self._record_duration("diameter", duration)
        return {
            "diameter": diam_len,
            "path": diam_path,
            "from_node": farthest_a,
            "to_node": farthest_b,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def astar(
        self,
        source_id: str,
        target_id: str,
        heuristic: Callable[[str, str], float] | None = None,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if source_id not in self._graph.nodes or target_id not in self._graph.nodes:
            return {"path": [], "length": 0, "execution_time_ms": 0.0, "nodes_visited": 0}
        if source_id == target_id:
            return {"path": [source_id], "length": 0, "execution_time_ms": 0.0, "nodes_visited": 1}

        h = heuristic or (lambda a, b: 0.0)
        open_set: list[tuple[float, float, str]] = []
        heapq.heappush(open_set, (h(source_id, target_id), 0.0, source_id))
        g_score: dict[str, float] = {source_id: 0.0}
        came_from: dict[str, str | None] = {source_id: None}
        visited_count = 0

        while open_set:
            _, cost, current = heapq.heappop(open_set)
            visited_count += 1
            if current == target_id:
                path: list[str] = []
                cur: str | None = current
                while cur is not None:
                    path.append(cur)
                    cur = came_from.get(cur)
                path.reverse()
                duration = time.perf_counter_ns() - t0
                self._record_duration("astar", duration)
                return {
                    "path": path,
                    "length": len(path) - 1,
                    "total_cost": round(g_score[current], 4),
                    "execution_time_ms": round(duration / 1_000_000, 2),
                    "nodes_visited": visited_count,
                }
            for neighbor in self._graph.forward_adjacency.get(current, set()):
                edge_weight = 1.0
                for eid in self._graph.node_edges.get(current, set()):
                    src_tgt = self._graph.edge_node_map.get(eid)
                    if src_tgt is None:
                        continue
                    s, t = src_tgt
                    if s == current and t == neighbor:
                        edge_weight = self._get_edge_weight(eid)
                        break
                tentative = g_score[current] + edge_weight
                if tentative < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative
                    f_score = tentative + h(neighbor, target_id)
                    heapq.heappush(open_set, (f_score, tentative, neighbor))

        duration = time.perf_counter_ns() - t0
        self._record_duration("astar", duration)
        return {
            "path": [],
            "length": 0,
            "execution_time_ms": round(duration / 1_000_000, 2),
            "nodes_visited": visited_count,
        }

    def path_length_statistics(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = list(self._graph.nodes.keys())
        n = len(node_ids)
        if n <= 1:
            return {"min": 0, "max": 0, "mean": 0.0, "median": 0, "stddev": 0.0, "sample_count": 0}

        lengths: list[int] = []
        sample_size = min(n, 50)
        import random

        random.seed(42)
        samples = random.sample(node_ids, sample_size) if sample_size < n else node_ids
        for src in samples:
            dist: dict[str, int] = {src: 0}
            q: deque[str] = deque([src])
            while q:
                v = q.popleft()
                for w in self._graph.adjacency.get(v, set()):
                    if w not in dist:
                        dist[w] = dist[v] + 1
                        q.append(w)
            for tgt in node_ids:
                if tgt != src and tgt in dist:
                    lengths.append(dist[tgt])
        if not lengths:
            return {"min": 0, "max": 0, "mean": 0.0, "median": 0, "stddev": 0.0, "sample_count": 0}
        lengths.sort()
        mean = sum(lengths) / len(lengths)
        median = lengths[len(lengths) // 2] if lengths else 0
        variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
        stddev = variance**0.5
        duration = time.perf_counter_ns() - t0
        self._record_duration("path_stats", duration)
        return {
            "min": lengths[0],
            "max": lengths[-1],
            "mean": round(mean, 4),
            "median": median,
            "stddev": round(stddev, 4),
            "sample_count": len(lengths),
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def connected_component_distribution(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = list(self._graph.nodes.keys())
        visited: set[str] = set()
        components: list[list[str]] = []
        for start in node_ids:
            if start in visited:
                continue
            comp: list[str] = []
            q: deque[str] = deque([start])
            visited.add(start)
            while q:
                v = q.popleft()
                comp.append(v)
                for w in self._graph.adjacency.get(v, set()):
                    if w not in visited:
                        visited.add(w)
                        q.append(w)
            components.append(comp)
        sizes = sorted([len(c) for c in components], reverse=True)
        largest = sizes[0] if sizes else 0
        isolated = sum(1 for s in sizes if s == 1)
        duration = time.perf_counter_ns() - t0
        self._record_duration("connected_components", duration)
        return {
            "component_count": len(components),
            "size_distribution": sizes,
            "largest_component_size": largest,
            "largest_component_fraction": round(largest / max(len(node_ids), 1), 4),
            "isolated_node_count": isolated,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def connectivity_metrics(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        n = self._graph.node_count
        e = self._graph.edge_count
        if n <= 1:
            return {
                "is_connected": n == 1,
                "component_count": n,
                "edge_density": 0.0,
                "avg_degree": 0.0,
                "is_tree": n == 1,
            }
        cc = self.connected_component_distribution()
        is_connected = cc["component_count"] == 1
        density = (2.0 * e / (n * (n - 1))) if n > 1 else 0.0
        total_deg = sum(len(self._graph.adjacency.get(nid, set())) for nid in self._graph.nodes)
        avg_deg = total_deg / n
        undirected_pairs: set[tuple[str, str]] = set()
        for _eid, (src, tgt) in self._graph.edge_node_map.items():
            pair = (src, tgt) if src <= tgt else (tgt, src)
            undirected_pairs.add(pair)
        unique_edges = len(undirected_pairs)
        is_tree = is_connected and unique_edges == n - 1
        duration = time.perf_counter_ns() - t0
        self._record_duration("connectivity", duration)
        return {
            "is_connected": is_connected,
            "component_count": cc["component_count"],
            "largest_component_size": cc["largest_component_size"],
            "edge_density": round(density, 6),
            "average_degree": round(avg_deg, 4),
            "is_tree": is_tree,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }
