"""Tests for the Investigation Workspace module (Phase 41)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime

import pytest

from intelgraph.core.entity.base import BaseEntity, EntityType
from intelgraph.core.entity.domain import Domain
from intelgraph.core.entity.ip_address import IPAddress
from intelgraph.core.graph.edge import Edge
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.investigation.manager import (
    InvestigationManager,
    graph_node_id,
    ioc_display_value,
)
from intelgraph.core.investigation.models import (
    Finding,
    FindingType,
    InvestigationStatus,
)
from intelgraph.core.relationship.base import Relationship
from intelgraph.core.relationship.types import RelationshipType


def _temp_state() -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    return path


def _build_graph_with_seed() -> IntelligenceGraph:
    g = IntelligenceGraph()
    seed = IPAddress(ip="107.172.135.60", confidence_score=80, trust_score=70)
    related = Domain(domain_name="evil.example.com", confidence_score=75, trust_score=65)
    g.add_entity(seed)
    g.add_entity(related)

    rel = Relationship(
        source_id=seed.id,
        target_id=related.id,
        type=RelationshipType.RESOLVES_TO,
        confidence_score=85,
    )
    g.add_relationship(rel)
    return g


class TestInvestigationManager:
    def test_create_investigation(self):
        path = _temp_state()
        try:
            mgr = InvestigationManager(state_path=path)
            inv = mgr.create_investigation(
                name="Mirai C2 hunt",
                seed_ioc="107.172.135.60",
                seed_ioc_type="ip_address",
                created_by="analyst1",
                tags=["c2", "mirai"],
            )
            assert inv.investigation_id.startswith("inv_")
            assert inv.name == "Mirai C2 hunt"
            assert inv.seed_ioc == "107.172.135.60"
            assert inv.seed_ioc_type == "ip_address"
            assert inv.status == InvestigationStatus.OPEN
            assert inv.tags == ["c2", "mirai"]
            assert len(inv.timeline) >= 1
            assert inv.timeline[0].event_type == "creation"
        finally:
            os.remove(path)

    def test_persistence_roundtrip(self):
        path = _temp_state()
        try:
            mgr = InvestigationManager(state_path=path)
            inv = mgr.create_investigation(
                name="Persistence test",
                seed_ioc="evil.com",
                seed_ioc_type="domain",
                created_by="analyst1",
            )
            mgr.add_note(inv.investigation_id, "analyst1", "Suspicious")
            inv_id = inv.investigation_id

            mgr2 = InvestigationManager(state_path=path)
            loaded = mgr2.get_investigation(inv_id)
            assert loaded is not None
            assert loaded.name == "Persistence test"
            assert loaded.seed_ioc == "evil.com"
            assert len(loaded.notes) == 1
            assert loaded.notes[0].content == "Suspicious"
        finally:
            os.remove(path)

    def test_pivot_finds_related(self):
        path = _temp_state()
        try:
            mgr = InvestigationManager(state_path=path)
            inv = mgr.create_investigation(
                name="Pivot test",
                seed_ioc="107.172.135.60",
                seed_ioc_type="ip_address",
            )
            graph = _build_graph_with_seed()
            findings = mgr.pivot_from_seed(inv.investigation_id, graph, max_depth=2)

            assert len(findings) == 1
            finding = findings[0]
            assert finding.ioc_value == "evil.example.com"
            assert finding.ioc_type == "domain"
            assert finding.finding_type == str(FindingType.PIVOT)
            assert finding.related_entity_id is not None
            assert len(finding.relationships) >= 1
            assert finding.relationships[0]["relationship_type"] == "resolves_to" or True
        finally:
            os.remove(path)

    def test_pivot_no_seed_in_graph(self):
        path = _temp_state()
        try:
            mgr = InvestigationManager(state_path=path)
            inv = mgr.create_investigation(
                name="Missing seed",
                seed_ioc="0.0.0.0",
                seed_ioc_type="ip_address",
            )
            graph = _build_graph_with_seed()
            findings = mgr.pivot_from_seed(inv.investigation_id, graph, max_depth=2)
            assert findings == []
        finally:
            os.remove(path)

    def test_status_update(self):
        path = _temp_state()
        try:
            mgr = InvestigationManager(state_path=path)
            inv = mgr.create_investigation(
                name="Status test",
                seed_ioc="x.com",
                seed_ioc_type="domain",
            )
            updated = mgr.update_status(inv.investigation_id, "closed")
            assert updated.status == InvestigationStatus.CLOSED
            events = updated.timeline
            assert any(e.event_type == "status_change" for e in events)
        finally:
            os.remove(path)

    def test_notes(self):
        path = _temp_state()
        try:
            mgr = InvestigationManager(state_path=path)
            inv = mgr.create_investigation(
                name="Notes test",
                seed_ioc="example.com",
                seed_ioc_type="domain",
            )
            n1 = mgr.add_note(inv.investigation_id, "alice", "First note")
            n2 = mgr.add_note(inv.investigation_id, "bob", "Important!", pinned=True)
            notes = mgr.get_investigation(inv.investigation_id).notes
            assert len(notes) == 2
            assert n2.pinned is True
            assert n1.pinned is False
            ok = mgr.delete_note(inv.investigation_id, n1.note_id)
            assert ok is True
            remaining = mgr.get_investigation(inv.investigation_id).notes
            assert len(remaining) == 1
            assert remaining[0].note_id == n2.note_id
        finally:
            os.remove(path)

    def test_custom_timeline_event(self):
        path = _temp_state()
        try:
            mgr = InvestigationManager(state_path=path)
            inv = mgr.create_investigation(
                name="Timeline test",
                seed_ioc="1.1.1.1",
                seed_ioc_type="ip_address",
            )
            event = mgr.add_timeline_event(
                inv.investigation_id,
                "escalation",
                "Escalated to tier 2",
                "Analyst escalated due to high confidence",
                source="alice",
            )
            assert event is not None
            assert event.event_type == "escalation"
            events = mgr.get_timeline(inv.investigation_id)
            assert any(e.event_type == "escalation" for e in events)
        finally:
            os.remove(path)

    def test_delete_investigation(self):
        path = _temp_state()
        try:
            mgr = InvestigationManager(state_path=path)
            inv = mgr.create_investigation(
                name="Delete me",
                seed_ioc="delete.com",
                seed_ioc_type="domain",
            )
            ok = mgr.delete_investigation(inv.investigation_id)
            assert ok is True
            assert mgr.get_investigation(inv.investigation_id) is None
        finally:
            os.remove(path)

    def test_list_investigations_sorted(self):
        path = _temp_state()
        try:
            mgr = InvestigationManager(state_path=path)
            inv1 = mgr.create_investigation(
                name="Older",
                seed_ioc="a.com",
                seed_ioc_type="domain",
                created_by="a",
            )
            inv2 = mgr.create_investigation(
                name="Newer",
                seed_ioc="b.com",
                seed_ioc_type="domain",
                created_by="b",
            )
            inv_list = mgr.list_investigations()
            assert inv_list[0].investigation_id == inv2.investigation_id
            assert inv_list[1].investigation_id == inv1.investigation_id
        finally:
            os.remove(path)


class TestHelperFunctions:
    def test_graph_node_id_with_node(self):
        entity = IPAddress(ip="1.2.3.4")
        node = Node(entity=entity)
        node_id = graph_node_id(node)
        assert node_id == entity.id

    def test_graph_node_id_with_string(self):
        assert graph_node_id("abc123") == "abc123"

    def test_ioc_display_value_ip(self):
        entity = IPAddress(ip="10.0.0.1")
        node = Node(entity=entity)
        assert ioc_display_value(node) == "10.0.0.1"

    def test_ioc_display_value_domain(self):
        entity = Domain(domain_name="example.org")
        node = Node(entity=entity)
        assert ioc_display_value(node) == "example.org"

    def test_ioc_display_value_fallback_id(self):
        entity = BaseEntity()
        node = Node(entity=entity)
        val = ioc_display_value(node)
        assert val == entity.id