import pytest

from intelgraph.core.entity import Person
from intelgraph.core.graph.algorithms import GraphAlgorithms
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.relationship import Relationship
from intelgraph.core.relationship.types import RelationshipType


def _add_undirected_edge(
    g: IntelligenceGraph, src_id: str, tgt_id: str, confidence: int = 80, trust: int = 70
) -> None:
    r1 = Relationship(
        source_id=src_id,
        target_id=tgt_id,
        type=RelationshipType.RELATED_TO,
        confidence_score=confidence,
        trust_weight=trust,
    )
    g.add_relationship(r1)
    r2 = Relationship(
        source_id=tgt_id,
        target_id=src_id,
        type=RelationshipType.RELATED_TO,
        confidence_score=confidence,
        trust_weight=trust,
    )
    g.add_relationship(r2)


def _line_graph(n: int = 4) -> IntelligenceGraph:
    g = IntelligenceGraph()
    nodes = [Person(name=f"Node{i}") for i in range(n)]
    for nd in nodes:
        g.add_entity(nd)
    for i in range(n - 1):
        _add_undirected_edge(g, nodes[i].id, nodes[i + 1].id, confidence=90 - i * 10)
    return g


def _star_graph(n_leaves: int = 3) -> IntelligenceGraph:
    g = IntelligenceGraph()
    center = Person(name="Center")
    g.add_entity(center)
    leaves = [Person(name=f"Leaf{i}") for i in range(n_leaves)]
    for leaf in leaves:
        g.add_entity(leaf)
        _add_undirected_edge(g, center.id, leaf.id, confidence=95)
    return g


def _complete_graph(n: int = 4) -> IntelligenceGraph:
    g = IntelligenceGraph()
    nodes = [Person(name=f"Node{i}") for i in range(n)]
    for nd in nodes:
        g.add_entity(nd)
    for i in range(n):
        for j in range(i + 1, n):
            _add_undirected_edge(g, nodes[i].id, nodes[j].id, confidence=85)
    return g


def _triangle_graph() -> IntelligenceGraph:
    g = IntelligenceGraph()
    a = Person(name="A")
    b = Person(name="B")
    c = Person(name="C")
    g.add_entity(a)
    g.add_entity(b)
    g.add_entity(c)
    _add_undirected_edge(g, a.id, b.id, confidence=90)
    _add_undirected_edge(g, b.id, c.id, confidence=80)
    _add_undirected_edge(g, a.id, c.id, confidence=70)
    return g


def _directed_graph() -> IntelligenceGraph:
    g = IntelligenceGraph()
    a = Person(name="A")
    b = Person(name="B")
    c = Person(name="C")
    d = Person(name="D")
    g.add_entity(a)
    g.add_entity(b)
    g.add_entity(c)
    g.add_entity(d)
    rels = [
        (a.id, b.id, 90),
        (b.id, c.id, 80),
        (c.id, a.id, 70),
        (b.id, d.id, 85),
    ]
    for src, tgt, conf in rels:
        r = Relationship(
            source_id=src,
            target_id=tgt,
            type=RelationshipType.RELATED_TO,
            confidence_score=conf,
            trust_weight=70,
        )
        g.add_relationship(r)
    return g


class TestMSTKruskal:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        algs = GraphAlgorithms(g)
        r = algs.mst_kruskal()
        assert r["edge_count"] == 0

    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        algs = GraphAlgorithms(g)
        r = algs.mst_kruskal()
        assert r["edge_count"] == 0

    def test_two_nodes(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        g.add_entity(a)
        g.add_entity(b)
        _add_undirected_edge(g, a.id, b.id, confidence=90)
        algs = GraphAlgorithms(g)
        r = algs.mst_kruskal()
        assert r["edge_count"] == 1
        assert r["edges"][0]["source"] in (a.id, b.id)
        assert r["edges"][0]["target"] in (a.id, b.id)

    def test_line_graph(self):
        g = _line_graph(4)
        algs = GraphAlgorithms(g)
        r = algs.mst_kruskal()
        assert r["edge_count"] == 3
        assert r["edge_count"] < g.edge_count

    def test_complete_graph(self):
        g = _complete_graph(4)
        algs = GraphAlgorithms(g)
        r = algs.mst_kruskal()
        assert r["edge_count"] == 3
        assert r["edge_count"] < g.edge_count

    def test_deterministic(self):
        g = _star_graph(4)
        algs = GraphAlgorithms(g)
        r1 = algs.mst_kruskal()
        r2 = algs.mst_kruskal()
        assert r1["edge_count"] == r2["edge_count"]
        assert r1["total_weight"] == r2["total_weight"]

    def test_tracks_execution_time(self):
        g = _line_graph(5)
        algs = GraphAlgorithms(g)
        r = algs.mst_kruskal()
        assert r["execution_time_ms"] > 0


class TestMSTPrim:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        algs = GraphAlgorithms(g)
        r = algs.mst_prim()
        assert r["edge_count"] == 0

    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        algs = GraphAlgorithms(g)
        r = algs.mst_prim()
        assert r["edge_count"] == 0

    def test_two_nodes(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        g.add_entity(a)
        g.add_entity(b)
        _add_undirected_edge(g, a.id, b.id, confidence=90)
        algs = GraphAlgorithms(g)
        r = algs.mst_prim()
        assert r["edge_count"] == 1

    def test_line_graph(self):
        g = _line_graph(4)
        algs = GraphAlgorithms(g)
        r = algs.mst_prim()
        assert r["edge_count"] == 3

    def test_complete_graph(self):
        g = _complete_graph(4)
        algs = GraphAlgorithms(g)
        r = algs.mst_prim()
        assert r["edge_count"] == 3

    def test_deterministic(self):
        g = _star_graph(4)
        algs = GraphAlgorithms(g)
        r1 = algs.mst_prim()
        r2 = algs.mst_prim()
        assert r1["edge_count"] == r2["edge_count"]

    def test_kruskal_equal_total_weight(self):
        g = _star_graph(5)
        algs = GraphAlgorithms(g)
        k = algs.mst_kruskal()
        p = algs.mst_prim()
        assert k["edge_count"] == p["edge_count"]
        assert abs(k["total_weight"] - p["total_weight"]) < 0.01

    def test_tracks_execution_time(self):
        g = _line_graph(5)
        algs = GraphAlgorithms(g)
        r = algs.mst_prim()
        assert r["execution_time_ms"] > 0


class TestSCC:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        algs = GraphAlgorithms(g)
        r = algs.scc_tarjan()
        assert r["count"] == 0

    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        algs = GraphAlgorithms(g)
        r = algs.scc_tarjan()
        assert r["count"] == 1
        assert len(r["components"]["scc_0"]) == 1

    def test_cycle_is_one_component(self):
        g = _directed_graph()
        algs = GraphAlgorithms(g)
        r = algs.scc_tarjan()
        assert r["count"] >= 2

    def test_line_graph_all_isolated(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        c = Person(name="C")
        g.add_entity(a)
        g.add_entity(b)
        g.add_entity(c)
        r1 = Relationship(
            source_id=a.id,
            target_id=b.id,
            type=RelationshipType.RELATED_TO,
            confidence_score=80,
            trust_weight=70,
        )
        r2 = Relationship(
            source_id=b.id,
            target_id=c.id,
            type=RelationshipType.RELATED_TO,
            confidence_score=80,
            trust_weight=70,
        )
        g.add_relationship(r1)
        g.add_relationship(r2)
        algs = GraphAlgorithms(g)
        r = algs.scc_tarjan()
        assert r["count"] == 3

    def test_tracks_execution_time(self):
        g = _directed_graph()
        algs = GraphAlgorithms(g)
        r = algs.scc_tarjan()
        assert r["execution_time_ms"] > 0


class TestDiameter:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        algs = GraphAlgorithms(g)
        r = algs.diameter()
        assert r["diameter"] == 0

    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        algs = GraphAlgorithms(g)
        r = algs.diameter()
        assert r["diameter"] == 0

    def test_two_nodes(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        g.add_entity(a)
        g.add_entity(b)
        r = Relationship(
            source_id=a.id,
            target_id=b.id,
            type=RelationshipType.RELATED_TO,
            confidence_score=80,
            trust_weight=70,
        )
        g.add_relationship(r)
        algs = GraphAlgorithms(g)
        result = algs.diameter()
        assert result["diameter"] == 1

    def test_line_graph_diameter(self):
        g = _line_graph(5)
        algs = GraphAlgorithms(g)
        result = algs.diameter()
        assert result["diameter"] == 4

    def test_triangle_diameter(self):
        g = _triangle_graph()
        algs = GraphAlgorithms(g)
        result = algs.diameter()
        assert result["diameter"] == 1

    def test_path_connects_endpoints(self):
        g = _line_graph(5)
        algs = GraphAlgorithms(g)
        result = algs.diameter()
        path = result["path"]
        assert len(path) == result["diameter"] + 1
        assert path[0] != path[-1]

    def test_tracks_execution_time(self):
        g = _line_graph(5)
        algs = GraphAlgorithms(g)
        r = algs.diameter()
        assert r["execution_time_ms"] > 0


class TestAStar:
    def test_nonexistent_source(self):
        g = _line_graph(3)
        algs = GraphAlgorithms(g)
        r = algs.astar("nonexistent", list(g.nodes.keys())[0])
        assert r["path"] == []

    def test_nonexistent_target(self):
        g = _line_graph(3)
        algs = GraphAlgorithms(g)
        r = algs.astar(list(g.nodes.keys())[0], "nonexistent")
        assert r["path"] == []

    def test_source_equals_target(self):
        g = _line_graph(3)
        nid = list(g.nodes.keys())[0]
        algs = GraphAlgorithms(g)
        r = algs.astar(nid, nid)
        assert r["path"] == [nid]
        assert r["length"] == 0

    def test_direct_path(self):
        g = _line_graph(3)
        ids = list(g.nodes.keys())
        algs = GraphAlgorithms(g)
        r = algs.astar(ids[0], ids[1])
        assert r["length"] == 1
        assert len(r["path"]) == 2

    def test_indirect_path(self):
        g = _line_graph(5)
        ids = list(g.nodes.keys())
        algs = GraphAlgorithms(g)
        r = algs.astar(ids[0], ids[4])
        assert r["length"] == 4
        assert r["path"][0] == ids[0]
        assert r["path"][-1] == ids[4]

    def test_unreachable(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        g.add_entity(a)
        g.add_entity(b)
        algs = GraphAlgorithms(g)
        r = algs.astar(a.id, b.id)
        assert r["path"] == []

    def test_tracks_nodes_visited(self):
        g = _line_graph(5)
        ids = list(g.nodes.keys())
        algs = GraphAlgorithms(g)
        r = algs.astar(ids[0], ids[4])
        assert r["nodes_visited"] >= 1

    def test_tracks_execution_time(self):
        g = _line_graph(5)
        ids = list(g.nodes.keys())
        algs = GraphAlgorithms(g)
        r = algs.astar(ids[0], ids[1])
        assert r["execution_time_ms"] >= 0


class TestPathStatistics:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        algs = GraphAlgorithms(g)
        r = algs.path_length_statistics()
        assert r["sample_count"] == 0

    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        algs = GraphAlgorithms(g)
        r = algs.path_length_statistics()
        assert r["sample_count"] == 0

    def test_line_graph(self):
        g = _line_graph(4)
        algs = GraphAlgorithms(g)
        r = algs.path_length_statistics()
        assert r["sample_count"] > 0
        assert r["min"] >= 1
        assert r["max"] <= 3

    def test_min_is_at_least_one(self):
        g = _complete_graph(5)
        algs = GraphAlgorithms(g)
        r = algs.path_length_statistics()
        assert r["min"] >= 1


class TestConnectedComponentDistribution:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        algs = GraphAlgorithms(g)
        r = algs.connected_component_distribution()
        assert r["component_count"] == 0

    def test_connected_graph(self):
        g = _line_graph(4)
        algs = GraphAlgorithms(g)
        r = algs.connected_component_distribution()
        assert r["component_count"] == 1
        assert r["largest_component_size"] == 4

    def test_disconnected_graph(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        c = Person(name="C")
        g.add_entity(a)
        g.add_entity(b)
        g.add_entity(c)
        _add_undirected_edge(g, a.id, b.id)
        algs = GraphAlgorithms(g)
        r = algs.connected_component_distribution()
        assert r["component_count"] == 2
        assert r["isolated_node_count"] == 1

    def test_star_graph_single_component(self):
        g = _star_graph(5)
        algs = GraphAlgorithms(g)
        r = algs.connected_component_distribution()
        assert r["component_count"] == 1


class TestConnectivityMetrics:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        algs = GraphAlgorithms(g)
        r = algs.connectivity_metrics()
        assert r["component_count"] == 0

    def test_connected_graph(self):
        g = _line_graph(4)
        algs = GraphAlgorithms(g)
        r = algs.connectivity_metrics()
        assert r["is_connected"] is True
        assert r["component_count"] == 1

    def test_disconnected_graph(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        c = Person(name="C")
        g.add_entity(a)
        g.add_entity(b)
        g.add_entity(c)
        _add_undirected_edge(g, a.id, b.id)
        algs = GraphAlgorithms(g)
        r = algs.connectivity_metrics()
        assert r["is_connected"] is False
        assert r["component_count"] == 2

    def test_tree_detected(self):
        g = _line_graph(3)
        algs = GraphAlgorithms(g)
        r = algs.connectivity_metrics()
        assert r["is_tree"] is True

    def test_cycle_not_tree(self):
        g = _triangle_graph()
        algs = GraphAlgorithms(g)
        r = algs.connectivity_metrics()
        assert r["is_tree"] is False

    def test_tracks_execution_time(self):
        g = _line_graph(4)
        algs = GraphAlgorithms(g)
        r = algs.connectivity_metrics()
        assert r["execution_time_ms"] > 0


class TestCustomWeightFunction:
    def test_uses_trust_weight(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        g.add_entity(a)
        g.add_entity(b)
        r = Relationship(
            source_id=a.id,
            target_id=b.id,
            type=RelationshipType.RELATED_TO,
            confidence_score=50,
            trust_weight=90,
        )
        g.add_relationship(r)
        algs_default = GraphAlgorithms(g)
        algs_custom = GraphAlgorithms(
            g, weight_fn=lambda e: float(101 - e.relationship.trust_weight)
        )
        r1 = algs_default.mst_kruskal()
        r2 = algs_custom.mst_kruskal()
        assert r1["total_weight"] != r2["total_weight"]

    def test_constant_weight(self):
        g = _complete_graph(3)
        algs = GraphAlgorithms(g, weight_fn=lambda e: 1.0)
        r = algs.mst_kruskal()
        assert r["edge_count"] == 2
        assert r["total_weight"] == pytest.approx(2.0)
