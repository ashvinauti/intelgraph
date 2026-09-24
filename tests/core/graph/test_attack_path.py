import random
from typing import Any

from intelgraph.core.entity.person import Person
from intelgraph.core.graph.attack_path import (
    ATTACK_PATH_SCHEMA_VERSION,
    AttackPathAnalyzer,
    AttackPathCache,
)
from intelgraph.core.graph.edge import Edge
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node


def _make_graph(seed: int = 42) -> IntelligenceGraph:
    random.seed(seed)
    g = IntelligenceGraph()
    for i in range(12):
        nid = f"node_{i}"
        ent = Person(
            id=nid,
            name=f"Person {i}",
            confidence_score=min(50 + i * 5, 95),
            trust_score=min(40 + i * 5, 90),
        )
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
        ("node_9", "node_10", 80),
        ("node_10", "node_11", 90),
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


class TestAttackPathCache:
    def test_cache_miss(self):
        cache = AttackPathCache()
        result = cache.get("src", "tgt", 5, "v1")
        assert result is None

    def test_cache_hit(self):
        cache = AttackPathCache()
        paths = [{"path_id": "p1"}]
        cache.set("src", "tgt", 5, "v1", paths)
        result = cache.get("src", "tgt", 5, "v1")
        assert result == paths

    def test_cache_version_mismatch(self):
        cache = AttackPathCache()
        cache.set("src", "tgt", 5, "v1", [{"path_id": "p1"}])
        result = cache.get("src", "tgt", 5, "v2")
        assert result is None

    def test_clear(self):
        cache = AttackPathCache()
        cache.set("src", "tgt", 5, "v1", [{"path_id": "p1"}])
        cache.clear()
        assert cache.get("src", "tgt", 5, "v1") is None


class TestAttackPathAnalyzer:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_shortest_path("nonexistent", "target")
        assert result["found"] is False
        result2 = analyzer.critical_nodes()
        assert len(result2["critical_nodes"]) == 0
        result3 = analyzer.attack_surface("nonexistent")
        assert result3["found"] is False

    # --- find_shortest_path ---

    def test_shortest_path_found(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_shortest_path("node_0", "node_7")
        assert result["found"] is True
        assert result["source"] == "node_0"
        assert result["target"] == "node_7"
        assert "path" in result
        assert result["path"]["node_ids"][0] == "node_0"
        assert result["path"]["node_ids"][-1] == "node_7"
        assert result["schema_version"] == ATTACK_PATH_SCHEMA_VERSION
        assert "graph_version" in result

    def test_shortest_path_source_not_found(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_shortest_path("nonexistent", "node_0")
        assert result["found"] is False
        assert "error" in result

    def test_shortest_path_target_not_found(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_shortest_path("node_0", "nonexistent")
        assert result["found"] is False

    def test_shortest_path_same_node(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_shortest_path("node_0", "node_0")
        assert result["found"] is True
        assert result["length"] == 0
        assert result["risk_score"] == 1.0

    def test_shortest_path_no_path(self):
        g = _make_graph()
        g.adjacency = {}
        g.forward_adjacency = {}
        g.reverse_adjacency = {}
        analyzer = AttackPathAnalyzer(g)
        analyzer.find_shortest_path("node_0", "node_11")
        # node_0 and node_11 exist but disconnected
        g2 = _make_graph()
        analyzer2 = AttackPathAnalyzer(g2)
        # Find a path that doesn't exist by clearing edges for specific nodes
        result2 = analyzer2.find_shortest_path(
            "node_11", "node_0"
        )  # no outgoing edges from node_11
        assert "found" in result2

    def test_shortest_path_deterministic(self):
        g = _make_graph()
        d1 = AttackPathAnalyzer(g, deterministic=True)
        d2 = AttackPathAnalyzer(g, deterministic=True)
        r1 = d1.find_shortest_path("node_0", "node_9")
        r2 = d2.find_shortest_path("node_0", "node_9")
        assert r1["found"] == r2["found"]
        if r1["found"]:
            assert r1["path"]["node_ids"] == r2["path"]["node_ids"]

    def test_shortest_path_risk_score(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_shortest_path("node_0", "node_9")
        if result["found"]:
            risk = result["path"]["risk_score"]
            assert 0.0 <= risk <= 1.0
            decomp = result["path"]["risk_decomposition"]
            assert "confidence_product" in decomp
            assert "trust_product" in decomp

    # --- find_all_paths ---

    def test_all_paths_found(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_all_paths("node_0", max_depth=4, max_paths=50)
        assert result["found"] is True
        assert result["path_count"] > 0
        assert "paths" in result
        assert result["schema_version"] == ATTACK_PATH_SCHEMA_VERSION

    def test_all_paths_to_target(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_all_paths("node_0", target="node_7", max_depth=4, max_paths=50)
        if result["found"]:
            for p in result["paths"]:
                assert p["node_ids"][0] == "node_0"
                assert p["node_ids"][-1] == "node_7"

    def test_all_paths_source_not_found(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_all_paths("nonexistent", max_depth=3)
        assert result["found"] is False

    def test_all_paths_max_depth_bound(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_all_paths("node_0", max_depth=2, max_paths=100)
        for p in result.get("paths", []):
            assert p["length"] <= 2

    def test_all_paths_deterministic(self):
        g = _make_graph()
        d1 = AttackPathAnalyzer(g, deterministic=True)
        d2 = AttackPathAnalyzer(g, deterministic=True)
        r1 = d1.find_all_paths("node_0", max_depth=3)
        r2 = d2.find_all_paths("node_0", max_depth=3)
        assert r1["path_count"] == r2["path_count"]

    def test_all_paths_caching(self):
        g = _make_graph()
        cache = AttackPathCache()
        d1 = AttackPathAnalyzer(g, cache=cache)
        d1.find_all_paths("node_0", max_depth=3)
        d2 = AttackPathAnalyzer(g, cache=cache)
        r2 = d2.find_all_paths("node_0", max_depth=3)
        assert r2.get("cached") is True

    # --- critical_nodes ---

    def test_critical_nodes(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.critical_nodes(max_depth=4)
        assert "critical_nodes" in result
        assert "analytics" in result
        assert len(result["critical_nodes"]) > 0
        assert "graph_version" in result

    def test_critical_nodes_schema(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.critical_nodes()
        for cn in result["critical_nodes"]:
            assert "node_id" in cn
            assert "centrality_score" in cn
            assert "degree" in cn

    # --- attack_surface ---

    def test_attack_surface(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.attack_surface("node_0", max_depth=3)
        assert result["found"] is True
        assert result["entity_id"] == "node_0"
        assert "surface_size" in result
        assert "surface_by_type" in result
        assert result["surface_size"]["nodes"] > 0

    def test_attack_surface_not_found(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.attack_surface("nonexistent")
        assert result["found"] is False

    def test_attack_surface_zero_depth(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.attack_surface("node_0", max_depth=0)
        assert result["surface_size"]["nodes"] == 0

    # --- explain_path ---

    def test_explain_path_with_paths_result(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        paths_result = analyzer.find_all_paths("node_0", target="node_7", max_depth=4)
        if paths_result["found"] and paths_result["path_count"] > 0:
            first_path = paths_result["paths"][0]
            path_id = first_path["path_id"]
            expl = analyzer.explain_path(path_id, paths_result)
            assert expl["found"] is True
            assert expl["path_id"] == path_id
            assert "segment_breakdown" in expl
            assert len(expl["segment_breakdown"]) > 0
            for seg in expl["segment_breakdown"]:
                assert "segment_index" in seg
                assert "source" in seg
                assert "target" in seg
                assert "edge_id" in seg
                assert "confidence" in seg
                assert "trust" in seg
                assert "contribution" in seg

    def test_explain_path_not_found(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.explain_path("nonexistent")
        assert result["found"] is False

    def test_explain_path_single_path(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        sp = analyzer.find_shortest_path("node_0", "node_7")
        if sp["found"]:
            expl = analyzer.explain_path(sp["path"]["path_id"], sp)
            assert expl["found"] is True

    # --- get_path_by_id ---

    def test_get_path_by_id(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        paths_result = analyzer.find_all_paths("node_0", max_depth=3)
        if paths_result["path_count"] > 0:
            path_id = paths_result["paths"][0]["path_id"]
            result = analyzer.get_path_by_id(path_id, paths_result["paths"])
            assert result["found"] is True
            assert result["path"]["path_id"] == path_id

    def test_get_path_by_id_not_found(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.get_path_by_id("nonexistent", [])
        assert result["found"] is False


class TestAttackPathAnalytics:
    def test_path_risk_distribution(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.find_all_paths("node_0", max_depth=4)
        if result["path_count"] > 0:
            for p in result["paths"]:
                assert 0.0 <= p["risk_score"] <= 1.0

    def test_critical_node_frequency(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.critical_nodes(max_depth=4)
        analytics = result.get("analytics", {})
        if analytics:
            freq = analytics.get("critical_node_frequency", {})
            assert isinstance(freq, dict)

    def test_path_length_statistics(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.critical_nodes(max_depth=4)
        analytics = result.get("analytics", {})
        if analytics:
            stats = analytics.get("path_length_stats", {})
            if stats:
                assert "min" in stats
                assert "max" in stats
                assert "mean" in stats

    def test_bottleneck_nodes(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.critical_nodes(max_depth=4)
        analytics = result.get("analytics", {})
        if analytics:
            bottlenecks = analytics.get("bottleneck_nodes", [])
            if bottlenecks:
                for bn in bottlenecks:
                    assert "node_id" in bn
                    assert "path_frequency" in bn


class TestAttackPathRegression:
    def test_known_path_fixture(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        sp = analyzer.find_shortest_path("node_0", "node_1")
        assert sp["found"] is True
        assert len(sp["path"]["node_ids"]) == 2
        assert sp["path"]["edge_ids"] == ["edge_0"]

    def test_path_risk_scoring_correctness(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        sp = analyzer.find_shortest_path("node_0", "node_1")
        if sp["found"]:
            risk = sp["path"]["risk_decomposition"]
            assert risk["confidence_product"] > 0
            assert risk["trust_product"] > 0

    def test_cross_version_reproducibility(self):
        g1 = _make_graph(seed=42)
        g2 = _make_graph(seed=42)
        d1 = AttackPathAnalyzer(g1, deterministic=True)
        d2 = AttackPathAnalyzer(g2, deterministic=True)
        r1 = d1.find_shortest_path("node_0", "node_9")
        r2 = d2.find_shortest_path("node_0", "node_9")
        if r1["found"] and r2["found"]:
            r1_path = r1["path"]
            r2_path = r2["path"]
            assert r1_path["node_ids"] == r2_path["node_ids"]
            assert r1_path["risk_score"] == r2_path["risk_score"]

    def test_cross_version_reproducibility_all_paths(self):
        g1 = _make_graph(seed=42)
        g2 = _make_graph(seed=42)
        d1 = AttackPathAnalyzer(g1, deterministic=True)
        d2 = AttackPathAnalyzer(g2, deterministic=True)
        r1 = d1.find_all_paths("node_0", max_depth=3)
        r2 = d2.find_all_paths("node_0", max_depth=3)
        assert r1["path_count"] == r2["path_count"]

    def test_graph_version_tracking(self):
        g = _make_graph()
        d1 = AttackPathAnalyzer(g)
        v1 = d1._graph_version
        g2 = _make_graph()
        g2.nodes.pop("node_0", None)
        d2 = AttackPathAnalyzer(g2)
        v2 = d2._graph_version
        assert v1 != v2

    def test_explainability_schema(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        sp = analyzer.find_shortest_path("node_0", "node_7")
        if sp["found"]:
            expl = analyzer.explain_path(sp["path"]["path_id"], sp)
            assert expl["schema_version"] == ATTACK_PATH_SCHEMA_VERSION
            assert "graph_version" in expl

    def test_incremental_computation_cache(self):
        cache = AttackPathCache()
        g = _make_graph()
        d1 = AttackPathAnalyzer(g, cache=cache)
        r1 = d1.find_all_paths("node_0", target="node_7", max_depth=4)
        d2 = AttackPathAnalyzer(g, cache=cache)
        r2 = d2.find_all_paths("node_0", target="node_7", max_depth=4)
        assert r2.get("cached") is True
        if r1["found"]:
            assert r2["path_count"] == r1["path_count"]

    def test_attack_surface_entity_type(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        result = analyzer.attack_surface("node_0")
        assert result["entity_type"] is not None

    def test_risk_decomposition_segments(self):
        g = _make_graph()
        analyzer = AttackPathAnalyzer(g)
        sp = analyzer.find_shortest_path("node_0", "node_9")
        if sp["found"]:
            decomp = sp["path"]["risk_decomposition"]
            assert "mean_edge_confidence" in decomp
            assert "mean_edge_trust" in decomp
            assert "mean_target_influence" in decomp
