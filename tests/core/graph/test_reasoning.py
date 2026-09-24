import random
from typing import Any

from intelgraph.core.entity.person import Person
from intelgraph.core.graph.edge import Edge
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.graph.reasoning import (
    CAUSAL_SCHEMA_VERSION,
    CausalEdge,
    CausalGraph,
    CausalReasoner,
)


def _make_graph(seed: int = 42) -> IntelligenceGraph:
    random.seed(seed)
    g = IntelligenceGraph()
    for i in range(10):
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


class TestCausalGraph:
    def test_empty(self):
        cg = CausalGraph()
        assert cg.node_count() == 0
        assert cg.edge_count() == 0

    def test_add_edge(self):
        cg = CausalGraph()
        ce = CausalEdge(
            cause_id="a",
            effect_id="b",
            confidence=0.8,
            temporal_order_confirmed=True,
            influence_contribution=0.5,
        )
        assert cg.add_edge(ce) is True
        assert cg.node_count() == 2
        assert cg.edge_count() == 1

    def test_cycle_detection(self):
        cg = CausalGraph()
        cg.add_edge(CausalEdge("a", "b", 0.8, True, 0.5))
        cg.add_edge(CausalEdge("b", "c", 0.8, True, 0.5))
        ce = CausalEdge("c", "a", 0.8, True, 0.5)
        assert cg.add_edge(ce) is False

    def test_self_cycle(self):
        cg = CausalGraph()
        ce = CausalEdge("a", "a", 0.8, True, 0.5)
        assert cg.add_edge(ce) is False

    def test_get_causes_and_effects(self):
        cg = CausalGraph()
        cg.add_edge(CausalEdge("a", "b", 0.8, True, 0.5))
        cg.add_edge(CausalEdge("c", "b", 0.7, True, 0.4))
        assert len(cg.get_causes("b")) == 2
        assert len(cg.get_effects("a")) == 1

    def test_to_network(self):
        cg = CausalGraph()
        cg.add_edge(CausalEdge("a", "b", 0.8, True, 0.5))
        net = cg.to_network()
        assert net["node_count"] == 2
        assert net["edge_count"] == 1
        assert "a" in net["nodes"]
        assert "b" in net["nodes"]


class TestCausalReasoner:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        reasoner = CausalReasoner(g)
        result = reasoner.root_cause_analysis("nonexistent")
        assert result.get("found") is False
        result2 = reasoner.causal_graph_network()
        assert result2["causal_graph"]["node_count"] == 0

    def test_build_causal_graph(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        cg = reasoner._build_causal_graph()
        assert cg.node_count() > 0
        assert cg.edge_count() > 0

    def test_causal_graph_dag(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        cg = reasoner._build_causal_graph()
        edges = cg.get_all_edges()
        for edge in edges:
            assert edge.cause_id != edge.effect_id
            assert edge.confidence > 0

    def test_root_cause_analysis(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.root_cause_analysis("node_7", max_depth=4, max_causes=5)
        assert result.get("found") is True
        assert "root_causes" in result
        assert "trace_id" in result
        assert result["schema_version"] == CAUSAL_SCHEMA_VERSION
        assert "graph_version" in result

    def test_root_cause_not_found(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.root_cause_analysis("nonexistent")
        assert result.get("found") is False

    def test_root_cause_ranking(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.root_cause_analysis("node_7", max_depth=4, max_causes=10)
        if result.get("found"):
            causes = result["root_causes"]
            if len(causes) > 1:
                for i in range(len(causes) - 1):
                    assert causes[i]["confidence"] >= causes[i + 1]["confidence"]

    def test_root_cause_deterministic(self):
        g = _make_graph()
        r1 = CausalReasoner(g, deterministic=True)
        r2 = CausalReasoner(g, deterministic=True)
        res1 = r1.root_cause_analysis("node_7", max_depth=4)
        res2 = r2.root_cause_analysis("node_7", max_depth=4)
        for rc1, rc2 in zip(res1["root_causes"], res2["root_causes"], strict=False):
            assert rc1["root_cause_node"] == rc2["root_cause_node"]
            assert rc1["path"] == rc2["path"]
            assert abs(rc1["confidence"] - rc2["confidence"]) < 0.01
            assert abs(rc1["uncertainty"] - rc2["uncertainty"]) < 0.01
            assert rc1["length"] == rc2["length"]

    # --- Causal Path ---

    def test_causal_path(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.causal_path("node_0", "node_7", max_depth=4)
        assert "trace_id" in result
        assert result["schema_version"] == CAUSAL_SCHEMA_VERSION

    def test_causal_path_source_not_found(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.causal_path("nonexistent", "node_7")
        assert result.get("found") is False

    def test_causal_path_target_not_found(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.causal_path("node_0", "nonexistent")
        assert result.get("found") is False

    def test_causal_path_same_node(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.causal_path("node_0", "node_0")
        assert result.get("found") is True

    def test_causal_path_paths_have_confidence(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.causal_path("node_0", "node_7", max_depth=4)
        if result.get("found") and result.get("paths"):
            for p in result["paths"]:
                assert 0.0 <= p["confidence"] <= 1.0
                assert "path_id" in p
                assert "edges" in p

    # --- Explain ---

    def test_explain(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.explain("node_0", max_depth=3)
        assert result.get("found") is True
        assert "direct_causes" in result
        assert "direct_effects" in result
        assert "ancestor_chain" in result
        assert "descendant_chain" in result
        assert "causal_graph" in result
        assert "trace_id" in result

    def test_explain_not_found(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.explain("nonexistent")
        assert result.get("found") is False

    # --- Chains ---

    def test_chains(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.chains("node_0", max_depth=3)
        assert result.get("found") is True
        assert "cause_chains" in result
        assert "effect_chains" in result
        assert "trace_id" in result

    def test_chains_not_found(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.chains("nonexistent")
        assert result.get("found") is False

    # --- Causal Graph Network ---

    def test_causal_graph_network(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.causal_graph_network()
        assert "causal_graph" in result
        assert "trace_id" in result
        assert result["schema_version"] == CAUSAL_SCHEMA_VERSION

    # --- Top Causes ---

    def test_top_causes(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.top_causes("node_7", max_depth=4, top_n=5)
        assert result.get("found") is True
        assert "root_causes" in result
        assert "cross_community_propagation" in result

    def test_top_causes_not_found(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.top_causes("nonexistent")
        assert result.get("found") is False

    # --- Lineage ---

    def test_lineage_tracking(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.root_cause_analysis("node_7", max_depth=3, max_causes=5)
        if result.get("found"):
            for rc in result["root_causes"]:
                assert "lineage" in rc
                if rc["lineage"]:
                    for entry in rc["lineage"]:
                        assert "hop" in entry
                        assert "cause" in entry
                        assert "effect" in entry
                        assert "confidence" in entry

    # --- Uncertainty ---

    def test_uncertainty_propagation(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.root_cause_analysis("node_7", max_depth=3, max_causes=5)
        if result.get("found"):
            for rc in result["root_causes"]:
                assert 0.0 <= rc["uncertainty"] <= 1.0

    # --- Trace ID ---

    def test_trace_id_unique(self):
        g = _make_graph()
        r1 = CausalReasoner(g)
        r2 = CausalReasoner(g)
        t1 = r1._generate_trace_id()
        t2 = r2._generate_trace_id()
        assert t1 != t2

    def test_trace_id_in_all_results(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        for method in [
            "root_cause_analysis",
            "causal_path",
            "explain",
            "chains",
            "causal_graph_network",
            "top_causes",
        ]:
            if method == "root_cause_analysis":
                result = getattr(reasoner, method)("node_0", max_depth=3)
            elif method == "causal_path":
                result = getattr(reasoner, method)("node_0", "node_7", max_depth=3)
            elif method == "causal_graph_network":
                result = getattr(reasoner, method)()
            else:
                result = getattr(reasoner, method)("node_0", max_depth=3)
            assert "trace_id" in result, f"{method} missing trace_id"


class TestCausalRegression:
    def test_cross_version_reproducibility(self):
        g1 = _make_graph(seed=42)
        g2 = _make_graph(seed=42)
        r1 = CausalReasoner(g1, deterministic=True)
        r2 = CausalReasoner(g2, deterministic=True)
        res1 = r1.root_cause_analysis("node_7", max_depth=4)
        res2 = r2.root_cause_analysis("node_7", max_depth=4)
        assert res1["found"] == res2["found"]
        assert len(res1["root_causes"]) == len(res2["root_causes"])
        for rc1, rc2 in zip(res1["root_causes"], res2["root_causes"], strict=False):
            assert rc1["root_cause_node"] == rc2["root_cause_node"]
            assert rc1["path"] == rc2["path"]
            assert abs(rc1["confidence"] - rc2["confidence"]) < 0.01

    def test_causal_decay(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        assert reasoner._causal_decay(0) == 1.0
        assert reasoner._causal_decay(1) == 0.7
        assert reasoner._causal_decay(3) == 0.7**3

    def test_uncertainty_formula(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        u = reasoner._uncertainty_propagation([0.9, 0.8, 0.7])
        expected = 1.0 - (0.9 * 0.8 * 0.7)
        assert abs(u - expected) < 0.001

    def test_causal_graph_version(self):
        g1 = _make_graph(seed=42)
        g2 = _make_graph(seed=42)
        g2.nodes.pop("node_0", None)
        r1 = CausalReasoner(g1)
        r2 = CausalReasoner(g2)
        assert r1._graph_version != r2._graph_version

    def test_explain_schema_consistency(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        result = reasoner.explain("node_0")
        assert result["schema_version"] == CAUSAL_SCHEMA_VERSION
        assert "execution_mode" in result
        assert "graph_version" in result

    def test_root_cause_depth_bound(self):
        g = _make_graph()
        reasoner = CausalReasoner(g)
        r1 = reasoner.root_cause_analysis("node_7", max_depth=2, max_causes=10)
        r2 = reasoner.root_cause_analysis("node_7", max_depth=4, max_causes=10)
        if r1.get("found") and r2.get("found"):
            for rc in r1["root_causes"]:
                assert rc["length"] <= 2
