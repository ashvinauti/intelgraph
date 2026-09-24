import random
from typing import Any

from intelgraph.core.entity.person import Person
from intelgraph.core.graph.edge import Edge
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.influence import InfluencePropagation
from intelgraph.core.graph.node import Node


def _make_graph(seed: int = 42) -> IntelligenceGraph:
    random.seed(seed)
    g = IntelligenceGraph()
    for i in range(10):
        nid = f"node_{i}"
        ent = Person(id=nid, name=f"Person {i}", confidence_score=50)
        n = Node(entity=ent)
        g.nodes[nid] = n
        g.adjacency[nid] = set()
        g.forward_adjacency[nid] = set()
        g.reverse_adjacency[nid] = set()
        g.node_edges[nid] = set()
    edges_data = [
        ("node_0", "node_1", 80),
        ("node_0", "node_2", 60),
        ("node_1", "node_3", 90),
        ("node_1", "node_4", 50),
        ("node_2", "node_5", 70),
        ("node_2", "node_6", 40),
        ("node_3", "node_7", 85),
        ("node_4", "node_8", 75),
        ("node_5", "node_9", 65),
        ("node_6", "node_7", 55),
        ("node_7", "node_8", 45),
        ("node_8", "node_9", 95),
        ("node_3", "node_0", 30),
        ("node_5", "node_6", 35),
    ]
    for idx, (src, tgt, conf) in enumerate(edges_data):
        eid = f"edge_{idx}"
        rel = _make_rel(eid, src, tgt, conf)
        e = Edge(relationship=rel)
        g.edges[eid] = e
        g.adjacency[src].add(tgt)
        g.adjacency[tgt].add(src)
        g.forward_adjacency[src].add(tgt)
        g.reverse_adjacency[tgt].add(src)
        g.node_edges[src].add(eid)
        g.node_edges[tgt].add(eid)
        g.edge_node_map[eid] = (src, tgt)
    return g


def _make_rel(eid: str, src: str, tgt: str, conf: int) -> Any:
    from intelgraph.core.relationship import Relationship
    from intelgraph.core.relationship.types import RelationshipType

    return Relationship(
        id=eid,
        source_id=src,
        target_id=tgt,
        type=RelationshipType.RELATED_TO,
        confidence_score=conf,
        trust_weight=conf,
    )


class TestInfluencePropagation:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        infl = InfluencePropagation(g)
        result = infl.page_rank()
        assert result["scores"] == {}
        assert result["converged"] is True

    def test_page_rank_deterministic(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        r1 = infl.page_rank(damping=0.85, max_iterations=100, tolerance=1e-8)
        r2 = infl.page_rank(damping=0.85, max_iterations=100, tolerance=1e-8)
        assert r1["scores"] == r2["scores"]
        assert r1["iterations"] == r2["iterations"]

    def test_page_rank_converges(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.page_rank(damping=0.85, max_iterations=100, tolerance=1e-8)
        assert result["converged"] is True
        assert len(result["scores"]) == 10
        assert result["iterations"] < 100
        total = sum(result["scores"].values())
        assert abs(total - 1.0) < 0.01

    def test_page_rank_high_node_ranks_higher(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.page_rank()
        scores = list(result["scores"].values())
        assert scores == sorted(scores, reverse=True)
        assert scores[0] > scores[-1]

    def test_weighted_page_rank_deterministic(self):
        g = _make_graph()

        def weight_fn(e):
            return float(e.relationship.confidence_score) / 100.0 if e.relationship else 1.0

        infl = InfluencePropagation(g, weight_fn=weight_fn)
        r1 = infl.weighted_page_rank()
        r2 = infl.weighted_page_rank()
        assert r1["scores"] == r2["scores"]

    def test_weighted_page_rank_converges(self):
        g = _make_graph()

        def weight_fn(e):
            return float(e.relationship.confidence_score) / 100.0 if e.relationship else 1.0

        infl = InfluencePropagation(g, weight_fn=weight_fn)
        result = infl.weighted_page_rank()
        assert result["converged"] is True
        assert len(result["scores"]) == 10

    def test_weighted_page_rank_different_from_standard(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        pr = infl.page_rank()

        def weight_fn(e):
            return float(e.relationship.confidence_score) / 100.0 if e.relationship else 1.0

        infl_w = InfluencePropagation(g, weight_fn=weight_fn)
        wpr = infl_w.weighted_page_rank()
        assert pr["scores"] != wpr["scores"]

    def test_influence_propagation_basic(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.influence_propagation(
            seed_nodes={"node_0": 1.0},
            threshold=0.3,
            decay_factor=0.5,
            max_depth=5,
        )
        assert result["seed_count"] == 1
        assert result["nodes_activated"] >= 1
        assert "node_0" in result["influence"]

    def test_influence_propagation_no_seeds(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.influence_propagation(seed_nodes={}, threshold=0.5, decay_factor=0.5)
        assert result["nodes_activated"] == 0

    def test_influence_propagation_high_threshold(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.influence_propagation(
            seed_nodes={"node_0": 0.2},
            threshold=0.9,
            decay_factor=0.3,
            max_depth=2,
        )
        assert result["nodes_activated"] == 1

    def test_influence_propagation_deep(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.influence_propagation(
            seed_nodes={"node_0": 1.0, "node_3": 0.9},
            threshold=0.1,
            decay_factor=0.8,
            max_depth=10,
        )
        assert result["nodes_activated"] >= 3

    def test_influence_scores_basic(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.influence_scores()
        assert len(result["scores"]) == 10
        assert "components" in result
        assert abs(result["components"]["page_rank_weight"] - 0.5) < 0.01

    def test_influence_scores_deterministic(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        r1 = infl.influence_scores()
        r2 = infl.influence_scores()
        assert r1["scores"] == r2["scores"]

    def test_top_influence_nodes(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.top_influence_nodes(n=3)
        assert result["count"] == 3
        assert len(result["top_nodes"]) == 3
        assert result["total_nodes"] == 10
        scores = list(result["top_nodes"].values())
        assert scores == sorted(scores, reverse=True)

    def test_top_influence_nodes_all(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.top_influence_nodes(n=100)
        assert result["count"] == 10

    def test_influence_chain_found(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.influence_chain("node_0", max_depth=5, min_influence=0.001)
        assert result["found"] is True
        assert result["node_id"] == "node_0"
        assert len(result["chain"]) >= 1
        assert result["chain"][0]["node_id"] == "node_0"

    def test_influence_chain_not_found(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.influence_chain("nonexistent", max_depth=5)
        assert result["found"] is False

    def test_influence_chain_depth_limit(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.influence_chain("node_0", max_depth=1, min_influence=0.0)
        chain_depths = [entry["depth"] for entry in result["chain"]]
        assert all(d <= 1 for d in chain_depths)

    def test_influence_decay_model(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.influence_decay_model("node_0", distance=5, decay_factor=0.5)
        assert result["found"] is True
        assert len(result["decay_curve"]) == 6
        assert result["decay_curve"][0]["distance"] == 0
        assert result["decay_curve"][5]["distance"] == 5
        assert result["decay_curve"][0]["decayed_influence"] == result["base_score"]
        assert (
            result["decay_curve"][1]["decayed_influence"]
            < result["decay_curve"][0]["decayed_influence"]
        )

    def test_influence_decay_model_not_found(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        result = infl.influence_decay_model("nonexistent", distance=5)
        assert result["found"] is False

    def test_influence_distribution_by_community(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        communities = {
            "community_0": ["node_0", "node_1", "node_2"],
            "community_1": ["node_3", "node_4", "node_5"],
            "community_2": ["node_6", "node_7", "node_8", "node_9"],
        }
        result = infl.influence_distribution_by_community(communities)
        assert result["community_count"] == 3
        dist = result["distribution"]
        for cid in communities:
            assert cid in dist
            assert dist[cid]["member_count"] == len(communities[cid])
            assert dist[cid]["mean_influence"] > 0
            assert dist[cid]["max_influence"] >= dist[cid]["min_influence"]

    def test_weight_fn_custom(self):
        g = _make_graph()

        def custom_fn(e):
            return 0.5

        infl = InfluencePropagation(g, weight_fn=custom_fn)
        pr = infl.page_rank()
        wpr = infl.weighted_page_rank()
        assert len(pr["scores"]) == 10
        assert len(wpr["scores"]) == 10

    def test_deterministic_output_same_input(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        for _ in range(3):
            r1 = infl.page_rank()
            r2 = infl.page_rank()
            assert r1["scores"] == r2["scores"]
            r3 = infl.influence_scores()
            r4 = infl.influence_scores()
            assert r3["scores"] == r4["scores"]

    def test_execution_time_present(self):
        g = _make_graph()
        infl = InfluencePropagation(g)
        for method in [
            "page_rank",
            "weighted_page_rank",
            "influence_propagation",
            "influence_scores",
        ]:
            if method == "influence_propagation":
                result = infl.influence_propagation({"node_0": 1.0}, 0.3, 0.5, 3)
            else:
                result = getattr(infl, method)()
            assert "execution_time_ms" in result
            assert result["execution_time_ms"] >= 0

    def test_large_graph_benchmark(self):
        random.seed(42)
        g = IntelligenceGraph()
        for i in range(100):
            nid = f"n_{i}"
            ent = Person(id=nid, name=f"N {i}", confidence_score=50)
            n = Node(entity=ent)
            g.nodes[nid] = n
            g.adjacency[nid] = set()
            g.forward_adjacency[nid] = set()
            g.reverse_adjacency[nid] = set()
            g.node_edges[nid] = set()
        from intelgraph.core.relationship import Relationship
        from intelgraph.core.relationship.types import RelationshipType

        for i in range(200):
            src = f"n_{random.randint(0, 99)}"
            tgt = f"n_{random.randint(0, 99)}"
            if src == tgt:
                continue
            eid = f"e_{i}"
            rel = Relationship(
                id=eid,
                source_id=src,
                target_id=tgt,
                type=RelationshipType.RELATED_TO,
                confidence_score=random.randint(20, 100),
                trust_weight=random.randint(20, 100),
            )
            e = Edge(relationship=rel)
            g.edges[eid] = e
            g.adjacency[src].add(tgt)
            g.adjacency[tgt].add(src)
            g.forward_adjacency[src].add(tgt)
            g.reverse_adjacency[tgt].add(src)
            g.node_edges[src].add(eid)
            g.node_edges[tgt].add(eid)
            g.edge_node_map[eid] = (src, tgt)
        infl = InfluencePropagation(g)
        result = infl.page_rank(max_iterations=50)
        assert len(result["scores"]) == 100
        assert result["execution_time_ms"] > 0
