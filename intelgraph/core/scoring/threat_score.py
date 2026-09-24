from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from intelgraph.core.entity.base import BaseEntity
from intelgraph.core.evidence.evidence import Evidence


def _node_edge_count(node_id: str, graph: Any) -> int:
    """Count edges incident to this node."""
    count = 0
    for e in graph.edges.values():
        if e.source_id == node_id or e.target_id == node_id:
            count += 1
    return count


def _unique_source_tiers(entity: BaseEntity) -> set[int]:
    tiers: set[int] = set()
    for ev in getattr(entity, "evidence", ()):
        if isinstance(ev, Evidence):
            tiers.add(ev.source_tier)
        elif isinstance(ev, dict):
            tiers.add(ev.get("source_tier", 3))
    return tiers


def _evidence_source_count(entity: BaseEntity) -> int:
    sources: set[str] = set()
    for ev in getattr(entity, "evidence", ()):
        src = (
            ev.source
            if isinstance(ev, Evidence)
            else (ev.get("source", "") if isinstance(ev, dict) else "")
        )
        if src:
            sources.add(src)
    return len(sources)


def _temporal_score(entity: BaseEntity) -> float:
    now = datetime.now(UTC)
    first = getattr(entity, "first_seen", None) or getattr(entity, "created_at", None)
    last = getattr(entity, "last_seen", None) or getattr(entity, "updated_at", None)
    score = 0.0
    if first and last:
        if isinstance(first, str):
            first = datetime.fromisoformat(first.replace("Z", "+00:00"))
        if isinstance(last, str):
            last = datetime.fromisoformat(last.replace("Z", "+00:00"))
        active_span = (last - first).total_seconds()
        active_days = active_span / 86400
        # Longer active span = higher score (up to 7 pts)
        score += min(7.0, active_days * 0.5)
        # Recently active (last 7 days) = +8 pts
        if last and (now - last).total_seconds() < 7 * 86400:
            score += 8.0
    return min(15.0, score)


def _malicious_signal_score(entity: BaseEntity) -> float:
    score = 0.0
    # VirusTotal malicious_ratio from entity evidence or metadata
    vt_ratio = getattr(entity, "malicious_ratio", None)
    if vt_ratio is not None:
        score += min(10.0, vt_ratio * 10.0)
    # Ransomware flag
    if getattr(entity, "known_ransomware_use", False):
        score += 5.0
    # Evidence source tier check (tier-1 sources = +5)
    tiers = _unique_source_tiers(entity)
    if 1 in tiers:
        score += 5.0
    return min(20.0, score)


class ThreatScorer:
    """Computes a composite threat score (0-100) for a graph node.

    Components:
      - Base confidence (30 pts)
      - Relationship depth (20 pts)
      - Evidence breadth (15 pts)
      - Temporal activity (15 pts)
      - Malicious signals (20 pts)
    """

    def score(self, node: Any, graph: Any) -> float:
        if node is None:
            return 0.0
        entity: BaseEntity = node.entity
        node_id = node.id if hasattr(node, "id") else getattr(node, "node_id", "")

        # 1. Base confidence (30 pts)
        conf = getattr(entity, "confidence_score", 0) or 0
        base = (conf / 100.0) * 30.0

        # 2. Relationship depth (20 pts) — logarithmic
        edge_count = _node_edge_count(node_id, graph)
        rel_depth = min(20.0, math.log2(edge_count + 1) * 6.0)

        # 3. Evidence breadth (15 pts) — unique sources + unique tiers
        src_count = _evidence_source_count(entity)
        evidence_breadth = min(15.0, src_count * 3.0)

        # 4. Temporal activity (15 pts)
        temporal = _temporal_score(entity)

        # 5. Malicious signals (20 pts)
        malicious = _malicious_signal_score(entity)

        total = base + rel_depth + evidence_breadth + temporal + malicious
        return round(min(100.0, total), 2)

    def score_all(self, graph: Any) -> list[dict[str, Any]]:
        """Score all nodes in the graph and return sorted results."""
        results: list[dict[str, Any]] = []
        for node_id, node in graph.nodes.items():
            s = self.score(node, graph)
            entity = node.entity
            identifier = (
                getattr(entity, "ip", None)
                or getattr(entity, "domain_name", None)
                or getattr(entity, "cve_id", None)
                or node_id
            )
            results.append(
                {
                    "node_id": node_id,
                    "entity_type": type(entity).__name__,
                    "entity_identifier": identifier,
                    "threat_score": s,
                    "confidence": getattr(entity, "confidence_score", 0),
                    "evidence_count": len(getattr(entity, "evidence", ())),
                    "edge_count": _node_edge_count(node_id, graph),
                }
            )
        results.sort(key=lambda r: -r["threat_score"])
        return results

    def top_k(self, graph: Any, k: int = 10) -> list[dict[str, Any]]:
        return self.score_all(graph)[:k]


def compute_threat_scores(graph: Any) -> dict[str, float]:
    """Compute threat scores for all nodes, return {node_id: score} map."""
    scorer = ThreatScorer()
    scores = {}
    for node_id, node in graph.nodes.items():
        scores[node_id] = scorer.score(node, graph)
    return scores


_SCORE_CACHE: dict[int, dict[str, float]] = {}


def _compute_node_scores(graph: Any) -> dict[str, float]:
    """Cached node score computation for graph.nodes_summary."""
    gid = id(graph)
    if gid in _SCORE_CACHE:
        return _SCORE_CACHE[gid]
    scores = compute_threat_scores(graph)
    _SCORE_CACHE[gid] = scores
    return scores


def _clear_score_cache() -> None:
    _SCORE_CACHE.clear()
