import random
from typing import Any

from intelgraph.core.entity.person import Person
from intelgraph.core.graph.anomaly import (
    EXPLANATION_SCHEMA_VERSION,
    AnomalyBaseline,
    AnomalyDetector,
)
from intelgraph.core.graph.edge import Edge
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node


def _make_graph(seed: int = 42) -> IntelligenceGraph:
    random.seed(seed)
    g = IntelligenceGraph()
    for i in range(15):
        nid = f"node_{i}"
        ent = Person(id=nid, name=f"Person {i}", confidence_score=50, trust_score=50)
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
        ("node_10", "node_11", 80),
        ("node_11", "node_12", 70),
        ("node_12", "node_13", 90),
        ("node_13", "node_14", 60),
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


class TestAnomalyBaseline:
    def test_empty_baseline(self):
        bl = AnomalyBaseline()
        assert bl.get_all_baselines() == {}

    def test_record_snapshot(self):
        bl = AnomalyBaseline({"baseline_history_size": 10})
        features = {"n1": {"degree": 5.0, "confidence": 80.0, "__entity_type": "person"}}
        bl.record_snapshot(features)
        assert "n1" in bl._feature_histories
        assert len(bl._feature_histories["n1"]) == 1

    def test_compute_baselines(self):
        bl = AnomalyBaseline()
        features = {}
        for i in range(10):
            nid = f"n{i}"
            features[nid] = {"degree": float(i * 2), "confidence": 50.0, "__entity_type": "test"}
        bl.compute_baselines(features)
        baselines = bl.get_all_baselines()
        assert "test" in baselines
        assert "degree" in baselines["test"]
        assert baselines["test"]["degree"]["mean"] == 9.0
        assert baselines["test"]["degree"]["std"] > 0

    def test_adaptive_threshold(self):
        bl = AnomalyBaseline()
        features = {
            f"n{i}": {"degree": float(i), "confidence": 50.0, "__entity_type": "t"}
            for i in range(10)
        }
        bl.compute_baselines(features)
        thresh = bl.compute_adaptive_threshold("t", "degree", multiplier=2.0)
        mean = bl.get_baseline("t", "degree")["mean"]
        std = bl.get_baseline("t", "degree")["std"]
        expected = mean + 2.0 * std
        assert abs(thresh - expected) < 0.01

    def test_drift_deviation(self):
        bl = AnomalyBaseline()
        features = {
            f"n{i}": {"degree": float(i), "confidence": 50.0, "__entity_type": "t"}
            for i in range(5)
        }
        bl.compute_baselines(features)
        new_features = {"n0": {"degree": 100.0, "confidence": 50.0, "__entity_type": "t"}}
        drift = bl.drift_deviation(new_features)
        assert "n0" in drift
        assert drift["n0"] > 0.5

    def test_historical_drift(self):
        bl = AnomalyBaseline()
        for i in range(10):
            bl.record_snapshot(
                {"n1": {"degree": float(i), "confidence": 50.0, "__entity_type": "t"}}
            )
        drift = bl.historical_drift()
        assert "n1" in drift
        assert drift["n1"] > 0


class TestAnomalyDetector:
    def test_empty_graph(self):
        g = IntelligenceGraph()
        detector = AnomalyDetector(g)
        result = detector.detect()
        assert result["total_nodes_analyzed"] == 0
        assert result["detections"]["high"] == 0

    def test_detect_deterministic(self):
        g = _make_graph()
        d1 = AnomalyDetector(g)
        d2 = AnomalyDetector(g)
        r1 = d1.detect()
        r2 = d2.detect()
        assert r1["detections"] == r2["detections"]
        assert r1["graph_version"] == r2["graph_version"]

    def test_detect_populated_graph(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.detect()
        assert result["total_nodes_analyzed"] == 15
        assert result["graph_node_count"] == 15
        assert result["graph_edge_count"] == 18
        assert "high" in result["detections"]
        assert "medium" in result["detections"]
        assert "low" in result["detections"]

    # --- Statistical Z-Score ---

    def test_statistical_zscore(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.statistical_zscore()
        assert result["method"] == "zscore"
        assert "anomalies" in result
        assert result["anomaly_count"] >= 0

    def test_statistical_zscore_empty(self):
        g = IntelligenceGraph()
        detector = AnomalyDetector(g)
        result = detector.statistical_zscore()
        assert result["anomalies"] == {}

    def test_statistical_zscore_deterministic(self):
        g = _make_graph()
        d1 = AnomalyDetector(g)
        d2 = AnomalyDetector(g)
        assert d1.statistical_zscore()["anomalies"] == d2.statistical_zscore()["anomalies"]

    # --- Statistical IQR ---

    def test_statistical_iqr(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.statistical_iqr()
        assert result["method"] == "iqr"
        assert "anomalies" in result

    def test_statistical_iqr_empty(self):
        g = IntelligenceGraph()
        detector = AnomalyDetector(g)
        result = detector.statistical_iqr()
        assert result["anomalies"] == {}

    def test_statistical_iqr_deterministic(self):
        g = _make_graph()
        d1 = AnomalyDetector(g)
        d2 = AnomalyDetector(g)
        assert d1.statistical_iqr()["anomalies"] == d2.statistical_iqr()["anomalies"]

    # --- Graph Degree Outliers ---

    def test_degree_outliers(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.graph_degree_outliers()
        assert result["method"] == "degree_outlier"
        assert "anomalies" in result

    def test_degree_outliers_empty(self):
        g = IntelligenceGraph()
        detector = AnomalyDetector(g)
        result = detector.graph_degree_outliers()
        assert result["anomalies"] == {}

    def test_degree_outliers_deterministic(self):
        g = _make_graph()
        d1 = AnomalyDetector(g)
        d2 = AnomalyDetector(g)
        assert d1.graph_degree_outliers()["anomalies"] == d2.graph_degree_outliers()["anomalies"]

    # --- Temporal Deviation ---

    def test_temporal_deviation(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.temporal_deviation()
        assert result["method"] == "temporal"
        assert "anomalies" in result

    def test_temporal_deviation_empty(self):
        g = IntelligenceGraph()
        detector = AnomalyDetector(g)
        result = detector.temporal_deviation()
        assert result["anomalies"] == {}

    def test_temporal_deviation_with_baseline(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        detector.multi_factor_score()
        result = detector.temporal_deviation()
        assert result["method"] == "temporal"

    # --- Community Anomaly ---

    def test_community_anomaly(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.community_anomaly()
        assert result["method"] == "community"
        assert result["community_count"] >= 2

    def test_community_anomaly_empty(self):
        g = IntelligenceGraph()
        detector = AnomalyDetector(g)
        result = detector.community_anomaly()
        assert result["anomalies"] == {}

    def test_community_anomaly_with_external_communities(self):
        g = _make_graph()
        communities = {"c1": ["node_0", "node_1", "node_2"], "c2": ["node_3", "node_4"]}
        detector = AnomalyDetector(g, communities=communities)
        result = detector.community_anomaly(communities)
        assert result["community_count"] == 2

    # --- Multi-Factor Scoring ---

    def test_multi_factor_score(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.multi_factor_score()
        assert "scores" in result
        assert len(result["scores"]) == 15
        assert "weights" in result
        assert "graph_version" in result

    def test_multi_factor_score_empty(self):
        g = IntelligenceGraph()
        detector = AnomalyDetector(g)
        result = detector.multi_factor_score()
        assert result["scores"] == {}

    def test_multi_factor_score_deterministic(self):
        g = _make_graph()
        d1 = AnomalyDetector(g)
        d2 = AnomalyDetector(g)
        r1 = d1.multi_factor_score()
        r2 = d2.multi_factor_score()
        assert r1["scores"] == r2["scores"]

    def test_multi_factor_score_weights_sum(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.multi_factor_score()
        total_weight = sum(result["weights"].values())
        assert abs(total_weight - 1.0) < 0.01

    # --- Feature Contributions ---

    def test_feature_contributions(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        detector.multi_factor_score()
        contribs = detector.feature_contributions("node_0")
        assert len(contribs) > 0
        total = sum(contribs.values())
        assert abs(total - 1.0) < 0.01

    def test_feature_contributions_nonexistent(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        assert detector.feature_contributions("nonexistent") == {}

    # --- Confidence Score ---

    def test_confidence_score(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        detector.multi_factor_score()
        conf = detector.confidence_score("node_0")
        assert 0.0 <= conf <= 1.0

    def test_confidence_score_nonexistent(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        assert detector.confidence_score("nonexistent") == 0.0

    # --- Detect for node ---

    def test_detect_for_node(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.detect_for_node("node_0")
        assert result["found"] is True
        assert "anomaly_score" in result
        assert "confidence" in result
        assert "signals" in result
        assert "feature_contributions" in result
        assert 0.0 <= result["anomaly_score"] <= 1.0

    def test_detect_for_node_not_found(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.detect_for_node("nonexistent")
        assert result["found"] is False

    # --- Timeline ---

    def test_timeline(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.timeline()
        assert "timeline" in result
        assert result["entry_count"] > 0

    def test_timeline_empty(self):
        g = IntelligenceGraph()
        detector = AnomalyDetector(g)
        result = detector.timeline()
        assert result["entry_count"] == 0

    # --- Top Anomalies ---

    def test_top_anomalies(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.top_anomalies(5)
        assert result["count"] == 5
        assert len(result["top_nodes"]) == 5
        assert "graph_version" in result

    def test_top_anomalies_all(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.top_anomalies(100)
        assert result["count"] == 15

    def test_top_anomalies_empty(self):
        g = IntelligenceGraph()
        detector = AnomalyDetector(g)
        result = detector.top_anomalies(5)
        assert result["count"] == 0

    # --- Explanation ---

    def test_explain(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.explain("node_0")
        assert result["found"] is True
        assert result["schema_version"] == EXPLANATION_SCHEMA_VERSION
        assert "overall_score" in result
        assert "confidence" in result
        assert "severity" in result
        assert "signals" in result
        assert "top_contributors" in result
        assert "entity_type" in result
        assert "graph_version" in result
        assert "baseline_deviation" in result

    def test_explain_not_found(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.explain("nonexistent")
        assert result["found"] is False

    def test_explain_detail(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.explain_detail("node_0")
        assert result["found"] is True
        assert "feature_values" in result
        assert "entity_type_baseline" in result
        assert "network_context" in result

    def test_explain_detail_not_found(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.explain_detail("nonexistent")
        assert result["found"] is False

    # --- Graph Version ---

    def test_graph_version_consistency(self):
        g = _make_graph()
        d1 = AnomalyDetector(g)
        d2 = AnomalyDetector(g)
        assert d1._graph_version == d2._graph_version

    def test_graph_version_changes(self):
        g1 = _make_graph(seed=42)
        g2 = _make_graph(seed=42)
        g2.edges.pop("edge_0", None)
        d1 = AnomalyDetector(g1)
        d2 = AnomalyDetector(g2)
        assert d1._graph_version != d2._graph_version

    # --- Edge weight function ---

    def test_custom_weight_fn(self):
        g = _make_graph()
        detector = AnomalyDetector(g, weight_fn=lambda e: 0.5)
        features = detector._compute_features()
        nid = "node_0"
        assert features[nid]["total_edge_weight"] > 0


class TestAnomalyRegression:
    def test_anomaly_score_distribution(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.detect()
        scores = [t["anomaly_score"] for t in result["top_anomalies"]]
        assert scores == sorted(scores, reverse=True)

    def test_anomaly_score_range(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.multi_factor_score()
        for score in result["scores"].values():
            assert 0.0 <= score <= 1.0

    def test_explain_schema_consistency(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        for nid in ["node_0", "node_1", "node_2"]:
            expl = detector.explain(nid)
            assert expl["schema_version"] == EXPLANATION_SCHEMA_VERSION
            assert "overall_score" in expl
            assert "confidence" in expl
            assert "severity" in expl
            assert "signals" in expl
            assert "top_contributors" in expl
            assert expl["found"] is True

    def test_temporal_consistency(self):
        g = _make_graph()
        d1 = AnomalyDetector(g)
        d2 = AnomalyDetector(g)
        r1 = d1.timeline()
        r2 = d2.timeline()
        for e1, e2 in zip(r1["timeline"], r2["timeline"], strict=False):
            assert e1["node_id"] == e2["node_id"]
            assert e1["current_score"] == e2["current_score"]

    def test_cross_version_reproducibility(self):
        g1 = _make_graph(seed=42)
        g2 = _make_graph(seed=42)
        d1 = AnomalyDetector(g1)
        d2 = AnomalyDetector(g2)
        r1 = d1.detect()
        r2 = d2.detect()
        r1.pop("execution_time_ms")
        r2.pop("execution_time_ms")
        assert r1 == r2

    def test_baseline_drift_stress(self):
        bl = AnomalyBaseline({"baseline_history_size": 50})
        for epoch in range(20):
            features = {}
            for i in range(10):
                val = float(i + epoch * 0.5)
                features[f"n{i}"] = {"degree": val, "confidence": 50.0, "__entity_type": "stress"}
            bl.record_snapshot(features)
            bl.compute_baselines(features)
            drift = bl.drift_deviation(features)
        assert len(drift) > 0


class TestAnomalyFeatureAttribution:
    def test_feature_attribution_correctness(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        detector.multi_factor_score()
        contribs = detector.feature_contributions("node_0")
        total = sum(contribs.values())
        assert abs(total - 1.0) < 0.001

    def test_feature_attribution_all_nodes(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        detector.multi_factor_score()
        for nid in g.nodes:
            contribs = detector.feature_contributions(nid)
            total = sum(contribs.values())
            assert abs(total - 1.0) < 0.001

    def test_signal_level_breakdown(self):
        g = _make_graph()
        detector = AnomalyDetector(g)
        result = detector.detect_for_node("node_0")
        signals = result["signals"]
        expected_signals = {
            "zscore",
            "iqr",
            "degree_outlier",
            "temporal",
            "community",
            "influence_score",
        }
        assert expected_signals.issubset(set(signals.keys()))

    def test_contribution_stability(self):
        g = _make_graph()
        d1 = AnomalyDetector(g)
        d2 = AnomalyDetector(g)
        d1.multi_factor_score()
        d2.multi_factor_score()
        c1 = d1.feature_contributions("node_0")
        c2 = d2.feature_contributions("node_0")
        assert c1 == c2
