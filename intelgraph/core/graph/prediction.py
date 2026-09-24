from __future__ import annotations

import hashlib
import math
import random
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from intelgraph.core.enterprise.observability import get_metrics
from intelgraph.core.graph.graph import IntelligenceGraph

PREDICTION_SCHEMA_VERSION = "1.0"


class ForecastHorizon(Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class ExecutionMode(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    HYBRID = "hybrid"
    STREAMING = "streaming"
    SPECULATIVE = "speculative"
    FAILOVER = "failover"


@dataclass
class PredictionResult:
    prediction_id: str
    entity_id: str
    prediction_type: str
    value: float
    confidence: float
    horizon: str
    features: dict[str, float] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    uncertainty: float = 0.0
    model_id: str = ""
    trace_id: str = ""
    execution_mode: str = "online"
    schema_version: str = PREDICTION_SCHEMA_VERSION
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "entity_id": self.entity_id,
            "prediction_type": self.prediction_type,
            "value": round(self.value, 6),
            "confidence": round(self.confidence, 4),
            "horizon": self.horizon,
            "features": self.features,
            "contributions": {k: round(v, 4) for k, v in self.contributions.items()},
            "uncertainty": round(self.uncertainty, 4),
            "model_id": self.model_id,
            "trace_id": self.trace_id,
            "execution_mode": self.execution_mode,
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
        }


class Predictor:
    def __init__(
        self,
        graph: IntelligenceGraph,
        config: dict[str, Any] | None = None,
        weight_fn: Callable[[Any], float] | None = None,
        deterministic: bool = True,
        anomaly_scores: dict[str, float] | None = None,
        influence_scores: dict[str, float] | None = None,
    ) -> None:
        self._graph = graph
        self._config = config or {}
        self._weight_fn = weight_fn or (lambda e: 1.0)
        self._deterministic = deterministic
        self._anomaly_scores = anomaly_scores or {}
        self._influence_scores = influence_scores or {}
        self._metrics = get_metrics()
        self._graph_version = self._compute_graph_version()
        self._seed = 42 if deterministic else None
        self._rng = random.Random(self._seed) if deterministic else random.Random()

    def _compute_graph_version(self) -> str:
        node_ids = sorted(self._graph.nodes.keys())
        edge_ids = sorted(self._graph.edges.keys())
        raw = "|".join(node_ids) + "||" + "|".join(edge_ids)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _generate_id(self) -> str:
        return f"pred_{uuid.uuid4().hex[:12]}"

    def _record_duration(self, name: str, duration_ns: int) -> None:
        self._metrics.set_gauge(f"prediction_{name}_duration_ms", duration_ns / 1_000_000)
        self._metrics.set_gauge(f"prediction_{name}_graph_nodes", float(self._graph.node_count))
        self._metrics.set_gauge(f"prediction_{name}_graph_edges", float(self._graph.edge_count))

    def _node_degree(self, nid: str) -> int:
        return len(self._graph.adjacency.get(nid, set()))

    def _compute_features(self, nid: str) -> dict[str, float]:
        deg = self._node_degree(nid)
        infl = self._influence_scores.get(nid, 0.0)
        anom = self._anomaly_scores.get(nid, 0.0)
        conf = 50.0
        trust = 50.0
        node = self._graph.nodes.get(nid)
        if node:
            conf = float(getattr(node.entity, "confidence_score", 50))
            trust = float(getattr(node.entity, "trust_score", 50))
        return {
            "degree": float(deg),
            "influence": infl,
            "anomaly_score": anom,
            "confidence": conf / 100.0,
            "trust": trust / 100.0,
        }

    def _forecast_holtwinters(
        self, values: list[float], horizon: int, alpha: float = 0.3, beta: float = 0.1
    ) -> list[float]:
        if not values:
            return []
        n = len(values)
        level = values[0]
        trend = values[-1] - values[0] / max(n, 1) if n > 1 else 0.0
        result: list[float] = []
        for _ in range(horizon):
            forecast = level + trend
            result.append(forecast)
            level = alpha * (forecast) + (1 - alpha) * level
            trend = beta * (level - forecast) + (1 - beta) * trend
        return result

    def risk_forecast(self, node_id: str, horizon: int = 3) -> PredictionResult:
        t0 = time.perf_counter_ns()
        features = self._compute_features(node_id)
        infl = features["influence"]
        anom = features["anomaly_score"]
        deg = features["degree"]
        base_risk = (
            0.4 * min(infl * 2, 1.0)
            + 0.3 * anom
            + 0.2 * min(deg / 100.0, 1.0)
            + 0.1 * features["confidence"]
        )
        horizons = [ForecastHorizon.SHORT, ForecastHorizon.MEDIUM, ForecastHorizon.LONG]
        decay = {0: 1.0, 1: 0.85, 2: 0.7}
        horizon_idx = min(horizon, 2)
        forecast_val = base_risk * decay.get(horizon_idx, 0.7)
        confidence = max(0.3, 1.0 - 0.2 * horizon_idx - features["anomaly_score"] * 0.1)
        uncertainty = min(0.1 + 0.15 * horizon_idx, 0.5)
        pred = PredictionResult(
            prediction_id=self._generate_id(),
            entity_id=node_id,
            prediction_type="risk_forecast",
            value=min(forecast_val, 1.0),
            confidence=confidence,
            horizon=horizons[horizon_idx].value,
            features=features,
            contributions={"influence": 0.4, "anomaly": 0.3, "degree": 0.2, "confidence": 0.1},
            uncertainty=uncertainty,
            execution_mode="online",
            timestamp=time.time(),
        )
        duration = time.perf_counter_ns() - t0
        self._record_duration("risk_forecast", duration)
        self._metrics.set_gauge("prediction_risk_forecast_duration_ms", duration / 1_000_000)
        return pred

    def temporal_trend(self, node_id: str, horizon: int = 3) -> PredictionResult:
        t0 = time.perf_counter_ns()
        features = self._compute_features(node_id)
        values = [features["degree"], features["influence"], features["anomaly_score"]]
        forecasted = self._forecast_holtwinters(values, horizon)
        trend_val = forecasted[-1] if forecasted else 0.0
        horizons = [ForecastHorizon.SHORT, ForecastHorizon.MEDIUM, ForecastHorizon.LONG]
        horizon_idx = min(horizon, 2)
        trend_conf = max(0.2, 1.0 - 0.25 * horizon_idx)
        uncertainty = min(0.1 + 0.2 * horizon_idx, 0.6)
        pred = PredictionResult(
            prediction_id=self._generate_id(),
            entity_id=node_id,
            prediction_type="temporal_trend",
            value=min(trend_val, 1.0),
            confidence=trend_conf,
            horizon=horizons[horizon_idx].value,
            features=features,
            contributions={"trend": 0.6, "seasonal": 0.2, "residual": 0.2},
            uncertainty=uncertainty,
            execution_mode="online",
            timestamp=time.time(),
        )
        duration = time.perf_counter_ns() - t0
        self._record_duration("temporal_trend", duration)
        return pred

    def influence_trajectory(self, node_id: str, horizon: int = 3) -> PredictionResult:
        t0 = time.perf_counter_ns()
        features = self._compute_features(node_id)
        current_infl = features["influence"]
        deg = features["degree"]
        trajectory = current_infl * (1.0 + 0.1 * math.log2(max(deg, 1)))
        horizons = [ForecastHorizon.SHORT, ForecastHorizon.MEDIUM, ForecastHorizon.LONG]
        horizon_idx = min(horizon, 2)
        decay = {0: 1.0, 1: 0.9, 2: 0.75}
        forecast_val = trajectory * decay.get(horizon_idx, 0.75)
        confidence = max(0.2, 1.0 - 0.15 * horizon_idx)
        uncertainty = min(0.1 + 0.15 * horizon_idx, 0.5)
        pred = PredictionResult(
            prediction_id=self._generate_id(),
            entity_id=node_id,
            prediction_type="influence_trajectory",
            value=min(forecast_val, 1.0),
            confidence=confidence,
            horizon=horizons[horizon_idx].value,
            features=features,
            contributions={"current_influence": 0.5, "degree_growth": 0.3, "decay": 0.2},
            uncertainty=uncertainty,
            execution_mode="online",
            timestamp=time.time(),
        )
        duration = time.perf_counter_ns() - t0
        self._record_duration("influence_trajectory", duration)
        return pred

    def anomaly_likelihood(self, node_id: str, horizon: int = 3) -> PredictionResult:
        t0 = time.perf_counter_ns()
        features = self._compute_features(node_id)
        current_anom = features["anomaly_score"]
        infl = features["influence"]
        base_likelihood = current_anom * 0.5 + infl * 0.3 + (1.0 - features["trust"]) * 0.2
        horizons = [ForecastHorizon.SHORT, ForecastHorizon.MEDIUM, ForecastHorizon.LONG]
        horizon_idx = min(horizon, 2)
        decay = {0: 1.0, 1: 0.8, 2: 0.6}
        forecast_val = base_likelihood * decay.get(horizon_idx, 0.6)
        confidence = max(0.15, 1.0 - 0.3 * horizon_idx - current_anom * 0.1)
        uncertainty = min(0.15 + 0.2 * horizon_idx, 0.6)
        pred = PredictionResult(
            prediction_id=self._generate_id(),
            entity_id=node_id,
            prediction_type="anomaly_likelihood",
            value=min(forecast_val, 1.0),
            confidence=confidence,
            horizon=horizons[horizon_idx].value,
            features=features,
            contributions={"current_anomaly": 0.5, "influence": 0.3, "trust_decay": 0.2},
            uncertainty=uncertainty,
            execution_mode="online",
            timestamp=time.time(),
        )
        duration = time.perf_counter_ns() - t0
        self._record_duration("anomaly_likelihood", duration)
        return pred

    def attack_path_probability(self, node_id: str, horizon: int = 3) -> PredictionResult:
        t0 = time.perf_counter_ns()
        features = self._compute_features(node_id)
        out_edges = len(self._graph.forward_adjacency.get(node_id, set()))
        in_edges = len(self._graph.reverse_adjacency.get(node_id, set()))
        connectivity = (out_edges + in_edges) / max(self._graph.node_count, 1)
        base_prob = (
            0.3 * connectivity
            + 0.3 * features["influence"]
            + 0.2 * features["anomaly_score"]
            + 0.1 * (1.0 - features["trust"])
            + 0.1 * features["confidence"]
        )
        horizons = [ForecastHorizon.SHORT, ForecastHorizon.MEDIUM, ForecastHorizon.LONG]
        horizon_idx = min(horizon, 2)
        growth = {0: 1.0, 1: 1.1, 2: 1.2}
        forecast_val = base_prob * growth.get(horizon_idx, 1.0)
        confidence = max(0.2, 1.0 - 0.2 * horizon_idx)
        uncertainty = min(0.1 + 0.2 * horizon_idx, 0.5)
        pred = PredictionResult(
            prediction_id=self._generate_id(),
            entity_id=node_id,
            prediction_type="attack_path_probability",
            value=min(forecast_val, 1.0),
            confidence=confidence,
            horizon=horizons[horizon_idx].value,
            features={
                **features,
                "connectivity": connectivity,
                "out_edges": float(out_edges),
                "in_edges": float(in_edges),
            },
            contributions={
                "connectivity": 0.3,
                "influence": 0.3,
                "anomaly": 0.2,
                "trust_decay": 0.1,
                "confidence": 0.1,
            },
            uncertainty=uncertainty,
            execution_mode="online",
            timestamp=time.time(),
        )
        duration = time.perf_counter_ns() - t0
        self._record_duration("attack_path_probability", duration)
        return pred

    def community_evolution(
        self, node_id: str, communities: dict[str, list[str]] | None = None, horizon: int = 3
    ) -> PredictionResult:
        t0 = time.perf_counter_ns()
        features = self._compute_features(node_id)
        community_id = "default"
        if communities:
            for cid, members in communities.items():
                if node_id in members:
                    community_id = cid
                    break
        community_size = len(communities.get(community_id, [])) if communities else 0
        growth_rate = features["degree"] / max(community_size, 1) if community_size > 0 else 0.0
        horizons = [ForecastHorizon.SHORT, ForecastHorizon.MEDIUM, ForecastHorizon.LONG]
        horizon_idx = min(horizon, 2)
        growth_factor = {0: 1.0, 1: 1.0 + growth_rate, 2: 1.0 + 2 * growth_rate}
        pred_size = community_size * growth_factor.get(horizon_idx, 1.0)
        confidence = max(0.2, 1.0 - 0.15 * horizon_idx - features["anomaly_score"] * 0.05)
        uncertainty = min(0.1 + 0.2 * horizon_idx, 0.6)
        pred = PredictionResult(
            prediction_id=self._generate_id(),
            entity_id=node_id,
            prediction_type="community_evolution",
            value=min(pred_size / max(community_size + 1, 1), 2.0),
            confidence=confidence,
            horizon=horizons[horizon_idx].value,
            features={
                **features,
                "community_size": float(community_size),
                "growth_rate": growth_rate,
            },
            contributions={
                "community_size": 0.4,
                "degree": 0.3,
                "growth_rate": 0.2,
                "anomaly": 0.1,
            },
            uncertainty=uncertainty,
            execution_mode="online",
            timestamp=time.time(),
        )
        duration = time.perf_counter_ns() - t0
        self._record_duration("community_evolution", duration)
        return pred

    def multi_horizon_forecast(self, node_id: str) -> list[PredictionResult]:
        results: list[PredictionResult] = []
        for h in range(3):
            results.append(self.risk_forecast(node_id, h))
            results.append(self.temporal_trend(node_id, h))
            results.append(self.influence_trajectory(node_id, h))
            results.append(self.anomaly_likelihood(node_id, h))
            results.append(self.attack_path_probability(node_id, h))
        return results

    def ensemble_score(
        self, predictions: list[PredictionResult], weights: list[float] | None = None
    ) -> PredictionResult:
        if not predictions:
            return PredictionResult(
                prediction_id=self._generate_id(),
                entity_id="",
                prediction_type="ensemble",
                value=0.0,
                confidence=0.0,
                horizon="short",
                execution_mode="online",
                timestamp=time.time(),
            )
        w = weights or [1.0 / len(predictions)] * len(predictions)
        w_sum = sum(w)
        norm_w = [ww / w_sum for ww in w]
        ensemble_val = sum(p.value * nw for p, nw in zip(predictions, norm_w, strict=False))
        ensemble_conf = sum(p.confidence * nw for p, nw in zip(predictions, norm_w, strict=False))
        ensemble_unc = sum(p.uncertainty * nw for p, nw in zip(predictions, norm_w, strict=False))
        return PredictionResult(
            prediction_id=self._generate_id(),
            entity_id=predictions[0].entity_id,
            prediction_type="ensemble",
            value=min(ensemble_val, 1.0),
            confidence=ensemble_conf,
            horizon=predictions[0].horizon,
            features={},
            contributions={f"pred_{i}": nw for i, nw in enumerate(norm_w)},
            uncertainty=ensemble_unc,
            execution_mode="online",
            timestamp=time.time(),
        )

    def full_forecast(
        self, node_id: str, communities: dict[str, list[str]] | None = None
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        results = self.multi_horizon_forecast(node_id)
        ensemble = self.ensemble_score(results)
        pred_dicts = [r.to_dict() for r in results]
        duration = time.perf_counter_ns() - t0
        self._record_duration("full_forecast", duration)
        self._metrics.set_gauge("prediction_full_forecast_duration_ms", duration / 1_000_000)
        self._metrics.set_gauge("prediction_full_forecast_count", float(len(results)))
        return {
            "predictions": pred_dicts,
            "ensemble": ensemble.to_dict(),
            "prediction_count": len(results),
            "graph_version": self._graph_version,
            "schema_version": PREDICTION_SCHEMA_VERSION,
            "deterministic": self._deterministic,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def counterfactual(self, node_id: str, what_if: dict[str, float]) -> PredictionResult:
        t0 = time.perf_counter_ns()
        features = self._compute_features(node_id)
        for k, v in what_if.items():
            features[k] = v
        impact = 0.0
        contributions = {}
        for k, v in what_if.items():
            contrib = v * features.get(k, 0.0) * 0.1
            impact += contrib
            contributions[k] = contrib
        base = features.get("anomaly_score", 0.0) + features.get("influence", 0.0)
        cf_val = min(max(base + impact, 0.0), 1.0)
        pred = PredictionResult(
            prediction_id=self._generate_id(),
            entity_id=node_id,
            prediction_type="counterfactual",
            value=cf_val,
            confidence=0.5,
            horizon="short",
            features=features,
            contributions=contributions,
            uncertainty=0.4,
            execution_mode="online",
            timestamp=time.time(),
        )
        duration = time.perf_counter_ns() - t0
        self._record_duration("counterfactual", duration)
        return pred
