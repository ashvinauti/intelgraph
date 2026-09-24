"""Investigation manager with pivot engine.

The pivot engine uses the in-memory IntelligenceGraph to walk from a
seed IOC to related infrastructure. It performs a bounded BFS traversal
and records each related entity as a Finding with its evidence summary.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

from intelgraph.core.investigation.models import (
    Finding,
    FindingType,
    Investigation,
    InvestigationStatus,
    Note,
    TimelineEvent,
)


class InvestigationManager:
    def __init__(self, state_path: str | None = None) -> None:
        self._state_path = state_path or os.environ.get(
            "INTELGRAPH_INVESTIGATION_STATE",
            "/tmp/intelgraph/investigations.json",
        )
        self._investigations: dict[str, Investigation] = {}
        self._load()

    def _load(self) -> None:
        import json
        try:
            with open(self._state_path) as f:
                data = json.load(f)
            for inv_data in data.get("investigations", []):
                inv = self._deserialize_investigation(inv_data)
                if inv is not None:
                    self._investigations[inv.investigation_id] = inv
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass

    def _save(self) -> None:
        import json
        os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
        data = {"investigations": [inv.to_dict() for inv in self._investigations.values()]}
        with open(self._state_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _deserialize_investigation(self, data: dict[str, Any]) -> Investigation | None:
        try:
            inv = Investigation(
                investigation_id=data["investigation_id"],
                name=data["name"],
                seed_ioc=data["seed_ioc"],
                seed_ioc_type=data["seed_ioc_type"],
                created_by=data.get("created_by", "system"),
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                status=InvestigationStatus[data.get("status", "open").upper()],
                tags=data.get("tags", []),
            )
            for f_data in data.get("findings", []):
                f = Finding(
                    finding_id=f_data["finding_id"],
                    investigation_id=f_data["investigation_id"],
                    ioc_value=f_data["ioc_value"],
                    ioc_type=f_data["ioc_type"],
                    finding_type=f_data["finding_type"],
                    confidence=f_data["confidence"],
                    evidence_summary=f_data["evidence_summary"],
                    related_entity_id=f_data.get("related_entity_id"),
                    relationships=f_data.get("relationships", []),
                    created_at=datetime.fromisoformat(f_data["created_at"]),
                )
                inv.findings.append(f)
            for t_data in data.get("timeline", []):
                t = TimelineEvent(
                    event_id=t_data["event_id"],
                    investigation_id=t_data["investigation_id"],
                    timestamp=datetime.fromisoformat(t_data["timestamp"]),
                    event_type=t_data["event_type"],
                    title=t_data["title"],
                    description=t_data["description"],
                    source=t_data.get("source", "analyst"),
                    metadata=t_data.get("metadata", {}),
                )
                inv.timeline.append(t)
            for n_data in data.get("notes", []):
                n = Note(
                    note_id=n_data["note_id"],
                    investigation_id=n_data["investigation_id"],
                    author=n_data["author"],
                    content=n_data["content"],
                    created_at=datetime.fromisoformat(n_data["created_at"]),
                    pinned=n_data.get("pinned", False),
                )
                inv.notes.append(n)
            return inv
        except (KeyError, ValueError):
            return None

    def list_investigations(self) -> list[Investigation]:
        return sorted(self._investigations.values(), key=lambda i: i.updated_at, reverse=True)

    def get_investigation(self, investigation_id: str) -> Investigation | None:
        return self._investigations.get(investigation_id)

    def create_investigation(
        self,
        name: str,
        seed_ioc: str,
        seed_ioc_type: str,
        created_by: str = "analyst",
        tags: list[str] | None = None,
    ) -> Investigation:
        inv_id = f"inv_{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        inv = Investigation(
            investigation_id=inv_id,
            name=name,
            seed_ioc=seed_ioc,
            seed_ioc_type=seed_ioc_type,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            tags=tags or [],
        )
        self._investigations[inv_id] = inv
        self._add_timeline_event(
            inv_id,
            "creation",
            "Investigation created",
            f"Investigation '{name}' started with seed IOC {seed_ioc} ({seed_ioc_type})",
            source=created_by,
        )
        self._save()
        return inv

    def delete_investigation(self, investigation_id: str) -> bool:
        existed = self._investigations.pop(investigation_id, None) is not None
        if existed:
            self._save()
        return existed

    def update_status(self, investigation_id: str, status: str) -> Investigation | None:
        inv = self._investigations.get(investigation_id)
        if inv is None:
            return None
        try:
            inv.status = InvestigationStatus[status.upper()]
        except KeyError:
            return None
        inv.updated_at = datetime.now(UTC)
        self._add_timeline_event(
            investigation_id,
            "status_change",
            f"Status changed to {status}",
            f"Investigation status changed from {inv.status} to {status}",
        )
        self._save()
        return inv

    def add_finding(self, investigation_id: str, finding: Finding) -> Investigation | None:
        inv = self._investigations.get(investigation_id)
        if inv is None:
            return None
        inv.findings.append(finding)
        inv.updated_at = datetime.now(UTC)
        self._add_timeline_event(
            investigation_id,
            "finding",
            f"Finding: {finding.ioc_value}",
            f"New {finding.finding_type} finding for {finding.ioc_value} ({finding.ioc_type}) — confidence {finding.confidence}%",
        )
        self._save()
        return inv

    def add_note(
        self,
        investigation_id: str,
        author: str,
        content: str,
        pinned: bool = False,
    ) -> Note | None:
        inv = self._investigations.get(investigation_id)
        if inv is None:
            return None
        note = Note(
            note_id=f"note_{uuid.uuid4().hex[:10]}",
            investigation_id=investigation_id,
            author=author,
            content=content,
            created_at=datetime.now(UTC),
            pinned=pinned,
        )
        inv.notes.append(note)
        inv.updated_at = datetime.now(UTC)
        self._save()
        return note

    def delete_note(self, investigation_id: str, note_id: str) -> bool:
        inv = self._investigations.get(investigation_id)
        if inv is None:
            return False
        before = len(inv.notes)
        inv.notes = [n for n in inv.notes if n.note_id != note_id]
        if len(inv.notes) < before:
            inv.updated_at = datetime.now(UTC)
            self._save()
            return True
        return False

    def get_timeline(self, investigation_id: str) -> list[TimelineEvent]:
        inv = self._investigations.get(investigation_id)
        if inv is None:
            return []
        return sorted(inv.timeline, key=lambda e: e.timestamp)

    def add_timeline_event(
        self,
        investigation_id: str,
        event_type: str,
        title: str,
        description: str,
        source: str = "analyst",
        metadata: dict[str, Any] | None = None,
    ) -> TimelineEvent | None:
        return self._add_timeline_event(
            investigation_id, event_type, title, description, source, metadata
        )

    def _add_timeline_event(
        self,
        investigation_id: str,
        event_type: str,
        title: str,
        description: str,
        source: str = "analyst",
        metadata: dict[str, Any] | None = None,
    ) -> TimelineEvent | None:
        inv = self._investigations.get(investigation_id)
        if inv is None:
            return None
        event = TimelineEvent(
            event_id=f"tl_{uuid.uuid4().hex[:10]}",
            investigation_id=investigation_id,
            timestamp=datetime.now(UTC),
            event_type=event_type,
            title=title,
            description=description,
            source=source,
            metadata=metadata or {},
        )
        inv.timeline.append(event)
        inv.updated_at = datetime.now(UTC)
        return event

    def pivot_from_seed(
        self,
        investigation_id: str,
        graph: Any,
        max_depth: int = 2,
        entity_types: list[str] | None = None,
    ) -> list[Finding]:
        """Walk the graph from the seed IOC and record related entities as findings.

        Uses bounded BFS: starts from the entity matching the seed IOC, walks
        up to max_depth hops, and records each newly discovered related entity
        as a PIVOT finding with its relationship evidence summary.
        """
        inv = self._investigations.get(investigation_id)
        if inv is None:
            return []

        seed_node = self._find_node_by_ioc(graph, inv.seed_ioc, inv.seed_ioc_type)
        if seed_node is None:
            return []

        from intelgraph.core.graph.node import Node

        visited: set[str] = {graph_node_id(seed_node)}
        findings: list[Finding] = []

        current_layer = [seed_node]
        for depth in range(1, max_depth + 1):
            next_layer: list[Node] = []
            for node in current_layer:
                node_id = graph_node_id(node)
                for neighbor in graph.neighbors(node_id):
                    neighbor_id = graph_node_id(neighbor)
                    if neighbor_id in visited:
                        continue
                    visited.add(neighbor_id)

                    if entity_types and neighbor.entity.entity_type.type_name not in entity_types:
                        continue

                    edges = self._edges_between(graph, node_id, neighbor_id)
                    rel_summary = self._summarize_relationships(edges)

                    finding = Finding(
                        finding_id=f"find_{uuid.uuid4().hex[:10]}",
                        investigation_id=investigation_id,
                        ioc_value=ioc_display_value(neighbor),
                        ioc_type=neighbor.entity.entity_type.type_name,
                        finding_type=str(FindingType.PIVOT),
                        confidence=neighbor.entity.confidence_score,
                        evidence_summary=rel_summary,
                        related_entity_id=neighbor_id,
                        relationships=edges,
                    )
                    findings.append(finding)
                    inv.findings.append(finding)
                    next_layer.append(neighbor)
            current_layer = next_layer

        if findings:
            inv.updated_at = datetime.now(UTC)
            self._add_timeline_event(
                investigation_id,
                "pivot",
                f"Pivot discovered {len(findings)} related entities",
                f"Graph traversal (depth={max_depth}) from {inv.seed_ioc} found {len(findings)} related entities.",
                source="pivot-engine",
                metadata={"max_depth": max_depth, "found_count": len(findings)},
            )
            self._save()
        return findings

    def _find_node_by_ioc(self, graph: Any, ioc_value: str, ioc_type: str) -> Any:
        from intelgraph.core.graph.node import Node

        ioc_lower = ioc_value.lower().strip()
        for node_id, node in getattr(graph, "nodes", {}).items():
            entity = node.entity
            if entity.entity_type.type_name != ioc_type:
                continue
            display = ioc_display_value(node)
            if display and display.lower() == ioc_lower:
                return node
        return None

    def _edges_between(self, graph: Any, src_id: str, tgt_id: str) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for edge_id in graph.node_edges.get(src_id, set()):
            edge = graph.edges.get(edge_id)
            if edge is None:
                continue
            src_tgt = graph.edge_node_map.get(edge_id)
            if src_tgt is None:
                continue
            other = src_tgt[1] if src_tgt[0] == src_id else src_tgt[0]
            if other == tgt_id:
                rel = edge.relationship
                edges.append({
                    "edge_id": edge_id,
                    "relationship_type": rel.type.name.lower() if hasattr(rel, "type") else str(rel),
                    "source_id": src_tgt[0],
                    "target_id": src_tgt[1],
                    "confidence": getattr(rel, "confidence_score", 0),
                })
        return edges

    def _summarize_relationships(self, edges: list[dict[str, Any]]) -> str:
        if not edges:
            return "No direct relationship metadata available."
        types: dict[str, int] = {}
        for e in edges:
            rtype = e.get("relationship_type", "unknown")
            types[rtype] = types.get(rtype, 0) + 1
        parts = [f"{count}x {rtype}" for rtype, count in sorted(types.items())]
        return "Related via: " + ", ".join(parts) + "."


def graph_node_id(node: Any) -> str:
    """Return the node identifier from a graph Node or ULID string."""
    if isinstance(node, str):
        return node
    for attr in ("node_id", "entity_id", "id"):
        val = getattr(node, attr, None)
        if val is not None:
            return str(val)
    return str(node)


def ioc_display_value(node: Any) -> str:
    """Extract the human-readable indicator value from a graph node."""
    try:
        entity = node.entity
    except AttributeError:
        return ""
    for attr in ("ip", "domain_name", "cve_id", "hash_value", "url", "email", "username", "name"):
        val = getattr(entity, attr, None)
        if val:
            return str(val)
    return str(getattr(entity, "id", ""))