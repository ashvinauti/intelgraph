from collections import deque
from collections.abc import Callable
from typing import Any

from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node


class GraphQueryEngine:
    def __init__(
        self,
        graph: IntelligenceGraph,
        verification_lookup: Callable[[str], dict[str, Any] | None] | None = None,
        chain_lookup: Callable[[str], dict[str, Any] | None] | None = None,
    ) -> None:
        self._graph = graph
        self._verification_lookup = verification_lookup
        self._chain_lookup = chain_lookup

    def _get_verification(self, entity_id: str) -> dict[str, Any] | None:
        if self._verification_lookup is None:
            return None
        return self._verification_lookup(entity_id)

    def _get_chain(self, entity_id: str) -> dict[str, Any] | None:
        if self._chain_lookup is None:
            return None
        return self._chain_lookup(entity_id)

    def _matches_filters(
        self,
        node: Node,
        entity_type: str | None = None,
        verification_state: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        source_trust_min: float | None = None,
    ) -> bool:
        if entity_type is not None and node.entity_type != entity_type:
            return False
        if any(
            v is not None
            for v in [verification_state, confidence_min, confidence_max, source_trust_min]
        ):
            vrec = self._get_verification(node.id)
            if vrec is None:
                return False
            if (
                verification_state is not None
                and vrec.get("verification_state") != verification_state
            ):
                return False
            if confidence_min is not None and vrec.get("confidence", 0) < confidence_min:
                return False
            if confidence_max is not None and vrec.get("confidence", 100) > confidence_max:
                return False
            if source_trust_min is not None:
                chain = self._get_chain(node.id)
                if chain is None:
                    return False
                evidence_list = chain.get("evidence", [])
                if not evidence_list:
                    return False
                avg_trust = sum(e.get("confidence", 0) for e in evidence_list) / len(evidence_list)
                if avg_trust < source_trust_min:
                    return False
        return True

    def filter_nodes(
        self,
        entity_type: str | None = None,
        verification_state: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        source_trust_min: float | None = None,
        limit: int = 0,
        offset: int = 0,
    ) -> list[Node]:
        result: list[Node] = []
        for node in self._graph.nodes.values():
            if self._matches_filters(
                node,
                entity_type,
                verification_state,
                confidence_min,
                confidence_max,
                source_trust_min,
            ):
                result.append(node)
        if offset > 0:
            result = result[offset:]
        if limit > 0:
            result = result[:limit]
        return result

    def find_path(self, start_id: str, end_id: str) -> list[dict[str, Any]]:
        nodes = self._graph.shortest_path(start_id, end_id)
        return [
            {"id": n.id, "entity_type": n.entity_type, "name": self._node_name(n)} for n in nodes
        ]

    def enumerate_paths(
        self, start_id: str, end_id: str, max_depth: int = 5
    ) -> list[list[dict[str, Any]]]:
        if start_id not in self._graph.nodes or end_id not in self._graph.nodes:
            return []
        if max_depth < 1:
            return []
        paths: list[list[str]] = []
        stack: list[tuple[str, list[str]]] = [(start_id, [start_id])]
        while stack:
            current, path = stack.pop()
            if len(path) > max_depth:
                continue
            for neighbor_id in self._graph.adjacency.get(current, set()):
                if neighbor_id in path:
                    continue
                new_path = path + [neighbor_id]
                if neighbor_id == end_id:
                    paths.append(new_path)
                elif len(new_path) < max_depth:
                    stack.append((neighbor_id, new_path))
        result: list[list[dict[str, Any]]] = []
        for p in paths:
            result.append(
                [
                    {
                        "id": nid,
                        "entity_type": self._graph.nodes[nid].entity_type,
                        "name": self._node_name(self._graph.nodes[nid]),
                    }
                    for nid in p
                ]
            )
        return result

    def bfs_query(
        self,
        start_id: str,
        entity_type: str | None = None,
        verification_state: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        source_trust_min: float | None = None,
        limit: int = 0,
        offset: int = 0,
    ) -> list[Node]:
        if start_id not in self._graph.nodes:
            return []
        visited: set[str] = set()
        queue: deque[str] = deque()
        result: list[Node] = []
        visited.add(start_id)
        queue.append(start_id)
        while queue:
            current = queue.popleft()
            node = self._graph.nodes.get(current)
            if node is None:
                continue
            if self._matches_filters(
                node,
                entity_type,
                verification_state,
                confidence_min,
                confidence_max,
                source_trust_min,
            ):
                result.append(node)
            for neighbor_id in self._graph.adjacency.get(current, set()):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append(neighbor_id)
        if offset > 0:
            result = result[offset:]
        if limit > 0:
            result = result[:limit]
        return result

    def dfs_query(
        self,
        start_id: str,
        entity_type: str | None = None,
        verification_state: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        source_trust_min: float | None = None,
        limit: int = 0,
        offset: int = 0,
    ) -> list[Node]:
        if start_id not in self._graph.nodes:
            return []
        visited: set[str] = set()
        stack: list[str] = [start_id]
        result: list[Node] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            node = self._graph.nodes.get(current)
            if node is None:
                continue
            if self._matches_filters(
                node,
                entity_type,
                verification_state,
                confidence_min,
                confidence_max,
                source_trust_min,
            ):
                result.append(node)
            for neighbor_id in sorted(self._graph.adjacency.get(current, set()), reverse=True):
                if neighbor_id not in visited:
                    stack.append(neighbor_id)
        if offset > 0:
            result = result[offset:]
        if limit > 0:
            result = result[:limit]
        return result

    def bfs_depth_query(
        self,
        start_id: str,
        max_depth: int,
        entity_type: str | None = None,
        verification_state: str | None = None,
        confidence_min: float | None = None,
        confidence_max: float | None = None,
        source_trust_min: float | None = None,
        limit: int = 0,
        offset: int = 0,
    ) -> list[Node]:
        if start_id not in self._graph.nodes or max_depth < 0:
            return []
        visited: set[str] = {start_id}
        queue: deque[tuple[str, int]] = deque()
        queue.append((start_id, 0))
        result: list[Node] = []
        while queue:
            current, depth = queue.popleft()
            if depth > max_depth:
                continue
            node = self._graph.nodes.get(current)
            if node is None:
                continue
            if self._matches_filters(
                node,
                entity_type,
                verification_state,
                confidence_min,
                confidence_max,
                source_trust_min,
            ):
                result.append(node)
            if depth < max_depth:
                for neighbor_id in self._graph.adjacency.get(current, set()):
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        queue.append((neighbor_id, depth + 1))
        if offset > 0:
            result = result[offset:]
        if limit > 0:
            result = result[:limit]
        return result

    @staticmethod
    def _node_name(node: Node) -> str:
        ent = node.entity
        for attr in ("name", "domain_name", "address", "username", "ip", "fingerprint"):
            val = getattr(ent, attr, None)
            if val:
                return str(val)
        return node.id
