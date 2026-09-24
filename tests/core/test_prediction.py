from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from intelgraph.core.entity.technology import Technology
from intelgraph.core.features.store import FeatureStore
from intelgraph.core.graph.edge import Edge
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.graph.prediction import (
    ForecastHorizon,
    PredictionResult,
    Predictor,
)
from intelgraph.core.kernel.execution import (
    CrossSystemConsistency,
    KernelTrace,
    UnifiedExecutionKernel,
)
from intelgraph.core.models.registry import ModelRegistry, ModelStatus
from intelgraph.core.relationship.base import Relationship
from intelgraph.core.relationship.types import RelationshipType


def _make_entity(id: str) -> Technology:
    return Technology(
        id=id,
        confidence_score=50,
        trust_score=50,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, tzinfo=UTC),
    )


def _make_rel(id: str, src: str, tgt: str, conf: float = 0.5, trust: float = 0.5) -> Relationship:
    return Relationship(
        id=id,
        source_id=src,
        target_id=tgt,
        type=RelationshipType.RELATED_TO,
        confidence_score=int(conf * 100),
        trust_weight=int(trust * 100),
    )


def _build_graph() -> IntelligenceGraph:
    g = IntelligenceGraph()
    for eid in ["A", "B", "C", "D", "E"]:
        g.nodes[eid] = Node(entity=_make_entity(eid))
    edges = [
        ("r0", "A", "B", 0.8, 0.7),
        ("r1", "B", "C", 0.6, 0.5),
        ("r2", "C", "D", 0.9, 0.8),
        ("r3", "D", "E", 0.5, 0.4),
        ("r4", "A", "C", 0.7, 0.6),
    ]
    for rid, src, tgt, conf, trust in edges:
        rel = _make_rel(rid, src, tgt, conf, trust)
        g.edges[rid] = Edge(relationship=rel)
        g.adjacency.setdefault(src, set()).add(tgt)
        g.adjacency.setdefault(tgt, set()).add(src)
        g.forward_adjacency.setdefault(src, set()).add(tgt)
        g.reverse_adjacency.setdefault(tgt, set()).add(src)
        g.node_edges.setdefault(src, set()).add(rid)
        g.node_edges.setdefault(tgt, set()).add(rid)
        g.edge_node_map[rid] = (src, tgt)
    return g


@pytest.fixture
def graph() -> IntelligenceGraph:
    return _build_graph()


@pytest.fixture
def predictor(graph: IntelligenceGraph) -> Predictor:
    return Predictor(graph)


@pytest.fixture
def kernel(graph: IntelligenceGraph) -> UnifiedExecutionKernel:
    return UnifiedExecutionKernel(graph)


def _exclude_time_ids(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in ("prediction_id", "timestamp")}


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry()


@pytest.fixture
def store() -> FeatureStore:
    return FeatureStore()


# ---------------------------------------------------------------------------
# ForecastHorizon (Enum)
# ---------------------------------------------------------------------------


class TestForecastHorizon:
    def test_members(self) -> None:
        assert ForecastHorizon.SHORT.value == "short"
        assert ForecastHorizon.MEDIUM.value == "medium"
        assert ForecastHorizon.LONG.value == "long"


# ---------------------------------------------------------------------------
# PredictionResult
# ---------------------------------------------------------------------------


class TestPredictionResult:
    def test_create(self) -> None:
        pr = PredictionResult(
            prediction_id="p1",
            entity_id="A",
            prediction_type="risk",
            value=0.5,
            confidence=0.8,
            horizon="short",
        )
        assert pr.entity_id == "A"
        assert pr.value == 0.5

    def test_to_dict(self) -> None:
        pr = PredictionResult(
            prediction_id="p1",
            entity_id="A",
            prediction_type="risk",
            value=0.5,
            confidence=0.8,
            horizon="short",
        )
        d = pr.to_dict()
        assert d["entity_id"] == "A"
        assert d["value"] == 0.5


# ---------------------------------------------------------------------------
# Predictor - risk_forecast
# ---------------------------------------------------------------------------


class TestRiskForecast:
    def test_returns_prediction_result(self, predictor: Predictor) -> None:
        r = predictor.risk_forecast("A")
        assert isinstance(r, PredictionResult)
        assert r.prediction_type == "risk_forecast"

    def test_horizon_short(self, predictor: Predictor) -> None:
        r = predictor.risk_forecast("A", horizon=0)
        assert r.horizon == "short"

    def test_horizon_medium(self, predictor: Predictor) -> None:
        r = predictor.risk_forecast("A", horizon=1)
        assert r.horizon == "medium"

    def test_horizon_long(self, predictor: Predictor) -> None:
        r = predictor.risk_forecast("A", horizon=2)
        assert r.horizon == "long"

    def test_deterministic(self, predictor: Predictor) -> None:
        r1 = predictor.risk_forecast("A", 0)
        r2 = predictor.risk_forecast("A", 0)
        d1 = {k: v for k, v in r1.to_dict().items() if k not in ("prediction_id", "timestamp")}
        d2 = {k: v for k, v in r2.to_dict().items() if k not in ("prediction_id", "timestamp")}
        assert d1 == d2

    def test_unknown_node_does_not_raise(self, predictor: Predictor) -> None:
        r = predictor.risk_forecast("ZZZ")
        assert isinstance(r, PredictionResult)

    def test_value_bounded(self, predictor: Predictor) -> None:
        r = predictor.risk_forecast("A")
        assert 0.0 <= r.value <= 1.0

    def test_confidence_bounded(self, predictor: Predictor) -> None:
        r = predictor.risk_forecast("A")
        assert 0.0 <= r.confidence <= 1.0

    def test_uncertainty_bounded(self, predictor: Predictor) -> None:
        r = predictor.risk_forecast("A")
        assert 0.0 <= r.uncertainty <= 1.0


# ---------------------------------------------------------------------------
# Predictor - temporal_trend
# ---------------------------------------------------------------------------


class TestTemporalTrend:
    def test_type(self, predictor: Predictor) -> None:
        r = predictor.temporal_trend("B")
        assert r.prediction_type == "temporal_trend"

    def test_deterministic(self, predictor: Predictor) -> None:
        r1 = predictor.temporal_trend("B", 0)
        r2 = predictor.temporal_trend("B", 0)
        assert _exclude_time_ids(r1.to_dict()) == _exclude_time_ids(r2.to_dict())

    def test_horizon(self, predictor: Predictor) -> None:
        r = predictor.temporal_trend("B", 2)
        assert r.horizon == "long"

    def test_isolated_node(self) -> None:
        g = IntelligenceGraph()
        g.nodes["X"] = Node(entity=_make_entity("X"))
        p = Predictor(g)
        r = p.temporal_trend("X")
        assert 0.0 <= r.value <= 1.0


# ---------------------------------------------------------------------------
# Predictor - influence_trajectory
# ---------------------------------------------------------------------------


class TestInfluenceTrajectory:
    def test_type(self, predictor: Predictor) -> None:
        r = predictor.influence_trajectory("A")
        assert r.prediction_type == "influence_trajectory"

    def test_deterministic(self, predictor: Predictor) -> None:
        r1 = predictor.influence_trajectory("A", 0)
        r2 = predictor.influence_trajectory("A", 0)
        assert _exclude_time_ids(r1.to_dict()) == _exclude_time_ids(r2.to_dict())

    def test_isolated_node(self) -> None:
        g = IntelligenceGraph()
        g.nodes["X"] = Node(entity=_make_entity("X"))
        p = Predictor(g)
        r = p.influence_trajectory("X")
        assert 0.0 <= r.value <= 1.0


# ---------------------------------------------------------------------------
# Predictor - anomaly_likelihood
# ---------------------------------------------------------------------------


class TestAnomalyLikelihood:
    def test_type(self, predictor: Predictor) -> None:
        r = predictor.anomaly_likelihood("B")
        assert r.prediction_type == "anomaly_likelihood"

    def test_deterministic(self, predictor: Predictor) -> None:
        r1 = predictor.anomaly_likelihood("B", 0)
        r2 = predictor.anomaly_likelihood("B", 0)
        assert _exclude_time_ids(r1.to_dict()) == _exclude_time_ids(r2.to_dict())

    def test_isolated_node(self) -> None:
        g = IntelligenceGraph()
        g.nodes["X"] = Node(entity=_make_entity("X"))
        p = Predictor(g)
        r = p.anomaly_likelihood("X")
        assert 0.0 <= r.value <= 1.0


# ---------------------------------------------------------------------------
# Predictor - attack_path_probability
# ---------------------------------------------------------------------------


class TestAttackPathProbability:
    def test_type(self, predictor: Predictor) -> None:
        r = predictor.attack_path_probability("A")
        assert r.prediction_type == "attack_path_probability"

    def test_deterministic(self, predictor: Predictor) -> None:
        r1 = predictor.attack_path_probability("A", 0)
        r2 = predictor.attack_path_probability("A", 0)
        assert _exclude_time_ids(r1.to_dict()) == _exclude_time_ids(r2.to_dict())

    def test_connectivity_features(self, predictor: Predictor) -> None:
        r = predictor.attack_path_probability("A")
        assert "connectivity" in r.features
        assert "out_edges" in r.features
        assert "in_edges" in r.features

    def test_isolated_node(self) -> None:
        g = IntelligenceGraph()
        g.nodes["X"] = Node(entity=_make_entity("X"))
        p = Predictor(g)
        r = p.attack_path_probability("X")
        assert 0.0 <= r.value <= 1.0


# ---------------------------------------------------------------------------
# Predictor - community_evolution
# ---------------------------------------------------------------------------


class TestCommunityEvolution:
    def test_type(self, predictor: Predictor) -> None:
        r = predictor.community_evolution("A")
        assert r.prediction_type == "community_evolution"

    def test_deterministic(self, predictor: Predictor) -> None:
        r1 = predictor.community_evolution("A", horizon=0)
        r2 = predictor.community_evolution("A", horizon=0)
        assert _exclude_time_ids(r1.to_dict()) == _exclude_time_ids(r2.to_dict())

    def test_with_communities(self, predictor: Predictor) -> None:
        comms = {"c1": ["A", "B"], "c2": ["C", "D"]}
        r = predictor.community_evolution("A", comms, 0)
        assert "community_size" in r.features
        assert r.features["community_size"] == 2.0


# ---------------------------------------------------------------------------
# Predictor - counterfactual
# ---------------------------------------------------------------------------


class TestCounterfactual:
    def test_basic(self, predictor: Predictor) -> None:
        r = predictor.counterfactual("A", {"risk": 0.9})
        assert r.prediction_type == "counterfactual"

    def test_deterministic(self, predictor: Predictor) -> None:
        r1 = predictor.counterfactual("A", {"risk": 0.9})
        r2 = predictor.counterfactual("A", {"risk": 0.9})
        assert _exclude_time_ids(r1.to_dict()) == _exclude_time_ids(r2.to_dict())

    def test_empty_what_if(self, predictor: Predictor) -> None:
        r = predictor.counterfactual("A", {})
        assert isinstance(r, PredictionResult)

    def test_unknown_node(self, predictor: Predictor) -> None:
        r = predictor.counterfactual("ZZZ", {"risk": 0.9})
        assert isinstance(r, PredictionResult)


# ---------------------------------------------------------------------------
# Predictor - full_forecast
# ---------------------------------------------------------------------------


class TestFullForecast:
    def test_returns_dict(self, predictor: Predictor) -> None:
        r = predictor.full_forecast("A")
        assert isinstance(r, dict)
        assert "predictions" in r
        assert "ensemble" in r

    def test_15_predictions(self, predictor: Predictor) -> None:
        r = predictor.full_forecast("A")
        # multi_horizon: 5 types x 3 horizons = 15
        assert r["prediction_count"] == 15

    def test_all_types_present(self, predictor: Predictor) -> None:
        r = predictor.full_forecast("A")
        types = {p["prediction_type"] for p in r["predictions"]}
        assert types == {
            "risk_forecast",
            "temporal_trend",
            "influence_trajectory",
            "anomaly_likelihood",
            "attack_path_probability",
        }

    def test_deterministic_values(self, predictor: Predictor) -> None:
        r1 = predictor.full_forecast("A")
        r2 = predictor.full_forecast("A")
        e1 = r1["ensemble"]
        e2 = r2["ensemble"]
        assert e1["value"] == e2["value"]
        assert e1["confidence"] == e2["confidence"]
        assert e1["uncertainty"] == e2["uncertainty"]
        for p1, p2 in zip(r1["predictions"], r2["predictions"], strict=False):
            for k in (
                "entity_id",
                "prediction_type",
                "value",
                "confidence",
                "uncertainty",
                "horizon",
                "features",
                "contributions",
            ):
                assert p1[k] == p2[k], f"Mismatch in {k}: {p1[k]} != {p2[k]}"

    def test_graph_version(self, predictor: Predictor) -> None:
        r = predictor.full_forecast("A")
        assert "graph_version" in r
        assert len(r["graph_version"]) == 16


# ---------------------------------------------------------------------------
# Predictor - ensemble_score
# ---------------------------------------------------------------------------


class TestEnsembleScore:
    def test_basic(self, predictor: Predictor) -> None:
        preds = [
            PredictionResult(
                prediction_id="a",
                entity_id="X",
                prediction_type="a",
                value=0.5,
                confidence=0.8,
                horizon="short",
            ),
            PredictionResult(
                prediction_id="b",
                entity_id="X",
                prediction_type="b",
                value=0.7,
                confidence=0.6,
                horizon="short",
            ),
        ]
        r = predictor.ensemble_score(preds)
        assert r.prediction_type == "ensemble"
        assert 0.5 <= r.value <= 0.7

    def test_empty(self, predictor: Predictor) -> None:
        r = predictor.ensemble_score([])
        assert r.value == 0.0

    def test_custom_weights(self, predictor: Predictor) -> None:
        preds = [
            PredictionResult(
                prediction_id="a",
                entity_id="X",
                prediction_type="a",
                value=0.0,
                confidence=0.8,
                horizon="short",
            ),
            PredictionResult(
                prediction_id="b",
                entity_id="X",
                prediction_type="b",
                value=1.0,
                confidence=0.6,
                horizon="short",
            ),
        ]
        r = predictor.ensemble_score(preds, [1.0, 3.0])
        assert r.value == pytest.approx(0.75)

    def test_deterministic(self, predictor: Predictor) -> None:
        preds = [
            PredictionResult(
                prediction_id="a",
                entity_id="X",
                prediction_type="a",
                value=0.5,
                confidence=0.8,
                horizon="short",
            ),
            PredictionResult(
                prediction_id="b",
                entity_id="X",
                prediction_type="b",
                value=0.5,
                confidence=0.6,
                horizon="short",
            ),
        ]
        r1 = predictor.ensemble_score(preds)
        r2 = predictor.ensemble_score(preds)
        assert _exclude_time_ids(r1.to_dict()) == _exclude_time_ids(r2.to_dict())

    def test_multi_horizon(self, predictor: Predictor) -> None:
        r = predictor.full_forecast("A")
        assert 0.0 <= r["ensemble"]["value"] <= 1.0


# ---------------------------------------------------------------------------
# Predictor - multi_horizon_forecast
# ---------------------------------------------------------------------------


class TestMultiHorizonForecast:
    def test_returns_15(self, predictor: Predictor) -> None:
        results = predictor.multi_horizon_forecast("A")
        assert len(results) == 15

    def test_deterministic_values(self, predictor: Predictor) -> None:
        r1 = predictor.multi_horizon_forecast("A")
        r2 = predictor.multi_horizon_forecast("A")
        for p1, p2 in zip(r1, r2, strict=False):
            for k in (
                "entity_id",
                "prediction_type",
                "value",
                "confidence",
                "uncertainty",
                "horizon",
                "features",
                "contributions",
            ):
                assert getattr(p1, k) == getattr(p2, k)


# ---------------------------------------------------------------------------
# ModelRegistry
# ---------------------------------------------------------------------------


class TestModelRegistry:
    def test_register_and_list(self, registry: ModelRegistry) -> None:
        m = registry.register("risk_v1", "1.0.0")
        assert m.name == "risk_v1"
        assert m.status == ModelStatus.PENDING

    def test_approve_deploy(self, registry: ModelRegistry) -> None:
        m = registry.register("risk_v1", "1.0.0")
        assert registry.approve(m.model_id) is True
        versions = registry.get_versions("risk_v1")
        assert versions[-1].status == ModelStatus.APPROVED
        assert registry.deploy(m.model_id) is True
        versions = registry.get_versions("risk_v1")
        assert versions[-1].status == ModelStatus.DEPLOYED

    def test_rollback(self, registry: ModelRegistry) -> None:
        m = registry.register("risk_v1", "1.0.0")
        registry.approve(m.model_id)
        registry.deploy(m.model_id)
        assert registry.rollback(m.model_id) is True
        versions = registry.get_versions("risk_v1")
        assert versions[-1].status == ModelStatus.ROLLED_BACK

    def test_champion(self, registry: ModelRegistry) -> None:
        m = registry.register("risk_v1", "1.0.0")
        registry.approve(m.model_id)
        registry.deploy(m.model_id)
        assert registry.set_champion(m.model_id) is True
        champ = registry.get_champion("risk_v1")
        assert champ is not None and champ.model_id == m.model_id
        assert champ.status == ModelStatus.CHAMPION

    def test_add_challenger(self, registry: ModelRegistry) -> None:
        m1 = registry.register("risk_v1", "1.0.0")
        registry.approve(m1.model_id)
        registry.deploy(m1.model_id)
        registry.set_champion(m1.model_id)
        m2 = registry.register("risk_v1", "2.0.0")
        assert registry.add_challenger(m2.model_id) is True
        challengers = registry.get_challengers("risk_v1")
        assert len(challengers) == 1
        assert challengers[0].model_id == m2.model_id
        assert challengers[0].status == ModelStatus.CHALLENGER

    def test_performance(self, registry: ModelRegistry) -> None:
        m = registry.register("risk_v1", "1.0.0")
        registry.approve(m.model_id)
        registry.deploy(m.model_id)
        assert registry.record_performance(m.model_id, {"accuracy": 0.95}) is True
        versions = registry.get_versions("risk_v1")
        assert versions[-1].performance_metrics.get("accuracy") == 0.95

    def test_health_check(self, registry: ModelRegistry) -> None:
        m = registry.register("risk_v1", "1.0.0")
        # No champion yet
        hc = registry.health_check("risk_v1")
        assert hc["healthy"] is False
        # Promote to champion
        registry.approve(m.model_id)
        registry.deploy(m.model_id)
        registry.set_champion(m.model_id)
        hc = registry.health_check("risk_v1")
        assert hc["healthy"] is True

    def test_lineage(self, registry: ModelRegistry) -> None:
        m1 = registry.register("risk_v1", "1.0.0")
        registry.register("risk_v1", "2.0.0", parent_id=m1.model_id)
        dag = registry.lineage_dag("risk_v1")
        assert len(dag) == 1
        assert m1.model_id in dag[0]

    def test_snapshot(self, registry: ModelRegistry) -> None:
        registry.register("risk_v1", "1.0.0")
        registry.register("risk_v1", "2.0.0")
        snap = registry.snapshot()
        assert snap["model_count"] == 2
        assert snap["champion_count"] == 0

    def test_versions(self, registry: ModelRegistry) -> None:
        registry.register("risk_v1", "1.0.0")
        registry.register("risk_v1", "2.0.0")
        versions = registry.get_versions("risk_v1")
        assert len(versions) == 2


# ---------------------------------------------------------------------------
# FeatureStore
# ---------------------------------------------------------------------------


class TestFeatureStore:
    def test_set_get(self, store: FeatureStore) -> None:
        store.set("A", "risk_score", 0.85)
        rec = store.get("A", "risk_score")
        assert rec is not None and rec.value == 0.85

    def test_get_all(self, store: FeatureStore) -> None:
        store.set("A", "risk_score", 0.85)
        store.set("A", "influence", 0.5)
        assert len(store.get_all("A")) == 2

    def test_invalidate(self, store: FeatureStore) -> None:
        store.set("A", "risk_score", 0.85)
        store.invalidate("A", "risk_score")
        assert store.get_fresh("A", "risk_score") is None

    def test_ttl_expiry(self, store: FeatureStore) -> None:
        store.set("A", "risk_score", 0.85, ttl=0)
        time.sleep(0.01)
        assert store.get_fresh("A", "risk_score") is None

    def test_freshness_score(self, store: FeatureStore) -> None:
        store.set("A", "risk_score", 0.85)
        rec = store.get("A", "risk_score")
        assert rec is not None and 0.0 <= rec.freshness_score() <= 1.0

    def test_data_quality(self, store: FeatureStore) -> None:
        store.set("A", "risk_score", 0.85)
        assert 0.0 < store.data_quality_score("A") <= 1.0

    def test_data_quality_empty(self, store: FeatureStore) -> None:
        assert store.data_quality_score("Z") == 0.0

    def test_detect_stale(self, store: FeatureStore) -> None:
        store.set("A", "fresh_f", 0.5)
        store.set("A", "stale_f", 0.5, ttl=0)
        time.sleep(0.01)
        assert store.detect_stale("A") == ["stale_f"]

    def test_integrity(self, store: FeatureStore) -> None:
        store.set("A", "risk_score", 0.85)
        h = store.integrity_hash("A", "risk_score")
        assert len(h) == 16

    def test_drift(self, store: FeatureStore) -> None:
        store.set("A", "risk_score", 0.5)
        # single record: no drift detectable
        assert store.detect_drift("A", "risk_score") == 0.0
        # second record creates drift
        store.set("A", "risk_score", 1.0)
        drift = store.detect_drift("A", "risk_score")
        assert drift > 0.0
        store.set("A", "risk_score", 0.5)
        drift = store.detect_drift("A", "risk_score")
        assert drift > 0.0


# ---------------------------------------------------------------------------
# CrossSystemConsistency
# ---------------------------------------------------------------------------


class TestCrossSystemConsistency:
    def test_perfect_coherence(self) -> None:
        csc = CrossSystemConsistency()
        s = csc.coherence_score(
            {"scores": {"A": 0.9}},
            {"root_causes": [{"root_cause_node": "A", "confidence": 0.8}]},
            {"predictions": [{"value": 0.5}]},
        )
        assert s > 0.8

    def test_low_coherence(self) -> None:
        csc = CrossSystemConsistency()
        s = csc.coherence_score(
            {"scores": {"A": 0.9, "B": 0.9, "C": 0.9}},
            {"root_causes": [{"root_cause_node": "Z", "confidence": 0.8}]},
            {"predictions": [{"value": 0.5}]},
        )
        assert s < 1.0

    def test_no_conflicts(self) -> None:
        csc = CrossSystemConsistency()
        cs = csc.detect_conflicts(
            {"scores": {"A": 0.9}},
            {"root_causes": [{"root_cause_node": "A", "confidence": 0.8}]},
            {"predictions": [{"value": 0.3}]},
        )
        assert len(cs) == 0

    def test_anomaly_causal_mismatch(self) -> None:
        csc = CrossSystemConsistency()
        cs = csc.detect_conflicts(
            {"scores": {"A": 0.9, "B": 0.9, "C": 0.9, "D": 0.9, "E": 0.9}},
            {"root_causes": [{"root_cause_node": "Z"}]},
            {"predictions": [{"value": 0.3}]},
        )
        assert any(c["type"] == "anomaly_causal_mismatch" for c in cs)

    def test_prediction_anomaly_divergence(self) -> None:
        csc = CrossSystemConsistency()
        cs = csc.detect_conflicts({"scores": {"A": 0.1}}, {}, {"predictions": [{"value": 0.9}]})
        assert any(c["type"] == "prediction_anomaly_divergence" for c in cs)

    def test_all_none(self) -> None:
        csc = CrossSystemConsistency()
        assert csc.coherence_score(None, None, None) == 1.0
        assert csc.detect_conflicts(None, None, None) == []


# ---------------------------------------------------------------------------
# KernelTrace
# ---------------------------------------------------------------------------


class TestKernelTrace:
    def test_create(self) -> None:
        t = KernelTrace(
            trace_id="kt1",
            graph_version="gv1",
            execution_mode="det",
            phases={},
            coherence_score=0.9,
            started_at=100.0,
        )
        assert t.trace_id == "kt1"

    def test_to_dict(self) -> None:
        t = KernelTrace(
            trace_id="kt1",
            graph_version="gv1",
            execution_mode="det",
            phases={},
            coherence_score=0.9,
            started_at=100.0,
        )
        d = t.to_dict()
        assert d["schema_version"] == "1.0"
        assert d["coherence_score"] == 0.9


# ---------------------------------------------------------------------------
# UnifiedExecutionKernel
# ---------------------------------------------------------------------------


class TestKernel:
    def test_execute_basic(self, kernel: UnifiedExecutionKernel) -> None:
        r = kernel.execute("A")
        assert (
            "trace" in r
            and "anomaly" in r
            and "causal" in r
            and "prediction" in r
            and "coherence" in r
            and "execution_time_ms" in r
        )

    def test_execute_deterministic(self, kernel: UnifiedExecutionKernel) -> None:
        r1 = kernel.execute("A")
        r2 = kernel.execute("A")
        a1 = {k: v for k, v in r1["anomaly"].items() if k != "execution_time_ms"}
        a2 = {k: v for k, v in r2["anomaly"].items() if k != "execution_time_ms"}
        assert a1 == a2

    def test_anomaly_only(self, kernel: UnifiedExecutionKernel) -> None:
        r = kernel.execute("A", enable_causal=False, enable_prediction=False)
        assert r["anomaly"] is not None
        assert r["causal"] is None
        assert r["prediction"] is None

    def test_causal_only(self, kernel: UnifiedExecutionKernel) -> None:
        r = kernel.execute("A", enable_anomaly=False, enable_prediction=False)
        assert r["anomaly"] is None
        assert r["prediction"] is None

    def test_prediction_only(self, kernel: UnifiedExecutionKernel) -> None:
        r = kernel.execute(enable_anomaly=False, enable_causal=False)
        assert r["anomaly"] is None
        assert r["causal"] is None
        assert r["prediction"] is not None

    def test_no_anomaly_node(self, kernel: UnifiedExecutionKernel) -> None:
        r = kernel.execute()
        assert r["causal"] is None
        assert r["anomaly"] is not None

    def test_unknown_node(self, kernel: UnifiedExecutionKernel) -> None:
        r = kernel.execute("ZZZ")
        assert r["causal"]["found"] is False

    def test_coherence(self, kernel: UnifiedExecutionKernel) -> None:
        c = kernel.execute("A")["coherence"]
        assert "score" in c and "conflicts" in c and "cross_phase_consistent" in c
        assert 0.0 <= c["score"] <= 1.0

    def test_fingerprint(self, kernel: UnifiedExecutionKernel) -> None:
        assert len(kernel.execute("A")["trace"]["execution_fingerprint"]) == 16

    def test_graph_version(self, kernel: UnifiedExecutionKernel) -> None:
        assert len(kernel.execute("A")["trace"]["graph_version"]) == 16

    def test_empty_graph(self) -> None:
        k = UnifiedExecutionKernel(IntelligenceGraph())
        r = k.execute()
        assert r["trace"] is not None

    def test_no_edges_graph(self) -> None:
        g = IntelligenceGraph()
        g.nodes["A"] = Node(entity=_make_entity("A"))
        g.nodes["B"] = Node(entity=_make_entity("B"))
        k = UnifiedExecutionKernel(g)
        assert k.execute("A")["anomaly"] is not None
