import logging
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime
from typing import Any

from intelgraph.core.entity import BaseEntity
from intelgraph.core.evidence import Evidence
from intelgraph.core.evidence_chain import (
    ChainManager,
    ConfidenceComputer,
    ContradictionDetector,
    EvidenceChain,
    EvidenceItem,
    SupportType,
)
from intelgraph.core.graph.edge import Edge
from intelgraph.core.graph.node import Node
from intelgraph.core.graph.storage import GraphStorage
from intelgraph.core.relationship import Relationship
from intelgraph.core.source.resolution import EntityMatcher, MergeEngine

logger = logging.getLogger(__name__)

_INFER_SUPPORTS = frozenset(
    {
        "zararsız",
        "benign",
        "clean",
        "safe",
        "legitimate",
        "normal",
        "harmless",
        "authorized",
        "allowed",
    }
)
_INFER_CONTRADICTS = frozenset(
    {
        "zararlı",
        "malicious",
        "c2",
        "threat",
        "attack",
        "phishing",
        "malware",
        "exploit",
        "suspicious",
        "harmful",
        "dangerous",
        "compromised",
    }
)


@dataclass
class IntelligenceGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)
    adjacency: dict[str, set[str]] = field(default_factory=dict)
    forward_adjacency: dict[str, set[str]] = field(default_factory=dict)
    reverse_adjacency: dict[str, set[str]] = field(default_factory=dict)
    node_edges: dict[str, set[str]] = field(default_factory=dict)
    edge_node_map: dict[str, tuple[str, str]] = field(default_factory=dict)
    previous_versions: dict[str, list[Node]] = field(default_factory=dict)
    entity_matcher: EntityMatcher | None = None
    merge_engine: MergeEngine | None = None
    evidence_contradiction_detector: ContradictionDetector | None = None
    confidence_computer: ConfidenceComputer | None = None
    contradiction_records: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    chain_manager: ChainManager | None = None
    storage_path: str | None = None

    # Hash-based pre-filter index for EntityMatcher.
    # Primary:   maps normalized exact-field values → node IDs (exact match)
    # Secondary: maps (etype, char-bag, length) → node IDs (name-similarity match)
    _entity_index: dict[str, set[str]] = field(default_factory=dict, repr=False)
    _entity_sig_index: dict[tuple[str, frozenset[str], int], set[str]] = field(
        default_factory=dict, repr=False
    )

    _storage: GraphStorage | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.entity_matcher is None:
            self.entity_matcher = EntityMatcher(
                match_threshold=0.9,
                exact_fields=["ip", "domain_name", "email", "name"],
            )
        if self.merge_engine is None:
            self.merge_engine = MergeEngine(default_strategy="most_confident")
        if self.evidence_contradiction_detector is None:
            self.evidence_contradiction_detector = ContradictionDetector()
        if self.confidence_computer is None:
            self.confidence_computer = ConfidenceComputer()
        if self.storage_path is not None:
            self._storage = GraphStorage(self.storage_path)
            self._load_from_storage()

    def _load_from_storage(self) -> None:
        """Rebuild in-memory state from SQLite storage (called from __post_init__)."""
        if self._storage is None:
            return
        for node in self._storage.load_nodes():
            self.nodes[node.id] = node
            self._ensure_node_structures(node.id)
            self._index_add(node.id, node.entity)
        for edge in self._storage.load_edges():
            self.edges[edge.id] = edge
            self.adjacency.setdefault(edge.source_id, set()).add(edge.target_id)
            self.adjacency.setdefault(edge.target_id, set()).add(edge.source_id)
            self.forward_adjacency.setdefault(edge.source_id, set()).add(edge.target_id)
            self.reverse_adjacency.setdefault(edge.target_id, set()).add(edge.source_id)
            self.node_edges.setdefault(edge.source_id, set()).add(edge.id)
            self.node_edges.setdefault(edge.target_id, set()).add(edge.id)
            self.edge_node_map[edge.id] = (edge.source_id, edge.target_id)
        self.previous_versions = self._storage.load_previous_versions()
        logger.info(
            "Loaded %d nodes, %d edges, %d versioned entries from storage",
            len(self.nodes),
            len(self.edges),
            len(self.previous_versions),
        )

    def add_entity(self, entity: BaseEntity, overwrite: bool = False) -> Node:
        if not entity.id:
            raise ValueError(f"entity.id must not be empty, got {entity.id!r}")
        node = Node(entity=entity)

        # 1) Exact ID match (existing behavior)
        if node.id in self.nodes:
            old_node = self.nodes[node.id]
            if not overwrite:
                self.previous_versions.setdefault(node.id, []).append(old_node)
                if self._storage is not None:
                    self._storage.save_previous_version(node.id, old_node)
                logger.info("Entity %s already exists, merging (previous version saved)", node.id)
            else:
                logger.info(
                    "Entity %s already exists, overwriting (previous version NOT saved)", node.id
                )
            self._index_remove(node.id, old_node.entity)
            self.nodes[node.id] = node
            self._index_add(node.id, entity)
            self._ensure_node_structures(node.id)
            if self._storage is not None:
                self._storage.upsert_node(node)
            self.resolve_evidence_contradictions(node.id)
            return self.nodes[node.id]

        # 2) Fuzzy match via EntityMatcher — hash-indexed candidates only
        if self.entity_matcher and self.merge_engine:
            new_dict = self._entity_to_match_dict(entity)
            candidates = self._index_candidates(entity)
            for existing_id in candidates:
                existing_node = self.nodes.get(existing_id)
                if existing_node is None or type(existing_node.entity) is not type(entity):
                    continue
                existing_dict = self._entity_to_match_dict(existing_node.entity)
                score = self.entity_matcher.match(new_dict, existing_dict)
                if score > 0:
                    merged_dict = self.merge_engine.merge(
                        new_dict,
                        existing_dict,
                        strategy="most_confident",
                    )
                    merged_entity = self._entity_from_merged_dict(
                        merged_dict,
                        type(entity),
                        existing_id,
                        existing_node.entity,
                    )

                    # Concatenate tuple fields from both entities
                    replace_kwargs: dict[str, Any] = {}
                    for fname in ("evidence", "provenance", "aliases", "open_ports"):
                        existing_val = getattr(existing_node.entity, fname, ())
                        new_val = getattr(entity, fname, ())
                        if existing_val and new_val:
                            replace_kwargs[fname] = existing_val + new_val
                    # Temporal: earliest first_seen, latest last_seen
                    old_fs = getattr(existing_node.entity, "first_seen", None)
                    new_fs = getattr(entity, "first_seen", None)
                    if old_fs and new_fs:
                        replace_kwargs["first_seen"] = min(old_fs, new_fs)
                        replace_kwargs["last_seen"] = max(
                            getattr(existing_node.entity, "last_seen", old_fs),
                            getattr(entity, "last_seen", new_fs),
                        )
                    if replace_kwargs:
                        merged_entity = replace(merged_entity, **replace_kwargs)

                    merged_node = Node(entity=merged_entity)
                    if not overwrite:
                        self.previous_versions.setdefault(existing_id, []).append(existing_node)
                        if self._storage is not None:
                            self._storage.save_previous_version(existing_id, existing_node)
                    # Update index: remove old entity, add merged
                    self._index_remove(existing_id, existing_node.entity)
                    self.nodes[existing_id] = merged_node
                    self._index_add(existing_id, merged_entity)
                    logger.info(
                        "Entity %s fuzzy-matched existing %s (score=%.4f), merged",
                        entity.id,
                        existing_id,
                        score,
                    )
                    if self._storage is not None:
                        self._storage.upsert_node(merged_node)
                    self.resolve_evidence_contradictions(existing_id)
                    return self.nodes[existing_id]

        # 3) No match — create new node
        self.nodes[node.id] = node
        self._ensure_node_structures(node.id)
        self._index_add(node.id, entity)
        if self._storage is not None:
            self._storage.upsert_node(node)
        self.resolve_evidence_contradictions(node.id)
        return self.nodes[node.id]

    @property
    def nodes_summary(self) -> list[dict[str, Any]]:
        from intelgraph.core.scoring.threat_score import _compute_node_scores

        scores = _compute_node_scores(self)
        return [
            {
                "node_id": n.id,
                "entity_type": type(n.entity).__name__,
                "entity_identifier": getattr(n.entity, "ip", None)
                or getattr(n.entity, "domain_name", None)
                or getattr(n.entity, "cve_id", None)
                or n.id,
                "confidence": getattr(n.entity, "confidence_score", 0) or 0,
                "evidence_count": len(getattr(n.entity, "evidence", ())),
                "first_seen": (
                    getattr(n.entity, "first_seen", None).isoformat()
                    if getattr(n.entity, "first_seen", None)
                    else None
                ),
                "last_seen": (
                    getattr(n.entity, "last_seen", None).isoformat()
                    if getattr(n.entity, "last_seen", None)
                    else None
                ),
                "threat_score": scores.get(n.id, 0.0),
            }
            for n in self.nodes.values()
        ]

    @property
    def edges_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "source": e.source_id,
                "target": e.target_id,
                "relationship_type": e.relationship.type.name.lower(),
                "confidence": e.relationship.confidence_score,
                "first_seen": (
                    e.relationship.first_seen.isoformat() if e.relationship.first_seen else None
                ),
                "last_seen": (
                    e.relationship.last_seen.isoformat() if e.relationship.last_seen else None
                ),
                "occurrence_count": e.relationship.occurrence_count,
            }
            for e in self.edges.values()
        ]

    @property
    def merge_audit(self) -> list[dict[str, Any]]:
        if self.merge_engine and hasattr(self.merge_engine, "audit"):
            return self.merge_engine.audit.get_history()
        return []

    # ── Temporal queries ──

    def entities_active_in_range(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        """Return entities active (first_seen <= end and last_seen >= start) in [start, end]."""
        results: list[dict[str, Any]] = []
        for nid, node in self.nodes.items():
            fs = getattr(node.entity, "first_seen", None)
            ls = getattr(node.entity, "last_seen", None)
            if fs and ls and fs <= end and ls >= start:
                results.append(
                    {
                        "node_id": nid,
                        "entity_type": type(node.entity).__name__,
                        "entity_identifier": getattr(node.entity, "ip", None)
                        or getattr(node.entity, "domain_name", None)
                        or getattr(node.entity, "cve_id", None)
                        or nid,
                        "first_seen": fs.isoformat(),
                        "last_seen": ls.isoformat(),
                        "confidence": getattr(node.entity, "confidence_score", 0),
                    }
                )
        return results

    def relationship_timeline(self, entity_id: str) -> list[dict[str, Any]]:
        """Chronological timeline of an entity's relationships."""
        timeline: list[dict[str, Any]] = []
        for eid in self.node_edges.get(entity_id, set()):
            edge = self.edges.get(eid)
            if not edge:
                continue
            other = edge.target_id if edge.source_id == entity_id else edge.source_id
            timeline.append(
                {
                    "first_seen": (
                        edge.relationship.first_seen.isoformat()
                        if edge.relationship.first_seen
                        else ""
                    ),
                    "last_seen": (
                        edge.relationship.last_seen.isoformat()
                        if edge.relationship.last_seen
                        else ""
                    ),
                    "other_entity": other,
                    "relationship_type": edge.relationship.type.name.lower(),
                    "occurrence_count": edge.relationship.occurrence_count,
                    "confidence": edge.relationship.confidence_score,
                }
            )
        timeline.sort(key=lambda r: r["first_seen"] or "")
        return timeline

    def trending_entities(self, days: int = 7) -> list[dict[str, Any]]:
        """Entities seen most recently (last N days), sorted by last_seen desc."""
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=days)
        results: list[dict[str, Any]] = []
        for nid, node in self.nodes.items():
            ls = getattr(node.entity, "last_seen", None)
            if ls and ls >= cutoff:
                results.append(
                    {
                        "node_id": nid,
                        "entity_type": type(node.entity).__name__,
                        "entity_identifier": getattr(node.entity, "ip", None)
                        or getattr(node.entity, "domain_name", None)
                        or getattr(node.entity, "cve_id", None)
                        or nid,
                        "last_seen": ls.isoformat(),
                        "evidence_count": len(getattr(node.entity, "evidence", ())),
                    }
                )
        results.sort(key=lambda r: r["last_seen"], reverse=True)
        return results

    def _ensure_node_structures(self, node_id: str) -> None:
        self.adjacency.setdefault(node_id, set())
        self.forward_adjacency.setdefault(node_id, set())
        self.reverse_adjacency.setdefault(node_id, set())
        self.node_edges.setdefault(node_id, set())

    # ── Hash-based pre-filter index ──

    _INDEX_FIELDS: tuple[str, ...] = ("ip", "domain_name", "cve_id", "email", "name")

    @staticmethod
    def _normalize_index(value: Any) -> str:
        """Same normalization as EntityMatcher._normalize."""
        return str(value).lower().strip().replace("-", "").replace("_", "").replace(".", "")

    def _index_key(self, entity: BaseEntity, field: str) -> str | None:
        """Return normalized value for *field* on *entity*, or None if empty."""
        raw = getattr(entity, field, None)
        if not raw:
            return None
        return self._normalize_index(raw)

    @staticmethod
    def _name_signature(normalized: str) -> tuple[frozenset[str], int]:
        """Character-bag + length signature for name-similarity pre-filtering."""
        return (frozenset(normalized), len(normalized))

    def _entity_name(self, entity: BaseEntity) -> str:
        """Return the normalized 'name' field used by EntityMatcher._name_similarity."""
        for attr in ("ip", "domain_name", "cve_id", "name", "email"):
            val = getattr(entity, attr, None)
            if val:
                return self._normalize_index(val)
        return self._normalize_index(entity.id)

    def _index_add(self, node_id: str, entity: BaseEntity) -> None:
        """Add *entity* to both primary and secondary indexes."""
        etype = type(entity).__name__
        for field in self._INDEX_FIELDS:
            val = self._index_key(entity, field)
            if val:
                key = f"{etype}:{field}:{val}"
                self._entity_index.setdefault(key, set()).add(node_id)
        # Secondary: name-signature for character-overlap matching
        name = self._entity_name(entity)
        if len(name) >= 3:
            sig = self._name_signature(name)
            sig_key = (etype, sig[0], sig[1])
            self._entity_sig_index.setdefault(sig_key, set()).add(node_id)

    def _index_remove(self, node_id: str, entity: BaseEntity) -> None:
        """Remove *entity* from both indexes."""
        etype = type(entity).__name__
        for field in self._INDEX_FIELDS:
            val = self._index_key(entity, field)
            if val:
                key = f"{etype}:{field}:{val}"
                bucket = self._entity_index.get(key)
                if bucket:
                    bucket.discard(node_id)
                    if not bucket:
                        del self._entity_index[key]
        name = self._entity_name(entity)
        if len(name) >= 3:
            sig = self._name_signature(name)
            sig_key = (etype, sig[0], sig[1])
            bucket = self._entity_sig_index.get(sig_key)
            if bucket:
                bucket.discard(node_id)
                if not bucket:
                    del self._entity_sig_index[sig_key]

    def _index_candidates(self, entity: BaseEntity) -> list[str]:
        """Return node IDs that are candidates for fuzzy matching."""
        etype = type(entity).__name__
        seen: set[str] = set()
        # Primary: exact-field matches
        for field in self._INDEX_FIELDS:
            val = self._index_key(entity, field)
            if val:
                key = f"{etype}:{field}:{val}"
                for nid in self._entity_index.get(key, ()):
                    seen.add(nid)
        # Secondary: same char-bag + length (name-similarity candidates)
        name = self._entity_name(entity)
        if len(name) >= 3:
            sig = self._name_signature(name)
            sig_key = (etype, sig[0], sig[1])
            for nid in self._entity_sig_index.get(sig_key, ()):
                seen.add(nid)
        return [nid for nid in seen if nid in self.nodes]

    def _entity_to_match_dict(self, entity: BaseEntity) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for f in fields(type(entity)):
            if not f.init:
                continue
            val = getattr(entity, f.name)
            if isinstance(val, datetime):
                d[f.name] = val.isoformat()
            elif isinstance(val, tuple):
                d[f.name] = list(val)
            elif not isinstance(val, (str, int, float, bool, type(None))):
                d[f.name] = str(val)
            else:
                d[f.name] = val
        # Name field for EntityMatcher's _name_similarity
        for attr in ("ip", "domain_name", "cve_id", "name", "email"):
            candidate = getattr(entity, attr, None)
            if candidate:
                d["name"] = str(candidate)
                break
        if "name" not in d:
            d["name"] = entity.id
        return d

    def _entity_from_merged_dict(
        self,
        merged: dict[str, Any],
        entity_class: type,
        entity_id: str,
        original: BaseEntity,
    ) -> BaseEntity:
        init_fields = {f.name for f in fields(entity_class) if f.init}
        kwargs: dict[str, Any] = {"id": entity_id}
        for fname in init_fields:
            if fname == "id":
                continue
            orig_val = getattr(original, fname)
            merged_val = merged.get(fname)
            if merged_val is None or merged_val == "" or merged_val == []:
                kwargs[fname] = orig_val
            elif isinstance(orig_val, datetime) and isinstance(merged_val, str):
                try:
                    kwargs[fname] = datetime.fromisoformat(merged_val)
                except (ValueError, TypeError):
                    kwargs[fname] = orig_val
            elif isinstance(orig_val, tuple) and isinstance(merged_val, list):
                kwargs[fname] = tuple(merged_val)
            elif not isinstance(merged_val, type(orig_val)) and orig_val is not None:
                try:
                    kwargs[fname] = type(orig_val)(merged_val)
                except (ValueError, TypeError):
                    kwargs[fname] = orig_val
            else:
                kwargs[fname] = merged_val
        return entity_class(**kwargs)

    def _infer_support_type(self, content: str) -> SupportType:
        words = content.lower().split()
        has_supports = bool(_INFER_SUPPORTS & set(words))
        has_contradicts = bool(_INFER_CONTRADICTS & set(words))
        if has_supports and not has_contradicts:
            return SupportType.SUPPORTS
        if has_contradicts and not has_supports:
            return SupportType.CONTRADICTS
        return SupportType.NEUTRAL

    def _evidence_to_items(self, evidence: tuple[Evidence, ...]) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for ev in evidence:
            items.append(
                EvidenceItem(
                    evidence_id=ev.id,
                    source_id=ev.source,
                    document_id=ev.id,
                    claim=ev.content,
                    support_type=self._infer_support_type(ev.content),
                    confidence=float(ev.reliability_score),
                )
            )
        return items

    def resolve_evidence_contradictions(self, node_id: str) -> dict[str, Any] | None:
        node = self.nodes.get(node_id)
        if node is None:
            return None
        entity = node.entity
        if not entity.evidence:
            return None

        # ── ChainManager path: single detect+compute, persisted ──
        if self.chain_manager is not None:
            batch_items: list[tuple[str, str, str, str, float, dict[str, Any]]] = []
            for ev in entity.evidence:
                st = self._infer_support_type(ev.content)
                batch_items.append(
                    (
                        ev.source,
                        ev.id,
                        ev.content,
                        st.name.lower(),
                        float(ev.trust_score),
                        {},
                    )
                )

            chain, records = self.chain_manager.add_evidence_batch(node_id, batch_items)

            new_confidence = int(round(chain.confidence))
            if new_confidence != entity.confidence_score:
                new_entity = replace(entity, confidence_score=new_confidence)
                self.nodes[node_id] = Node(entity=new_entity)
                if self._storage is not None:
                    self._storage.upsert_node(self.nodes[node_id])

            self.contradiction_records[node_id] = [
                {
                    "type": r.contradiction_type,
                    "score": r.score,
                    "evidence_a": r.evidence_id_a,
                    "evidence_b": r.evidence_id_b,
                    "chain_confidence": chain.confidence,
                    "chain_status": chain.status.name_lower,
                }
                for r in records
            ]

            if records:
                logger.warning(
                    "Evidence contradictions for %s: %d record(s) "
                    "(chain_manager), chain_confidence=%.2f, status=%s",
                    node_id,
                    len(records),
                    chain.confidence,
                    chain.status.name_lower,
                )

            return {
                "contradiction_count": len(records),
                "contradictions": self.contradiction_records[node_id],
                "chain_confidence": chain.confidence,
                "chain_status": chain.status.name_lower,
            }

        # ── In-memory path (backward compat, no chain_manager) ──
        if self.evidence_contradiction_detector is None or self.confidence_computer is None:
            return None

        items = self._evidence_to_items(entity.evidence)
        chain = EvidenceChain(
            entity_id=entity.id,
            evidence=items,
        )
        chain.recompute_id()

        records = self.evidence_contradiction_detector.detect(chain)
        self.confidence_computer.compute(chain)

        new_confidence = int(round(chain.confidence))
        if new_confidence != entity.confidence_score:
            new_entity = replace(entity, confidence_score=new_confidence)
            self.nodes[node_id] = Node(entity=new_entity)
            if self._storage is not None:
                self._storage.upsert_node(self.nodes[node_id])

        self.contradiction_records[node_id] = [
            {
                "type": r.contradiction_type,
                "score": r.score,
                "evidence_a": r.evidence_id_a,
                "evidence_b": r.evidence_id_b,
                "chain_confidence": chain.confidence,
                "chain_status": chain.status.name_lower,
            }
            for r in records
        ]

        if records:
            logger.warning(
                "Evidence contradictions for %s: %d record(s) "
                "(in-memory), chain_confidence=%.2f, status=%s",
                node_id,
                len(records),
                chain.confidence,
                chain.status.name_lower,
            )

        return {
            "contradiction_count": len(records),
            "contradictions": self.contradiction_records[node_id],
            "chain_confidence": chain.confidence,
            "chain_status": chain.status.name_lower,
        }

    def add_relationship(self, relationship: Relationship) -> Edge:
        # Check for existing edge with same source/target/type (temporal update)
        for eid in self.node_edges.get(relationship.source_id, set()):
            existing = self.edges.get(eid)
            if (
                existing
                and existing.source_id == relationship.source_id
                and existing.target_id == relationship.target_id
                and existing.relationship.type == relationship.type
            ):
                # Update temporal fields on existing edge
                updated_rel = replace(
                    existing.relationship,
                    last_seen=relationship.last_seen,
                    first_seen=min(existing.relationship.first_seen, relationship.first_seen),
                    occurrence_count=existing.relationship.occurrence_count + 1,
                    confidence_score=max(
                        existing.relationship.confidence_score, relationship.confidence_score
                    ),
                )
                updated_edge = Edge(relationship=updated_rel)
                self.edges[eid] = updated_edge
                if self._storage is not None:
                    self._storage.upsert_edge(updated_edge)
                return updated_edge

        edge = Edge(relationship=relationship)
        self.edges[edge.id] = edge
        self.adjacency.setdefault(edge.source_id, set()).add(edge.target_id)
        self.adjacency.setdefault(edge.target_id, set()).add(edge.source_id)
        self.forward_adjacency.setdefault(edge.source_id, set()).add(edge.target_id)
        self.reverse_adjacency.setdefault(edge.target_id, set()).add(edge.source_id)
        self.node_edges.setdefault(edge.source_id, set()).add(edge.id)
        self.node_edges.setdefault(edge.target_id, set()).add(edge.id)
        self.edge_node_map[edge.id] = (edge.source_id, edge.target_id)
        if self._storage is not None:
            self._storage.upsert_edge(edge)
        return edge

    def get_node(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)

    def get_edge(self, edge_id: str) -> Edge | None:
        return self.edges.get(edge_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self.nodes

    def has_edge(self, edge_id: str) -> bool:
        return edge_id in self.edges

    def remove_node(self, node_id: str) -> bool:
        node = self.nodes.pop(node_id, None)
        if node is None:
            return False
        self._index_remove(node_id, node.entity)
        for neighbor_id in list(self.adjacency.get(node_id, set())):
            self.adjacency.get(neighbor_id, set()).discard(node_id)
            self.reverse_adjacency.get(neighbor_id, set()).discard(node_id)
            self.forward_adjacency.get(neighbor_id, set()).discard(node_id)
        self.adjacency.pop(node_id, None)
        self.forward_adjacency.pop(node_id, None)
        self.reverse_adjacency.pop(node_id, None)
        edge_ids = list(self.node_edges.get(node_id, set()))
        for eid in edge_ids:
            self.edges.pop(eid, None)
            src_tgt = self.edge_node_map.pop(eid, None)
            if src_tgt:
                src, tgt = src_tgt
                self.adjacency.get(src, set()).discard(tgt)
                self.adjacency.get(tgt, set()).discard(src)
                self.forward_adjacency.get(src, set()).discard(tgt)
                self.reverse_adjacency.get(tgt, set()).discard(src)
                self.node_edges.get(src, set()).discard(eid)
                self.node_edges.get(tgt, set()).discard(eid)
        self.node_edges.pop(node_id, None)
        self.previous_versions.pop(node_id, None)
        if self._storage is not None:
            self._storage.delete_node(node_id)
        return True

    def remove_edge(self, edge_id: str) -> bool:
        edge = self.edges.pop(edge_id, None)
        if edge is None:
            return False
        src_tgt = self.edge_node_map.pop(edge_id, None)
        if src_tgt:
            src, tgt = src_tgt
            self.adjacency.get(src, set()).discard(tgt)
            self.adjacency.get(tgt, set()).discard(src)
            self.forward_adjacency.get(src, set()).discard(tgt)
            self.reverse_adjacency.get(tgt, set()).discard(src)
            self.node_edges.get(src, set()).discard(edge_id)
            self.node_edges.get(tgt, set()).discard(edge_id)
        if self._storage is not None:
            self._storage.delete_edge(edge_id)
        return True

    def neighbors(self, node_id: str) -> Iterator[Node]:
        for neighbor_id in self.adjacency.get(node_id, set()):
            neighbor = self.nodes.get(neighbor_id)
            if neighbor is not None:
                yield neighbor

    def outgoing(self, node_id: str) -> Iterator[Node]:
        for neighbor_id in self.forward_adjacency.get(node_id, set()):
            neighbor = self.nodes.get(neighbor_id)
            if neighbor is not None:
                yield neighbor

    def incoming(self, node_id: str) -> Iterator[Node]:
        for neighbor_id in self.reverse_adjacency.get(node_id, set()):
            neighbor = self.nodes.get(neighbor_id)
            if neighbor is not None:
                yield neighbor

    def edges_for_node(self, node_id: str, direction: str = "both") -> Iterator[Edge]:
        for eid in self.node_edges.get(node_id, set()):
            edge = self.edges.get(eid)
            if edge is None:
                continue
            if direction == "both":
                yield edge
            elif direction == "outgoing" and edge.source_id == node_id:
                yield edge
            elif direction == "incoming" and edge.target_id == node_id:
                yield edge

    def nodes_for_edge(self, edge_id: str) -> tuple[Node, Node] | None:
        src_tgt = self.edge_node_map.get(edge_id)
        if src_tgt is None:
            return None
        src_id, tgt_id = src_tgt
        src = self.nodes.get(src_id)
        tgt = self.nodes.get(tgt_id)
        if src is None or tgt is None:
            return None
        return src, tgt

    def bfs(self, start_id: str) -> list[Node]:
        if start_id not in self.nodes:
            return []
        visited: set[str] = set()
        queue: deque[str] = deque()
        result: list[Node] = []
        visited.add(start_id)
        queue.append(start_id)
        while queue:
            current = queue.popleft()
            node = self.nodes.get(current)
            if node is not None:
                result.append(node)
            for neighbor_id in self.adjacency.get(current, set()):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append(neighbor_id)
        return result

    def dfs(self, start_id: str) -> list[Node]:
        if start_id not in self.nodes:
            return []
        visited: set[str] = set()
        stack: list[str] = [start_id]
        result: list[Node] = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            node = self.nodes.get(current)
            if node is not None:
                result.append(node)
            for neighbor_id in sorted(self.adjacency.get(current, set()), reverse=True):
                if neighbor_id not in visited:
                    stack.append(neighbor_id)
        return result

    def shortest_path(self, start_id: str, end_id: str) -> list[Node]:
        if start_id not in self.nodes or end_id not in self.nodes:
            return []
        if start_id == end_id:
            node = self.nodes.get(start_id)
            return [node] if node is not None else []
        visited: set[str] = {start_id}
        queue: deque[list[str]] = deque([[start_id]])
        while queue:
            path = queue.popleft()
            current = path[-1]
            for neighbor_id in self.adjacency.get(current, set()):
                if neighbor_id == end_id:
                    full_path = path + [neighbor_id]
                    result: list[Node] = []
                    for nid in full_path:
                        n = self.nodes.get(nid)
                        if n is not None:
                            result.append(n)
                    return result
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append(path + [neighbor_id])
        return []

    def bfs_depth(self, start_id: str, max_depth: int) -> list[Node]:
        if start_id not in self.nodes or max_depth < 0:
            return []
        visited: set[str] = {start_id}
        queue: deque[tuple[str, int]] = deque()
        queue.append((start_id, 0))
        result: list[Node] = []
        while queue:
            current, depth = queue.popleft()
            if depth > max_depth:
                continue
            node = self.nodes.get(current)
            if node is not None:
                result.append(node)
            if depth < max_depth:
                for neighbor_id in self.adjacency.get(current, set()):
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        queue.append((neighbor_id, depth + 1))
        return result

    def extract_subgraph(self, start_id: str, max_depth: int = 1) -> "IntelligenceGraph":
        sub = IntelligenceGraph()
        seed_nodes = self.bfs_depth(start_id, max_depth)
        seed_ids = {n.id for n in seed_nodes}
        for n in seed_nodes:
            sub.nodes[n.id] = n
            sub.adjacency.setdefault(n.id, set())
            sub.forward_adjacency.setdefault(n.id, set())
            sub.reverse_adjacency.setdefault(n.id, set())
            sub.node_edges.setdefault(n.id, set())
        for eid, edge in self.edges.items():
            src_tgt = self.edge_node_map.get(eid)
            if src_tgt is None:
                continue
            src_id, tgt_id = src_tgt
            if src_id in seed_ids and tgt_id in seed_ids:
                sub.edges[eid] = edge
                sub.adjacency.setdefault(src_id, set()).add(tgt_id)
                sub.adjacency.setdefault(tgt_id, set()).add(src_id)
                sub.forward_adjacency.setdefault(src_id, set()).add(tgt_id)
                sub.reverse_adjacency.setdefault(tgt_id, set()).add(src_id)
                sub.node_edges.setdefault(src_id, set()).add(eid)
                sub.node_edges.setdefault(tgt_id, set()).add(eid)
                sub.edge_node_map[eid] = (src_id, tgt_id)
        return sub

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)
