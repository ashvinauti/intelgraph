from __future__ import annotations

from collections import deque
from typing import Any

from intelgraph.core.graph.graph import IntelligenceGraph


class GraphAnalytics:
    def __init__(self, graph: IntelligenceGraph) -> None:
        self._graph = graph

    def degree_centrality(self, node_id: str) -> float:
        node_count = self._graph.node_count
        if node_count <= 1:
            return 0.0
        degree = len(self._graph.adjacency.get(node_id, set()))
        return degree / (node_count - 1)

    def page_rank(
        self,
        node_id: str,
        damping: float = 0.85,
        max_iterations: int = 100,
        tolerance: float = 1e-8,
    ) -> float:
        n = self._graph.node_count
        if n == 0:
            return 0.0
        if n == 1:
            return 1.0
        node_ids = sorted(self._graph.nodes.keys())
        index_of = {nid: i for i, nid in enumerate(node_ids)}

        out_degree = [len(self._graph.forward_adjacency.get(nid, set())) for nid in node_ids]
        pr = [1.0 / n] * n
        dangling = [1.0 / n if d == 0 else 0.0 for d in out_degree]
        teleport = (1.0 - damping) / n

        for _ in range(max_iterations):
            prev = pr[:]
            dangling_sum = sum(pr[i] * dangling[i] for i in range(n))
            for i in range(n):
                incoming_sum = 0.0
                nid = node_ids[i]
                for src_id in self._graph.reverse_adjacency.get(nid, set()):
                    src_idx = index_of.get(src_id)
                    if src_idx is not None and out_degree[src_idx] > 0:
                        incoming_sum += prev[src_idx] / out_degree[src_idx]
                pr[i] = teleport + damping * (incoming_sum + dangling_sum)
            diff = sum(abs(pr[i] - prev[i]) for i in range(n))
            if diff < tolerance:
                break

        idx = index_of.get(node_id)
        if idx is None:
            return 0.0
        return pr[idx]

    def betweenness_centrality(self, node_id: str) -> float:
        n = self._graph.node_count
        if n <= 2:
            return 0.0
        if node_id not in self._graph.nodes:
            return 0.0
        cb = dict.fromkeys(self._graph.nodes, 0.0)
        node_ids_sorted = sorted(self._graph.nodes.keys())
        for s in node_ids_sorted:
            stack: list[str] = []
            pred: dict[str, list[str]] = {v: [] for v in node_ids_sorted}
            sigma: dict[str, float] = dict.fromkeys(node_ids_sorted, 0.0)
            sigma[s] = 1.0
            dist: dict[str, int] = dict.fromkeys(node_ids_sorted, -1)
            dist[s] = 0
            q: deque[str] = deque([s])
            while q:
                v = q.popleft()
                stack.append(v)
                for w in sorted(self._graph.adjacency.get(v, set())):
                    if dist[w] < 0:
                        q.append(w)
                        dist[w] = dist[v] + 1
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        pred[w].append(v)
            delta: dict[str, float] = dict.fromkeys(node_ids_sorted, 0.0)
            while stack:
                w = stack.pop()
                for v in pred[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
                if w != s:
                    cb[w] += delta[w]
        if n > 2:
            factor = 2.0 / ((n - 1) * (n - 2))
            for k in cb:
                cb[k] *= factor
        return cb.get(node_id, 0.0)

    def closeness_centrality(self, node_id: str) -> float:
        n = self._graph.node_count
        if n <= 1:
            return 0.0
        if node_id not in self._graph.nodes:
            return 0.0
        dist: dict[str, int] = {node_id: 0}
        q: deque[str] = deque([node_id])
        while q:
            v = q.popleft()
            for w in self._graph.adjacency.get(v, set()):
                if w not in dist:
                    dist[w] = dist[v] + 1
                    q.append(w)
        reachable = {k: v for k, v in dist.items() if k != node_id}
        r = len(reachable)
        if r == 0:
            return 0.0
        total_distance = sum(reachable.values())
        if total_distance == 0:
            return 0.0
        return (r / (n - 1)) * (r / total_distance)

    def local_clustering(self, node_id: str) -> float:
        neighbors = self._graph.adjacency.get(node_id, set())
        k = len(neighbors)
        if k < 2:
            return 0.0
        edges = 0
        for u in neighbors:
            for v in self._graph.adjacency.get(u, set()):
                if v in neighbors and v > u:
                    edges += 1
        return (2.0 * edges) / (k * (k - 1))

    def average_clustering_coefficient(self) -> float:
        n = self._graph.node_count
        if n == 0:
            return 0.0
        total = 0.0
        for nid in self._graph.nodes:
            total += self.local_clustering(nid)
        return total / n

    def max_degree(self) -> int:
        if self._graph.node_count == 0:
            return 0
        return max(len(self._graph.adjacency.get(nid, set())) for nid in self._graph.nodes)

    def min_degree(self) -> int:
        if self._graph.node_count == 0:
            return 0
        return min(len(self._graph.adjacency.get(nid, set())) for nid in self._graph.nodes)

    def degree_histogram(self) -> list[dict[str, int]]:
        if self._graph.node_count == 0:
            return []
        degrees = [len(self._graph.adjacency.get(nid, set())) for nid in self._graph.nodes]
        max_d = max(degrees)
        counts = [0] * (max_d + 1)
        for d in degrees:
            counts[d] += 1
        return [{"degree": d, "count": c} for d, c in enumerate(counts)]

    def stats(self, detail: bool = False) -> dict[str, Any]:
        n = self._graph.node_count
        e = self._graph.edge_count
        density = (2.0 * e / (n * (n - 1))) if n > 1 else 0.0
        total_degree = sum(len(self._graph.adjacency.get(nid, set())) for nid in self._graph.nodes)
        avg_degree = (total_degree / n) if n > 0 else 0.0
        result: dict[str, Any] = {
            "node_count": n,
            "edge_count": e,
            "density": round(density, 6),
            "average_degree": round(avg_degree, 4),
        }
        if detail:
            result["clustering_coefficient"] = round(self.average_clustering_coefficient(), 6)
            result["max_degree"] = self.max_degree()
            result["min_degree"] = self.min_degree()
            result["degree_histogram"] = self.degree_histogram()
        return result
