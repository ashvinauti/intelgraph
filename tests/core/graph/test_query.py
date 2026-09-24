from typing import Any

from intelgraph.core.entity import Company, Domain, Person
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.query import GraphQueryEngine
from intelgraph.core.relationship import Relationship
from intelgraph.core.relationship.types import RelationshipType


def _make_graph() -> tuple[IntelligenceGraph, dict[str, Any], dict[str, Any]]:
    g = IntelligenceGraph()
    alice = Person(name="Alice")
    bob = Person(name="Bob")
    carol = Person(name="Carol")
    acme = Company(name="Acme Corp")
    example = Domain(domain_name="example.com")
    g.add_entity(alice)
    g.add_entity(bob)
    g.add_entity(carol)
    g.add_entity(acme)
    g.add_entity(example)

    r1 = Relationship(
        source_id=alice.id,
        target_id=bob.id,
        type=RelationshipType.RELATED_TO,
        confidence_score=80,
        trust_weight=70,
    )
    r2 = Relationship(
        source_id=bob.id,
        target_id=carol.id,
        type=RelationshipType.RELATED_TO,
        confidence_score=80,
        trust_weight=70,
    )
    r3 = Relationship(
        source_id=alice.id,
        target_id=acme.id,
        type=RelationshipType.WORKS_FOR,
        confidence_score=90,
        trust_weight=80,
    )
    r4 = Relationship(
        source_id=acme.id,
        target_id=example.id,
        type=RelationshipType.OWNS,
        confidence_score=70,
        trust_weight=60,
    )
    g.add_relationship(r1)
    g.add_relationship(r2)
    g.add_relationship(r3)
    g.add_relationship(r4)

    vrecs: dict[str, dict[str, Any]] = {
        alice.id: {"verification_state": "confirmed", "confidence": 95.0, "entity_type": "person"},
        bob.id: {"verification_state": "probable", "confidence": 75.0, "entity_type": "person"},
        carol.id: {
            "verification_state": "speculative",
            "confidence": 30.0,
            "entity_type": "person",
        },
        acme.id: {"verification_state": "confirmed", "confidence": 90.0, "entity_type": "company"},
        example.id: {"verification_state": "possible", "confidence": 55.0, "entity_type": "domain"},
    }

    chains: dict[str, dict[str, Any]] = {
        alice.id: {"evidence": [{"confidence": 90.0}, {"confidence": 80.0}]},
        bob.id: {"evidence": [{"confidence": 70.0}]},
        carol.id: {"evidence": [{"confidence": 30.0}]},
        acme.id: {"evidence": [{"confidence": 85.0}, {"confidence": 75.0}]},
        example.id: {"evidence": [{"confidence": 50.0}]},
    }

    def vl(eid: str) -> dict[str, Any] | None:
        return vrecs.get(eid)

    def cl(eid: str) -> dict[str, Any] | None:
        return chains.get(eid)

    return g, vl, cl


class TestFilterNodes:
    def test_filter_by_entity_type(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        people = qe.filter_nodes(entity_type="person")
        assert len(people) == 3
        companies = qe.filter_nodes(entity_type="company")
        assert len(companies) == 1
        domains = qe.filter_nodes(entity_type="domain")
        assert len(domains) == 1

    def test_filter_by_verification_state(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        confirmed = qe.filter_nodes(verification_state="confirmed")
        assert len(confirmed) == 2

    def test_filter_by_confidence_range(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        high = qe.filter_nodes(confidence_min=80.0)
        assert len(high) == 2
        mid = qe.filter_nodes(confidence_min=50.0, confidence_max=80.0)
        assert len(mid) == 2
        low = qe.filter_nodes(confidence_max=40.0)
        assert len(low) == 1

    def test_filter_by_source_trust(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        trusted = qe.filter_nodes(source_trust_min=75.0)
        assert len(trusted) == 2
        all_nodes = qe.filter_nodes(source_trust_min=0.0)
        assert len(all_nodes) == 5

    def test_filter_composite(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        result = qe.filter_nodes(entity_type="person", verification_state="confirmed")
        assert len(result) == 1
        assert result[0].entity.name == "Alice"

    def test_filter_no_verification_lookup(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g)
        result = qe.filter_nodes(entity_type="person")
        assert len(result) == 3

    def test_filter_with_limit_offset(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        all_nodes = qe.filter_nodes()
        assert len(all_nodes) == 5
        limited = qe.filter_nodes(limit=2)
        assert len(limited) == 2
        offset = qe.filter_nodes(limit=2, offset=2)
        assert len(offset) == 2
        assert limited[0].id != offset[0].id


class TestPathQueries:
    def test_find_path(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        carol_id = next(n.id for n in g.nodes.values() if n.entity.name == "Carol")
        path = qe.find_path(alice_id, carol_id)
        assert len(path) == 3
        assert path[0]["name"] == "Alice"
        assert path[1]["name"] == "Bob"
        assert path[2]["name"] == "Carol"

    def test_find_path_unreachable(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        isolated = Person(name="Isolated")
        g.add_entity(isolated)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        path = qe.find_path(alice_id, isolated.id)
        assert path == []

    def test_enumerate_paths(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        c = Person(name="C")
        d = Person(name="D")
        g.add_entity(a)
        g.add_entity(b)
        g.add_entity(c)
        g.add_entity(d)
        g.add_relationship(
            Relationship(
                source_id=a.id,
                target_id=b.id,
                type=RelationshipType.RELATED_TO,
                confidence_score=50,
                trust_weight=50,
            )
        )
        g.add_relationship(
            Relationship(
                source_id=a.id,
                target_id=c.id,
                type=RelationshipType.RELATED_TO,
                confidence_score=50,
                trust_weight=50,
            )
        )
        g.add_relationship(
            Relationship(
                source_id=b.id,
                target_id=d.id,
                type=RelationshipType.RELATED_TO,
                confidence_score=50,
                trust_weight=50,
            )
        )
        g.add_relationship(
            Relationship(
                source_id=c.id,
                target_id=d.id,
                type=RelationshipType.RELATED_TO,
                confidence_score=50,
                trust_weight=50,
            )
        )
        qe = GraphQueryEngine(g)
        paths = qe.enumerate_paths(a.id, d.id, max_depth=3)
        assert len(paths) == 2

    def test_enumerate_paths_same_node(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        paths = qe.enumerate_paths(alice_id, alice_id, max_depth=3)
        assert paths == []

    def test_enumerate_paths_nonexistent(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        assert qe.enumerate_paths("x", "y") == []


class TestTraversalQuery:
    def test_bfs_query(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        result = qe.bfs_query(alice_id)
        assert len(result) == 5

    def test_bfs_query_filtered(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        result = qe.bfs_query(alice_id, entity_type="person")
        assert len(result) == 3
        result2 = qe.bfs_query(alice_id, verification_state="confirmed")
        assert len(result2) == 2

    def test_bfs_query_nonexistent(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        assert qe.bfs_query("nonexistent") == []

    def test_dfs_query(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        result = qe.dfs_query(alice_id)
        assert len(result) == 5

    def test_dfs_query_filtered(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        result = qe.dfs_query(alice_id, entity_type="company")
        assert len(result) == 1

    def test_dfs_query_nonexistent(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        assert qe.dfs_query("nonexistent") == []

    def test_bfs_depth_query(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        depth0 = qe.bfs_depth_query(alice_id, 0)
        assert len(depth0) == 1
        depth1 = qe.bfs_depth_query(alice_id, 1)
        assert len(depth1) == 3
        depth2 = qe.bfs_depth_query(alice_id, 2)
        assert len(depth2) == 5

    def test_bfs_depth_query_filtered(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        result = qe.bfs_depth_query(alice_id, 2, entity_type="person")
        assert len(result) == 3

    def test_bfs_depth_query_negative(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        assert qe.bfs_depth_query(alice_id, -1) == []

    def test_traversal_with_limit_offset(self):
        g, vl, cl = _make_graph()
        qe = GraphQueryEngine(g, vl, cl)
        alice_id = next(n.id for n in g.nodes.values() if n.entity.name == "Alice")
        full = qe.bfs_query(alice_id)
        assert len(full) == 5
        limited = qe.bfs_query(alice_id, limit=2)
        assert len(limited) == 2
        offset = qe.bfs_query(alice_id, limit=2, offset=2)
        assert len(offset) == 2
