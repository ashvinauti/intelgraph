import pytest

from intelgraph.core.entity import Person
from intelgraph.core.graph.analytics import GraphAnalytics
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.relationship import Relationship
from intelgraph.core.relationship.types import RelationshipType


def _add_undirected_edge(g: IntelligenceGraph, src_id: str, tgt_id: str) -> None:
    r1 = Relationship(
        source_id=src_id,
        target_id=tgt_id,
        type=RelationshipType.RELATED_TO,
        confidence_score=80,
        trust_weight=70,
    )
    g.add_relationship(r1)
    r2 = Relationship(
        source_id=tgt_id,
        target_id=src_id,
        type=RelationshipType.RELATED_TO,
        confidence_score=80,
        trust_weight=70,
    )
    g.add_relationship(r2)


def _line_graph(n: int = 4) -> IntelligenceGraph:
    g = IntelligenceGraph()
    nodes = [Person(name=f"Node{i}") for i in range(n)]
    for nd in nodes:
        g.add_entity(nd)
    for i in range(n - 1):
        _add_undirected_edge(g, nodes[i].id, nodes[i + 1].id)
    return g


def _star_graph(n_leaves: int = 3) -> IntelligenceGraph:
    g = IntelligenceGraph()
    center = Person(name="Center")
    g.add_entity(center)
    leaves = [Person(name=f"Leaf{i}") for i in range(n_leaves)]
    for leaf in leaves:
        g.add_entity(leaf)
        _add_undirected_edge(g, center.id, leaf.id)
    return g


def _complete_graph(n: int = 4) -> IntelligenceGraph:
    g = IntelligenceGraph()
    nodes = [Person(name=f"Node{i}") for i in range(n)]
    for nd in nodes:
        g.add_entity(nd)
    for i in range(n):
        for j in range(i + 1, n):
            _add_undirected_edge(g, nodes[i].id, nodes[j].id)
    return g


class TestDegreeCentrality:
    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        a = GraphAnalytics(g)
        node_id = list(g.nodes.keys())[0]
        assert a.degree_centrality(node_id) == 0.0

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
        an = GraphAnalytics(g)
        assert an.degree_centrality(a.id) == 1.0
        assert an.degree_centrality(b.id) == 1.0

    def test_line_graph_endpoints(self):
        g = _line_graph(4)
        an = GraphAnalytics(g)
        ids = list(g.nodes.keys())
        dc = [an.degree_centrality(nid) for nid in ids]
        assert dc[0] == pytest.approx(1.0 / 3)
        assert dc[1] == pytest.approx(2.0 / 3)
        assert dc[2] == pytest.approx(2.0 / 3)
        assert dc[3] == pytest.approx(1.0 / 3)

    def test_star_center_high(self):
        g = _star_graph(4)
        an = GraphAnalytics(g)
        center_id = [nid for nid in g.nodes if len(g.adjacency[nid]) == 4][0]
        leaf_id = [nid for nid in g.nodes if nid != center_id][0]
        assert an.degree_centrality(center_id) == pytest.approx(4.0 / 4)
        assert an.degree_centrality(leaf_id) == pytest.approx(1.0 / 4)

    def test_complete_graph(self):
        g = _complete_graph(5)
        an = GraphAnalytics(g)
        for nid in g.nodes:
            assert an.degree_centrality(nid) == pytest.approx(1.0)

    def test_nonexistent_node(self):
        g = _line_graph(3)
        an = GraphAnalytics(g)
        assert an.degree_centrality("nonexistent") == 0.0


class TestPageRank:
    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        an = GraphAnalytics(g)
        node_id = list(g.nodes.keys())[0]
        assert an.page_rank(node_id) == 1.0

    def test_two_nodes_undirected(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        g.add_entity(a)
        g.add_entity(b)
        _add_undirected_edge(g, a.id, b.id)
        an = GraphAnalytics(g)
        pr_a = an.page_rank(a.id)
        pr_b = an.page_rank(b.id)
        assert pr_a == pytest.approx(pr_b, abs=1e-4)

    def test_star_center_higher_than_leaf(self):
        g = _star_graph(3)
        an = GraphAnalytics(g)
        center_id = [nid for nid in g.nodes if len(g.forward_adjacency[nid]) == 3][0]
        leaf_id = [nid for nid in g.nodes if nid != center_id][0]
        pr_c = an.page_rank(center_id)
        pr_l = an.page_rank(leaf_id)
        assert pr_c > pr_l

    def test_page_rank_sum_one(self):
        g = _star_graph(4)
        an = GraphAnalytics(g)
        total = sum(an.page_rank(nid) for nid in g.nodes)
        assert total == pytest.approx(1.0, abs=1e-4)

    def test_line_graph_inner_higher_than_ends(self):
        g = _line_graph(5)
        an = GraphAnalytics(g)
        ids = list(g.nodes.keys())
        for mid in ids[1:-1]:
            for end in [ids[0], ids[-1]]:
                assert an.page_rank(mid) >= an.page_rank(end)

    def test_deterministic(self):
        g = _star_graph(5)
        an = GraphAnalytics(g)
        r1 = [an.page_rank(nid) for nid in sorted(g.nodes.keys())]
        r2 = [an.page_rank(nid) for nid in sorted(g.nodes.keys())]
        assert r1 == r2

    def test_nonexistent_node_returns_zero(self):
        g = _line_graph(3)
        an = GraphAnalytics(g)
        assert an.page_rank("nonexistent") == 0.0

    def test_empty_graph(self):
        g = IntelligenceGraph()
        an = GraphAnalytics(g)
        assert an.page_rank("anything") == 0.0


class TestGraphStats:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        an = GraphAnalytics(g)
        s = an.stats()
        assert s["node_count"] == 0
        assert s["edge_count"] == 0
        assert s["density"] == 0.0
        assert s["average_degree"] == 0.0

    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        an = GraphAnalytics(g)
        s = an.stats()
        assert s["node_count"] == 1
        assert s["edge_count"] == 0
        assert s["density"] == 0.0
        assert s["average_degree"] == 0.0

    def test_line_graph(self):
        g = _line_graph(4)
        an = GraphAnalytics(g)
        s = an.stats()
        assert s["node_count"] == 4
        assert s["edge_count"] == 6
        assert s["density"] == pytest.approx(6.0 * 2 / (4 * 3), abs=1e-6)
        assert s["average_degree"] == pytest.approx(1.5, abs=1e-4)

    def test_complete_graph(self):
        g = _complete_graph(5)
        an = GraphAnalytics(g)
        s = an.stats()
        assert s["node_count"] == 5
        assert s["edge_count"] == 20
        assert s["density"] == 2.0
        assert s["average_degree"] == 4.0

    def test_star_graph(self):
        g = _star_graph(3)
        an = GraphAnalytics(g)
        s = an.stats()
        assert s["node_count"] == 4
        assert s["edge_count"] == 6
        assert s["average_degree"] == 1.5

    def test_rounding(self):
        g = _line_graph(3)
        an = GraphAnalytics(g)
        s = an.stats()
        assert isinstance(s["density"], float)
        assert isinstance(s["average_degree"], float)

    def test_stats_with_detail(self):
        g = _line_graph(4)
        an = GraphAnalytics(g)
        s = an.stats(detail=True)
        assert "clustering_coefficient" in s
        assert "max_degree" in s
        assert "min_degree" in s
        assert "degree_histogram" in s
        assert s["max_degree"] == 2
        assert s["min_degree"] == 1

    def test_stats_without_detail_excludes_extra(self):
        g = _line_graph(4)
        an = GraphAnalytics(g)
        s = an.stats(detail=False)
        assert "clustering_coefficient" not in s
        assert "degree_histogram" not in s


class TestBetweennessCentrality:
    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        an = GraphAnalytics(g)
        assert an.betweenness_centrality(list(g.nodes.keys())[0]) == 0.0

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
        an = GraphAnalytics(g)
        assert an.betweenness_centrality(a.id) == 0.0
        assert an.betweenness_centrality(b.id) == 0.0

    def test_line_graph_center_highest(self):
        g = _line_graph(5)
        an = GraphAnalytics(g)
        ids = list(g.nodes.keys())
        bc = [an.betweenness_centrality(nid) for nid in ids]
        assert bc[0] == pytest.approx(0.0, abs=1e-6)
        assert bc[2] > bc[1]
        assert bc[2] > bc[0]
        assert bc[2] == pytest.approx(bc[2], abs=1e-6)

    def test_star_center_highest(self):
        g = _star_graph(4)
        an = GraphAnalytics(g)
        center_id = [nid for nid in g.nodes if len(g.adjacency[nid]) == 4][0]
        leaf_id = [nid for nid in g.nodes if nid != center_id][0]
        bc_c = an.betweenness_centrality(center_id)
        bc_l = an.betweenness_centrality(leaf_id)
        assert bc_c > bc_l

    def test_complete_graph_all_zero(self):
        g = _complete_graph(5)
        an = GraphAnalytics(g)
        for nid in g.nodes:
            assert an.betweenness_centrality(nid) == pytest.approx(0.0, abs=1e-6)

    def test_nonexistent_node(self):
        g = _line_graph(3)
        an = GraphAnalytics(g)
        assert an.betweenness_centrality("nonexistent") == 0.0

    def test_empty_graph(self):
        g = IntelligenceGraph()
        an = GraphAnalytics(g)
        assert an.betweenness_centrality("x") == 0.0

    def test_deterministic(self):
        g = _star_graph(3)
        an = GraphAnalytics(g)
        r1 = [an.betweenness_centrality(nid) for nid in sorted(g.nodes.keys())]
        r2 = [an.betweenness_centrality(nid) for nid in sorted(g.nodes.keys())]
        assert r1 == r2


class TestClosenessCentrality:
    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        an = GraphAnalytics(g)
        assert an.closeness_centrality(list(g.nodes.keys())[0]) == 0.0

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
        an = GraphAnalytics(g)
        assert an.closeness_centrality(a.id) == pytest.approx(1.0, abs=1e-4)
        assert an.closeness_centrality(b.id) == pytest.approx(1.0, abs=1e-4)

    def test_star_center_higher(self):
        g = _star_graph(4)
        an = GraphAnalytics(g)
        center_id = [nid for nid in g.nodes if len(g.adjacency[nid]) == 4][0]
        leaf_id = [nid for nid in g.nodes if nid != center_id][0]
        cc_c = an.closeness_centrality(center_id)
        cc_l = an.closeness_centrality(leaf_id)
        assert cc_c > cc_l

    def test_line_graph_inner_higher(self):
        g = _line_graph(5)
        an = GraphAnalytics(g)
        ids = list(g.nodes.keys())
        cc = [an.closeness_centrality(nid) for nid in ids]
        assert cc[2] > cc[0]
        assert cc[2] > cc[1]

    def test_disconnected_returns_nonzero_for_reachable(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        c = Person(name="C")
        g.add_entity(a)
        g.add_entity(b)
        g.add_entity(c)
        r = Relationship(
            source_id=a.id,
            target_id=b.id,
            type=RelationshipType.RELATED_TO,
            confidence_score=80,
            trust_weight=70,
        )
        g.add_relationship(r)
        an = GraphAnalytics(g)
        cc_a = an.closeness_centrality(a.id)
        cc_c = an.closeness_centrality(c.id)
        assert cc_a > 0.0
        assert cc_c == 0.0

    def test_nonexistent_node(self):
        g = _line_graph(3)
        an = GraphAnalytics(g)
        assert an.closeness_centrality("nonexistent") == 0.0

    def test_empty_graph(self):
        g = IntelligenceGraph()
        an = GraphAnalytics(g)
        assert an.closeness_centrality("x") == 0.0

    def test_deterministic(self):
        g = _star_graph(3)
        an = GraphAnalytics(g)
        r1 = [an.closeness_centrality(nid) for nid in sorted(g.nodes.keys())]
        r2 = [an.closeness_centrality(nid) for nid in sorted(g.nodes.keys())]
        assert r1 == r2


class TestLocalClustering:
    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        an = GraphAnalytics(g)
        assert an.local_clustering(list(g.nodes.keys())[0]) == 0.0

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
        an = GraphAnalytics(g)
        assert an.local_clustering(a.id) == 0.0
        assert an.local_clustering(b.id) == 0.0

    def test_triangle(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        c = Person(name="C")
        g.add_entity(a)
        g.add_entity(b)
        g.add_entity(c)
        _add_undirected_edge(g, a.id, b.id)
        _add_undirected_edge(g, b.id, c.id)
        _add_undirected_edge(g, a.id, c.id)
        an = GraphAnalytics(g)
        assert an.local_clustering(a.id) == pytest.approx(1.0)
        assert an.local_clustering(b.id) == pytest.approx(1.0)
        assert an.local_clustering(c.id) == pytest.approx(1.0)

    def test_line_graph(self):
        g = _line_graph(4)
        an = GraphAnalytics(g)
        for nid in g.nodes:
            assert an.local_clustering(nid) == 0.0

    def test_star_graph_leaves_zero(self):
        g = _star_graph(4)
        an = GraphAnalytics(g)
        center_id = [nid for nid in g.nodes if len(g.adjacency[nid]) == 4][0]
        leaf_id = [nid for nid in g.nodes if nid != center_id][0]
        assert an.local_clustering(leaf_id) == 0.0
        assert an.local_clustering(center_id) == 0.0


class TestAverageClustering:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        an = GraphAnalytics(g)
        assert an.average_clustering_coefficient() == 0.0

    def test_triangle(self):
        g = IntelligenceGraph()
        a = Person(name="A")
        b = Person(name="B")
        c = Person(name="C")
        g.add_entity(a)
        g.add_entity(b)
        g.add_entity(c)
        _add_undirected_edge(g, a.id, b.id)
        _add_undirected_edge(g, b.id, c.id)
        _add_undirected_edge(g, a.id, c.id)
        an = GraphAnalytics(g)
        assert an.average_clustering_coefficient() == pytest.approx(1.0)

    def test_line_graph(self):
        g = _line_graph(4)
        an = GraphAnalytics(g)
        assert an.average_clustering_coefficient() == 0.0


class TestDegreeHistogram:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        an = GraphAnalytics(g)
        assert an.degree_histogram() == []

    def test_single_node(self):
        g = IntelligenceGraph()
        g.add_entity(Person(name="Alone"))
        an = GraphAnalytics(g)
        h = an.degree_histogram()
        assert h == [{"degree": 0, "count": 1}]

    def test_line_graph_4(self):
        g = _line_graph(4)
        an = GraphAnalytics(g)
        h = an.degree_histogram()
        assert h[0] == {"degree": 0, "count": 0}
        assert h[1] == {"degree": 1, "count": 2}
        assert h[2] == {"degree": 2, "count": 2}

    def test_star_graph(self):
        g = _star_graph(3)
        an = GraphAnalytics(g)
        h = an.degree_histogram()
        assert h[0] == {"degree": 0, "count": 0}
        assert h[1] == {"degree": 1, "count": 3}
        assert h[2] == {"degree": 2, "count": 0}
        assert h[3] == {"degree": 3, "count": 1}

    def test_deterministic_order(self):
        g = _star_graph(5)
        an = GraphAnalytics(g)
        assert an.degree_histogram() == an.degree_histogram()


class TestMaxMinDegree:
    def test_empty(self):
        g = IntelligenceGraph()
        an = GraphAnalytics(g)
        assert an.max_degree() == 0
        assert an.min_degree() == 0

    def test_line_graph(self):
        g = _line_graph(4)
        an = GraphAnalytics(g)
        assert an.max_degree() == 2
        assert an.min_degree() == 1

    def test_star_graph(self):
        g = _star_graph(3)
        an = GraphAnalytics(g)
        assert an.max_degree() == 3
        assert an.min_degree() == 1
