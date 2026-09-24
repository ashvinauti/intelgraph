from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from intelgraph.core.enterprise.observability import get_metrics
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node

EXPLANATION_SCHEMA_VERSION = "1.0"


@dataclass
class AnomalyResult:
    node_id: str
    anomaly_type: str
    anomaly_score: float
    explanation: str
    entity_type: str = ""
    entity_identifier: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "anomaly_type": self.anomaly_type,
            "anomaly_score": round(self.anomaly_score, 2),
            "explanation": self.explanation,
            "entity_type": self.entity_type,
            "entity_identifier": self.entity_identifier,
        }


_THREAT_SCORE_CACHE: dict[str, float] = {}  # populated by pipeline, keyed by node_id


class AnomalyBaseline:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._baselines: dict[str, dict[str, Any]] = {}
        self._feature_histories: dict[str, list[dict[str, float]]] = {}

    def _entity_type_key(self, node: Node) -> str:
        return node.entity_type or "unknown"

    def record_snapshot(
        self, features: dict[str, dict[str, float]], timestamp: float | None = None
    ) -> None:
        timestamp or time.time()
        for nid, feats in features.items():
            self._feature_histories.setdefault(nid, []).append(feats)
        retained = self._config.get("baseline_history_size", 100)
        for nid in list(self._feature_histories.keys()):
            if len(self._feature_histories[nid]) > retained:
                self._feature_histories[nid] = self._feature_histories[nid][-retained:]

    def compute_baselines(self, features: dict[str, dict[str, float]]) -> None:
        entity_features: dict[str, list[dict[str, float]]] = {}
        for _nid, feats in features.items():
            n = feats.get("__entity_type", "unknown")
            entity_features.setdefault(n, []).append(
                {k: v for k, v in feats.items() if not k.startswith("__")}
            )
        for etype, feat_list in entity_features.items():
            if not feat_list:
                continue
            baseline: dict[str, dict[str, float]] = {}
            keys = feat_list[0].keys()
            for key in keys:
                values = [f[key] for f in feat_list]
                mean = sum(values) / len(values)
                variance = sum((v - mean) ** 2 for v in values) / max(len(values), 1)
                std = math.sqrt(variance) if variance > 0 else 1e-10
                sorted_vals = sorted(values)
                n = len(sorted_vals)
                q1 = sorted_vals[n // 4] if n > 0 else 0.0
                q3 = sorted_vals[(3 * n) // 4] if n > 0 else 0.0
                baseline[key] = {
                    "mean": mean,
                    "std": std,
                    "min": min(values),
                    "max": max(values),
                    "q1": q1,
                    "q3": q3,
                    "iqr": q3 - q1,
                    "count": len(values),
                }
            self._baselines[etype] = baseline

    def compute_adaptive_threshold(
        self, etype: str, feature: str, multiplier: float = 3.0
    ) -> float:
        bl = self._baselines.get(etype, {})
        feat_bl = bl.get(feature, {})
        mean = feat_bl.get("mean", 0.0)
        std = feat_bl.get("std", 1e-10)
        return mean + multiplier * std

    def get_baseline(self, etype: str, feature: str) -> dict[str, float]:
        return self._baselines.get(etype, {}).get(feature, {})

    def get_all_baselines(self) -> dict[str, dict[str, Any]]:
        return dict(self._baselines)

    def drift_deviation(self, features: dict[str, dict[str, float]]) -> dict[str, float]:
        deviations: dict[str, float] = {}
        for nid, feats in features.items():
            n = feats.get("__entity_type", "unknown")
            bl = self._baselines.get(n, {})
            if not bl:
                continue
            node_dev = 0.0
            count = 0
            for key, val in feats.items():
                if key.startswith("__"):
                    continue
                feat_bl = bl.get(key, {})
                mean = feat_bl.get("mean", 0.0)
                std = feat_bl.get("std", 1e-10)
                if std > 0:
                    z = abs(val - mean) / std
                    node_dev += z
                    count += 1
            deviations[nid] = round(node_dev / max(count, 1), 4)
        return deviations

    def historical_drift(self) -> dict[str, float]:
        drift: dict[str, float] = {}
        for nid, history in self._feature_histories.items():
            if len(history) < 2:
                continue
            recent_5 = history[-5:] if len(history) >= 5 else history
            means: list[float] = []
            for f in recent_5:
                numeric = [
                    v
                    for k, v in f.items()
                    if isinstance(v, (int, float)) and not k.startswith("__")
                ]
                means.append(sum(numeric) / max(len(numeric), 1) if numeric else 0.0)
            drift[nid] = round(max(means) - min(means), 4) if means else 0.0
        return drift


class AnomalyDetector:
    def __init__(
        self,
        graph: IntelligenceGraph,
        config: dict[str, Any] | None = None,
        weight_fn: Callable[[Any], float] | None = None,
        communities: dict[str, list[str]] | None = None,
        baseline: AnomalyBaseline | None = None,
    ) -> None:
        self._graph = graph
        self._config = config or {}
        self._weight_fn = weight_fn or (lambda e: 1.0)
        self._communities = communities or {}
        self._baseline = baseline or AnomalyBaseline(config)
        self._metrics = get_metrics()
        self._graph_version = self._compute_graph_version()

    def _compute_graph_version(self) -> str:
        node_ids = sorted(self._graph.nodes.keys())
        edge_ids = sorted(self._graph.edges.keys())
        combined = "|".join(node_ids) + "||" + "|".join(edge_ids)
        return str(hash(combined))

    def _record_duration(self, name: str, duration_ns: int) -> None:
        self._metrics.set_gauge(f"anomaly_{name}_duration_ms", duration_ns / 1_000_000)
        n = self._graph.node_count
        e = self._graph.edge_count
        self._metrics.set_gauge(f"anomaly_{name}_graph_nodes", float(n))
        self._metrics.set_gauge(f"anomaly_{name}_graph_edges", float(e))

    def _get_edge_weight(self, edge_id: str) -> float:
        edge = self._graph.edges.get(edge_id)
        if edge is None:
            return 1.0
        return self._weight_fn(edge)

    def _compute_features(self) -> dict[str, dict[str, float]]:
        node_ids = sorted(self._graph.nodes.keys())
        features: dict[str, dict[str, float]] = {}
        for nid in node_ids:
            node = self._graph.nodes.get(nid)
            if node is None:
                continue
            deg = len(self._graph.adjacency.get(nid, set()))
            out_deg = len(self._graph.forward_adjacency.get(nid, set()))
            in_deg = len(self._graph.reverse_adjacency.get(nid, set()))
            total_edge_weight = 0.0
            for eid in self._graph.node_edges.get(nid, set()):
                total_edge_weight += self._get_edge_weight(eid)
            entity_type = node.entity_type if hasattr(node, "entity_type") else "unknown"
            confidence = float(getattr(node.entity, "confidence_score", 50))
            trust = float(getattr(node.entity, "trust_score", 50))
            evidence_count = float(len(getattr(node.entity, "evidence", [])))
            features[nid] = {
                "degree": float(deg),
                "out_degree": float(out_deg),
                "in_degree": float(in_deg),
                "total_edge_weight": total_edge_weight,
                "avg_edge_weight": total_edge_weight / max(deg, 1),
                "confidence": confidence,
                "trust": trust,
                "evidence_count": evidence_count,
                "__entity_type": entity_type,
            }
        return features

    def statistical_zscore(
        self, features: dict[str, dict[str, float]] | None = None
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if features is None:
            features = self._compute_features()
        node_ids = sorted(features.keys())
        if not node_ids:
            return {"anomalies": {}, "method": "zscore", "execution_time_ms": 0.0}
        numerical_keys = [k for k in features[node_ids[0]] if not k.startswith("__")]
        global_means: dict[str, float] = {}
        global_stds: dict[str, float] = {}
        for key in numerical_keys:
            values = [features[nid][key] for nid in node_ids]
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            global_means[key] = mean
            global_stds[key] = math.sqrt(variance) if variance > 0 else 1e-10
        anomalies: dict[str, list[dict[str, Any]]] = {}
        for nid in node_ids:
            node_anomalies: list[dict[str, Any]] = []
            for key in numerical_keys:
                val = features[nid][key]
                mean = global_means[key]
                std = global_stds[key]
                z = (val - mean) / std
                threshold = self._config.get("zscore_threshold", 3.0)
                if abs(z) > threshold:
                    node_anomalies.append(
                        {
                            "feature": key,
                            "value": round(val, 4),
                            "mean": round(mean, 4),
                            "std": round(std, 4),
                            "zscore": round(z, 4),
                            "severity": "high" if abs(z) > threshold * 1.5 else "medium",
                        }
                    )
            if node_anomalies:
                anomalies[nid] = node_anomalies
        duration = time.perf_counter_ns() - t0
        self._record_duration("zscore", duration)
        return {
            "anomalies": anomalies,
            "anomaly_count": sum(len(v) for v in anomalies.values()),
            "node_count": len(anomalies),
            "method": "zscore",
            "threshold": self._config.get("zscore_threshold", 3.0),
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def statistical_iqr(
        self, features: dict[str, dict[str, float]] | None = None
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if features is None:
            features = self._compute_features()
        node_ids = sorted(features.keys())
        if not node_ids:
            return {"anomalies": {}, "method": "iqr", "execution_time_ms": 0.0}
        numerical_keys = [k for k in features[node_ids[0]] if not k.startswith("__")]
        global_stats: dict[str, dict[str, float]] = {}
        for key in numerical_keys:
            values = sorted([features[nid][key] for nid in node_ids])
            n = len(values)
            q1 = values[n // 4]
            q3 = values[(3 * n) // 4]
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            global_stats[key] = {"q1": q1, "q3": q3, "iqr": iqr, "lower": lower, "upper": upper}
        anomalies: dict[str, list[dict[str, Any]]] = {}
        for nid in node_ids:
            node_anomalies: list[dict[str, Any]] = []
            for key in numerical_keys:
                val = features[nid][key]
                stats = global_stats[key]
                if val < stats["lower"] or val > stats["upper"]:
                    direction = "high" if val > stats["upper"] else "low"
                    distance = max(abs(val - stats["upper"]), abs(val - stats["lower"])) / max(
                        stats["iqr"], 1e-10
                    )
                    node_anomalies.append(
                        {
                            "feature": key,
                            "value": round(val, 4),
                            "q1": round(stats["q1"], 4),
                            "q3": round(stats["q3"], 4),
                            "iqr": round(stats["iqr"], 4),
                            "lower_fence": round(stats["lower"], 4),
                            "upper_fence": round(stats["upper"], 4),
                            "direction": direction,
                            "severity": "high" if distance > 3.0 else "medium",
                        }
                    )
            if node_anomalies:
                anomalies[nid] = node_anomalies
        duration = time.perf_counter_ns() - t0
        self._record_duration("iqr", duration)
        return {
            "anomalies": anomalies,
            "anomaly_count": sum(len(v) for v in anomalies.values()),
            "node_count": len(anomalies),
            "method": "iqr",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def graph_degree_outliers(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = sorted(self._graph.nodes.keys())
        if not node_ids:
            return {"anomalies": {}, "method": "degree_outlier", "execution_time_ms": 0.0}
        degrees = [(nid, len(self._graph.adjacency.get(nid, set()))) for nid in node_ids]
        deg_values = sorted([d for _, d in degrees])
        n = len(deg_values)
        q1 = deg_values[n // 4]
        q3 = deg_values[(3 * n) // 4]
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        mean_deg = sum(deg_values) / len(deg_values)
        std_deg = (
            math.sqrt(sum((d - mean_deg) ** 2 for d in deg_values) / len(deg_values))
            if deg_values
            else 1e-10
        )
        anomalies: dict[str, list[dict[str, Any]]] = {}
        for nid, deg in degrees:
            z = (deg - mean_deg) / std_deg if std_deg > 0 else 0.0
            node_anomalies: list[dict[str, Any]] = []
            if deg < lower or deg > upper:
                direction = "high_degree" if deg > upper else "low_degree"
                node_anomalies.append(
                    {
                        "feature": "degree",
                        "value": deg,
                        "mean": round(mean_deg, 2),
                        "std": round(std_deg, 2),
                        "zscore": round(z, 4),
                        "lower_fence": round(lower, 2),
                        "upper_fence": round(upper, 2),
                        "direction": direction,
                        "severity": "high" if abs(z) > 4.0 else "medium",
                    }
                )
                anomalies[nid] = node_anomalies
        duration = time.perf_counter_ns() - t0
        self._record_duration("degree_outliers", duration)
        return {
            "anomalies": anomalies,
            "anomaly_count": sum(len(v) for v in anomalies.values()),
            "node_count": len(anomalies),
            "method": "degree_outlier",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def temporal_deviation(
        self,
        features: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if features is None:
            features = self._compute_features()
        node_ids = sorted(features.keys())
        if not node_ids:
            return {"anomalies": {}, "method": "temporal", "execution_time_ms": 0.0}
        drift = self._baseline.drift_deviation(features)
        historical_drift = self._baseline.historical_drift()
        threshold = self._config.get("temporal_deviation_threshold", 2.0)
        anomalies: dict[str, list[dict[str, Any]]] = {}
        for nid in node_ids:
            node_anomalies: list[dict[str, Any]] = []
            deviation = drift.get(nid, 0.0)
            if deviation > threshold:
                node_anomalies.append(
                    {
                        "feature": "baseline_deviation",
                        "value": round(deviation, 4),
                        "threshold": threshold,
                        "severity": "high" if deviation > threshold * 1.5 else "medium",
                    }
                )
            hist_drift = historical_drift.get(nid, 0.0)
            if hist_drift > threshold:
                node_anomalies.append(
                    {
                        "feature": "historical_drift",
                        "value": round(hist_drift, 4),
                        "threshold": threshold,
                        "severity": "high" if hist_drift > threshold * 1.5 else "medium",
                    }
                )
            if node_anomalies:
                anomalies[nid] = node_anomalies
        duration = time.perf_counter_ns() - t0
        self._record_duration("temporal", duration)
        return {
            "anomalies": anomalies,
            "anomaly_count": sum(len(v) for v in anomalies.values()),
            "node_count": len(anomalies),
            "method": "temporal",
            "threshold": threshold,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def community_anomaly(
        self,
        communities: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        node_ids = sorted(self._graph.nodes.keys())
        if not node_ids:
            return {"anomalies": {}, "method": "community", "execution_time_ms": 0.0}
        communities = communities or self._communities
        if not communities:
            node_to_community: dict[str, str] = {}
            visited: set[str] = set()
            community_id = 0
            for nid in node_ids:
                if nid in visited:
                    continue
                queue: deque[str] = deque([nid])
                visited.add(nid)
                member_ids: list[str] = []
                while queue:
                    cur = queue.popleft()
                    member_ids.append(cur)
                    for neighbor in self._graph.adjacency.get(cur, set()):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                cid_str = f"component_{community_id}"
                for m in member_ids:
                    node_to_community[m] = cid_str
                community_id += 1
            communities = {}
            for nid, cid in node_to_community.items():
                communities.setdefault(cid, []).append(nid)
        community_stats: dict[str, dict[str, float]] = {}
        for cid, members in communities.items():
            member_degrees = [
                len(self._graph.adjacency.get(m, set())) for m in members if m in self._graph.nodes
            ]
            if not member_degrees:
                continue
            community_stats[cid] = {
                "mean_degree": sum(member_degrees) / len(member_degrees),
                "max_degree": max(member_degrees),
                "min_degree": min(member_degrees),
                "size": len(members),
            }
        anomalies: dict[str, list[dict[str, Any]]] = {}
        for cid, members in communities.items():
            stats = community_stats.get(cid)
            if not stats:
                continue
            for member in members:
                if member not in self._graph.nodes:
                    continue
                deg = len(self._graph.adjacency.get(member, set()))
                self._graph.nodes.get(member)
                node_anomalies: list[dict[str, Any]] = []
                mean_deg = stats["mean_degree"]
                std_deg = (
                    math.sqrt(
                        sum(
                            (len(self._graph.adjacency.get(m, set())) - mean_deg) ** 2
                            for m in members
                            if m in self._graph.nodes
                        )
                        / max(len(members), 1)
                    )
                    if len(members) > 1
                    else 1e-10
                )
                z = (deg - mean_deg) / std_deg if std_deg > 0 else 0.0
                threshold = self._config.get("community_zscore_threshold", 2.5)
                if abs(z) > threshold:
                    direction = "high_degree_for_community" if z > 0 else "low_degree_for_community"
                    node_anomalies.append(
                        {
                            "feature": "community_degree_deviation",
                            "value": deg,
                            "community_mean": round(mean_deg, 2),
                            "community_std": round(std_deg, 2),
                            "zscore": round(z, 4),
                            "community_id": cid,
                            "community_size": stats["size"],
                            "direction": direction,
                            "severity": "high" if abs(z) > threshold * 1.5 else "medium",
                        }
                    )
                if node_anomalies:
                    anomalies[member] = node_anomalies
        duration = time.perf_counter_ns() - t0
        self._record_duration("community", duration)
        return {
            "anomalies": anomalies,
            "anomaly_count": sum(len(v) for v in anomalies.values()),
            "node_count": len(anomalies),
            "method": "community",
            "community_count": len(communities),
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def _compute_influence_scores_snapshot(self) -> dict[str, float]:
        from intelgraph.core.graph.influence import InfluencePropagation

        infl = InfluencePropagation(self._graph, weight_fn=self._weight_fn)
        result = infl.influence_scores()
        return result.get("scores", {})

    def multi_factor_score(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        features = self._compute_features()
        node_ids = sorted(features.keys())
        if not node_ids:
            return {"scores": {}, "method": "multi_factor", "execution_time_ms": 0.0}
        zscore_result = self.statistical_zscore(features)
        iqr_result = self.statistical_iqr(features)
        degree_result = self.graph_degree_outliers()
        temporal_result = self.temporal_deviation(features)
        community_result = self.community_anomaly()
        influence_scores = self._compute_influence_scores_snapshot()
        entity_type_signals: dict[str, dict[str, float]] = {}
        for nid in node_ids:
            features[nid].get("__entity_type", "unknown")
            is_anomalous_z = nid in zscore_result["anomalies"]
            is_anomalous_iqr = nid in iqr_result["anomalies"]
            is_anomalous_deg = nid in degree_result["anomalies"]
            is_anomalous_temp = nid in temporal_result["anomalies"]
            is_anomalous_comm = nid in community_result["anomalies"]
            zscore_intensity = sum(
                abs(a.get("zscore", 0.0)) for a in zscore_result["anomalies"].get(nid, [])
            ) / max(len(zscore_result["anomalies"].get(nid, [])), 1)
            iqr_intensity = len(iqr_result["anomalies"].get(nid, []))
            deg_intensity = sum(
                abs(a.get("zscore", 0.0)) for a in degree_result["anomalies"].get(nid, [])
            ) / max(len(degree_result["anomalies"].get(nid, [])), 1)
            temp_intensity = len(temporal_result["anomalies"].get(nid, []))
            comm_intensity = len(community_result["anomalies"].get(nid, []))
            influence_score = influence_scores.get(nid, 0.0)
            signal_count = sum(
                [
                    is_anomalous_z,
                    is_anomalous_iqr,
                    is_anomalous_deg,
                    is_anomalous_temp,
                    is_anomalous_comm,
                ]
            )
            raw = (
                float(is_anomalous_z) * 0.20
                + float(is_anomalous_iqr) * 0.15
                + float(is_anomalous_deg) * 0.20
                + float(is_anomalous_temp) * 0.15
                + float(is_anomalous_comm) * 0.15
                + min(influence_score, 1.0) * 0.15
            )
            score = min(raw * (1.0 + 0.3 * math.log2(max(signal_count, 1))), 1.0)
            entity_type_signals[nid] = {
                "zscore": float(is_anomalous_z),
                "zscore_intensity": zscore_intensity,
                "iqr": float(is_anomalous_iqr),
                "iqr_intensity": float(iqr_intensity),
                "degree_outlier": float(is_anomalous_deg),
                "degree_intensity": deg_intensity,
                "temporal": float(is_anomalous_temp),
                "temporal_intensity": float(temp_intensity),
                "community": float(is_anomalous_comm),
                "community_intensity": float(comm_intensity),
                "influence_score": influence_score,
            }
        scores: dict[str, float] = {}
        for nid in node_ids:
            signals = entity_type_signals[nid]
            raw_score = 0.0
            raw_score += signals["zscore"] * 0.20
            raw_score += signals["iqr"] * 0.15
            raw_score += signals["degree_outlier"] * 0.20
            raw_score += signals["temporal"] * 0.15
            raw_score += signals["community"] * 0.15
            raw_score += min(signals["influence_score"], 1.0) * 0.15
            signal_count = sum(
                [
                    signals["zscore"],
                    signals["iqr"],
                    signals["degree_outlier"],
                    signals["temporal"],
                    signals["community"],
                ]
            )
            score = min(raw_score * (1.0 + 0.3 * math.log2(max(signal_count, 1))), 1.0)
            scores[nid] = round(score, 6)
        scores_sorted = dict(sorted(scores.items(), key=lambda x: -x[1]))
        self._baseline.record_snapshot(features)
        self._baseline.compute_baselines(features)
        duration = time.perf_counter_ns() - t0
        self._record_duration("multi_factor", duration)
        self._metrics.set_gauge("anomaly_multi_factor_duration_ms", duration / 1_000_000)
        self._metrics.set_gauge("anomaly_node_count", float(len(scores)))
        self._metrics.set_gauge(
            "anomaly_high_count", float(sum(1 for v in scores.values() if v > 0.7))
        )
        self._metrics.set_gauge(
            "anomaly_medium_count", float(sum(1 for v in scores.values() if 0.4 < v <= 0.7))
        )
        self._metrics.set_gauge("anomaly_mean_score", sum(scores.values()) / max(len(scores), 1))
        return {
            "scores": scores_sorted,
            "signals": entity_type_signals,
            "method": "multi_factor",
            "weights": {
                "zscore": 0.20,
                "iqr": 0.15,
                "degree_outlier": 0.20,
                "temporal": 0.15,
                "community": 0.15,
                "influence": 0.15,
            },
            "graph_version": self._graph_version,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def feature_contributions(self, node_id: str) -> dict[str, float]:
        features = self._compute_features()
        if node_id not in features:
            return {}
        entity_type = features[node_id].get("__entity_type", "unknown")
        feats = {k: v for k, v in features[node_id].items() if not k.startswith("__")}
        contributions: dict[str, float] = {}
        for key, val in feats.items():
            bl = self._baseline.get_baseline(entity_type, key)
            mean = bl.get("mean", 0.0)
            std = bl.get("std", 1e-10)
            if std > 0:
                z = abs(val - mean) / std
                contributions[key] = round(min(z / 10.0, 1.0), 4)
            else:
                contributions[key] = 0.0
        total = sum(contributions.values()) or 1.0
        return {k: round(v / total, 4) for k, v in contributions.items()}

    def confidence_score(self, node_id: str) -> float:
        features = self._compute_features()
        if node_id not in features:
            return 0.0
        entity_type = features[node_id].get("__entity_type", "unknown")
        bl_count = len(self._baseline.get_all_baselines().get(entity_type, {}))
        if bl_count == 0:
            return 0.5
        deg = len(self._graph.adjacency.get(node_id, set()))
        total_nodes = max(self._graph.node_count, 1)
        evidence_count = features[node_id].get("evidence_count", 0.0)
        evidence_factor = min(evidence_count / 10.0, 1.0)
        degree_factor = min(deg / total_nodes * 10, 1.0)
        baseline_factor = min(bl_count / 5.0, 1.0)
        confidence = 0.4 * evidence_factor + 0.3 * degree_factor + 0.3 * baseline_factor
        return round(min(confidence, 1.0), 4)

    # ------------------------------------------------------------------
    # New anomaly algorithms (Phase 34)
    # ------------------------------------------------------------------

    def _entity_identifier(self, node_id: str) -> str:
        node = self._graph.nodes.get(node_id)
        if node is None:
            return node_id
        e = node.entity
        return (
            getattr(e, "ip", None)
            or getattr(e, "domain_name", None)
            or getattr(e, "cve_id", None)
            or node_id
        )

    def threat_score_anomaly(self) -> list[AnomalyResult]:
        """Flag entities whose threat_score is > 2 std from same-type mean."""
        results: list[AnomalyResult] = []
        type_scores: dict[str, list[float]] = {}
        # Collect threat scores by entity type from nodes + cache
        for nid, node in self._graph.nodes.items():
            etype = getattr(node.entity, "entity_type", None)
            if etype is None:
                continue
            etype_name = etype.name if hasattr(etype, "name") else str(etype)
            ts = _THREAT_SCORE_CACHE.get(nid, 0.0)
            if ts > 0:
                type_scores.setdefault(etype_name, []).append(ts)

        # Compute mean + std per type
        type_stats: dict[str, tuple[float, float]] = {}
        for etype, scores in type_scores.items():
            if len(scores) < 2:
                continue
            mean = sum(scores) / len(scores)
            var = sum((s - mean) ** 2 for s in scores) / len(scores)
            std = math.sqrt(var) if var > 0 else 0.0
            type_stats[etype] = (mean, std)

        for nid, node in self._graph.nodes.items():
            etype = getattr(node.entity, "entity_type", None)
            if etype is None:
                continue
            etype_name = etype.name if hasattr(etype, "name") else str(etype)
            if etype_name not in type_stats:
                continue
            mean, std = type_stats[etype_name]
            if std == 0:
                continue
            ts = _THREAT_SCORE_CACHE.get(nid, 0.0)
            if ts == 0:
                continue
            z = (ts - mean) / std
            if z >= 2.0:
                score = min(100.0, z * 20.0)
                results.append(
                    AnomalyResult(
                        node_id=nid,
                        anomaly_type="threat_score",
                        anomaly_score=score,
                        explanation=f"Threat score {ts:.1f} is {z:.1f}σ above {etype_name} mean {mean:.1f}",
                        entity_type=etype_name,
                        entity_identifier=self._entity_identifier(nid),
                    )
                )
        return results

    def temporal_spike_anomaly(self) -> list[AnomalyResult]:
        """Flag entities with sudden activity spike in last 24h vs 30d avg."""
        results: list[AnomalyResult] = []
        now = datetime.now(UTC)
        cutoff_24h = now - timedelta(hours=24)
        cutoff_30d = now - timedelta(days=30)

        for nid, node in self._graph.nodes.items():
            entity = node.entity
            etype = getattr(entity, "entity_type", None)
            etype_name = etype.name if hasattr(etype, "name") else str(etype)

            # Count evidence in last 24h vs last 30d
            ev_list = getattr(entity, "evidence", ())
            if not ev_list:
                continue
            count_24h = 0
            count_30d = 0
            for ev in ev_list:
                ts = getattr(ev, "collected_at", None)
                if ts is None:
                    continue
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts)
                    except ValueError:
                        continue
                if ts >= cutoff_24h:
                    count_24h += 1
                if ts >= cutoff_30d:
                    count_30d += 1

            if count_30d < 3 or count_24h == 0:
                continue
            ratio = count_24h / (count_30d / 30.0)  # normalized to daily rate
            if ratio > 3.0:
                score = min(100.0, ratio * 15.0)
                results.append(
                    AnomalyResult(
                        node_id=nid,
                        anomaly_type="temporal_spike",
                        anomaly_score=score,
                        explanation=f"Recent activity spike: {count_24h} evidence in 24h "
                        f"({ratio:.1f}x the 30d daily avg of {count_30d / 30:.1f})",
                        entity_type=etype_name,
                        entity_identifier=self._entity_identifier(nid),
                    )
                )
        return results

    def relationship_outlier_anomaly(self) -> list[AnomalyResult]:
        """Flag entities whose edge count is extreme vs same-type peers."""
        results: list[AnomalyResult] = []
        type_degrees: dict[str, list[int]] = {}
        for nid, node in self._graph.nodes.items():
            etype = getattr(node.entity, "entity_type", None)
            if etype is None:
                continue
            etype_name = etype.name if hasattr(etype, "name") else str(etype)
            deg = len(self._graph.adjacency.get(nid, set()))
            type_degrees.setdefault(etype_name, []).append(deg)

        type_stats: dict[str, tuple[float, float]] = {}
        for etype, degs in type_degrees.items():
            if len(degs) < 2:
                continue
            mean = sum(degs) / len(degs)
            var = sum((d - mean) ** 2 for d in degs) / len(degs)
            std = math.sqrt(var) if var > 0 else 0.0
            type_stats[etype] = (mean, std)

        for nid, node in self._graph.nodes.items():
            etype = getattr(node.entity, "entity_type", None)
            if etype is None:
                continue
            etype_name = etype.name if hasattr(etype, "name") else str(etype)
            if etype_name not in type_stats:
                continue
            mean, std = type_stats[etype_name]
            if std == 0:
                continue
            deg = len(self._graph.adjacency.get(nid, set()))
            if deg == 0:
                continue
            z = (deg - mean) / std
            if z >= 2.0:
                score = min(100.0, z * 15.0)
                results.append(
                    AnomalyResult(
                        node_id=nid,
                        anomaly_type="relationship_outlier",
                        anomaly_score=score,
                        explanation=f"Has {deg} edges ({z:.1f}σ above {etype_name} mean {mean:.1f})",
                        entity_type=etype_name,
                        entity_identifier=self._entity_identifier(nid),
                    )
                )
        return results

    def detect_all(self) -> list[AnomalyResult]:
        """Run all anomaly algorithms and return combined, deduplicated results."""
        combined: dict[str, AnomalyResult] = {}
        for detector in [
            self.threat_score_anomaly,
            self.temporal_spike_anomaly,
            self.relationship_outlier_anomaly,
        ]:
            for r in detector():
                key = f"{r.node_id}:{r.anomaly_type}"
                if key not in combined or r.anomaly_score > combined[key].anomaly_score:
                    combined[key] = r
        # Also include the existing multi-factor results (scaled to 0-100)
        multi = self.multi_factor_score()
        for nid, score in multi.get("scores", {}).items():
            if score <= 0:
                continue
            scaled = min(100.0, score * 100.0)
            node = self._graph.nodes.get(nid)
            etype_name = ""
            if node:
                etype = getattr(node.entity, "entity_type", None)
                etype_name = etype.name if hasattr(etype, "name") else str(etype) if etype else ""
            key = f"{nid}:multi_factor"
            combined[key] = AnomalyResult(
                node_id=nid,
                anomaly_type="multi_factor",
                anomaly_score=scaled,
                explanation=f"Multi-factor anomaly score: {score:.4f} (z-score, IQR, degree, temporal, community, influence)",
                entity_type=etype_name,
                entity_identifier=self._entity_identifier(nid),
            )
        return sorted(combined.values(), key=lambda r: -r.anomaly_score)

    def detect(self) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        multi_result = self.multi_factor_score()
        scores = multi_result["scores"]
        signals = multi_result.get("signals", {})
        high_count = sum(1 for v in scores.values() if v > 0.7)
        medium_count = sum(1 for v in scores.values() if 0.4 < v <= 0.7)
        low_count = sum(1 for v in scores.values() if 0.0 < v <= 0.4)
        top_anomalies: list[dict[str, Any]] = []
        for nid, score in list(scores.items())[:20]:
            sig = signals.get(nid, {})
            conf = self.confidence_score(nid)
            contribs = self.feature_contributions(nid)
            top_signal = max(contribs, key=contribs.get) if contribs else "unknown"
            top_anomalies.append(
                {
                    "node_id": nid,
                    "anomaly_score": score,
                    "confidence": conf,
                    "top_signal": top_signal,
                    "signal_count": sum(
                        1 for k, v in sig.items() if k.endswith("_intensity") is False and v > 0
                    ),
                }
            )
        duration = time.perf_counter_ns() - t0
        self._record_duration("detect", duration)
        self._metrics.set_gauge("anomaly_detect_duration_ms", duration / 1_000_000)
        self._metrics.set_gauge("anomaly_high_count", float(high_count))
        self._metrics.set_gauge("anomaly_medium_count", float(medium_count))
        self._metrics.set_gauge("anomaly_low_count", float(low_count))
        n = float(len(scores)) if scores else 1.0
        self._metrics.set_gauge("anomaly_mean_score", sum(scores.values()) / n)
        return {
            "detections": {
                "high": high_count,
                "medium": medium_count,
                "low": low_count,
            },
            "total_nodes_analyzed": len(scores),
            "top_anomalies": top_anomalies,
            "graph_version": self._graph_version,
            "graph_node_count": self._graph.node_count,
            "graph_edge_count": self._graph.edge_count,
            "baseline_status": "active" if bool(self._baseline.get_all_baselines()) else "cold",
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def detect_for_node(self, node_id: str) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        if node_id not in self._graph.nodes:
            return {"node_id": node_id, "found": False, "execution_time_ms": 0.0}
        multi_result = self.multi_factor_score()
        scores = multi_result["scores"]
        signals = multi_result.get("signals", {})
        score = scores.get(node_id, 0.0)
        sig = signals.get(node_id, {})
        conf = self.confidence_score(node_id)
        contribs = self.feature_contributions(node_id)
        node_signal_breakdown: dict[str, Any] = {}
        for signal_name in [
            "zscore",
            "iqr",
            "degree_outlier",
            "temporal",
            "community",
            "influence_score",
        ]:
            val = sig.get(signal_name, 0.0)
            intensity_key = f"{signal_name}_intensity" if signal_name != "influence_score" else None
            intensity = sig.get(intensity_key, 0.0) if intensity_key else val
            node_signal_breakdown[signal_name] = {
                "detected": bool(val),
                "intensity": round(float(intensity), 4),
            }
        feature_breakdown = {k: round(v, 4) for k, v in contribs.items()}
        duration = time.perf_counter_ns() - t0
        return {
            "node_id": node_id,
            "found": True,
            "anomaly_score": round(score, 6),
            "confidence": conf,
            "severity": "high" if score > 0.7 else ("medium" if score > 0.4 else "low"),
            "signals": node_signal_breakdown,
            "feature_contributions": feature_breakdown,
            "top_contributing_feature": max(contribs, key=contribs.get) if contribs else None,
            "graph_version": self._graph_version,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def timeline(self) -> dict[str, Any]:
        historical_drift = self._baseline.historical_drift()
        node_ids = sorted(self._graph.nodes.keys())
        multi_scores = self.multi_factor_score()["scores"]
        timeline_entries: list[dict[str, Any]] = []
        for nid in node_ids:
            hist_drift = historical_drift.get(nid, 0.0)
            score = multi_scores.get(nid, 0.0)
            timeline_entries.append(
                {
                    "node_id": nid,
                    "current_score": score,
                    "historical_drift": hist_drift,
                    "trend": (
                        "increasing"
                        if hist_drift > 0.5
                        else ("stable" if hist_drift > 0.1 else "decreasing")
                    ),
                }
            )
        timeline_entries.sort(key=lambda x: -x["current_score"])
        return {
            "timeline": timeline_entries,
            "entry_count": len(timeline_entries),
            "graph_version": self._graph_version,
            "high_count": sum(1 for e in timeline_entries if e["current_score"] > 0.7),
            "medium_count": sum(1 for e in timeline_entries if 0.4 < e["current_score"] <= 0.7),
        }

    def top_anomalies(self, n: int = 10) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        multi_result = self.multi_factor_score()
        scores = multi_result["scores"]
        signals = multi_result.get("signals", {})
        top_n = dict(list(scores.items())[:n])
        result: list[dict[str, Any]] = []
        for nid, score in top_n.items():
            sig = signals.get(nid, {})
            conf = self.confidence_score(nid)
            contribs = self.feature_contributions(nid)
            result.append(
                {
                    "node_id": nid,
                    "anomaly_score": score,
                    "confidence": conf,
                    "top_signal": max(contribs, key=contribs.get) if contribs else "unknown",
                    "signal_count": sum(
                        1
                        for k, v in sig.items()
                        if not k.endswith("_intensity") and k != "influence_score" and v > 0
                    ),
                }
            )
        duration = time.perf_counter_ns() - t0
        return {
            "top_nodes": result,
            "count": len(result),
            "total_nodes": len(scores),
            "graph_version": self._graph_version,
            "execution_time_ms": round(duration / 1_000_000, 2),
        }

    def _build_explanation(
        self,
        node_id: str,
        detailed: bool = False,
    ) -> dict[str, Any]:
        if node_id not in self._graph.nodes:
            return {
                "node_id": node_id,
                "found": False,
                "schema_version": EXPLANATION_SCHEMA_VERSION,
            }
        features = self._compute_features()
        if node_id not in features:
            return {
                "node_id": node_id,
                "found": False,
                "schema_version": EXPLANATION_SCHEMA_VERSION,
            }
        entity_type = features[node_id].get("__entity_type", "unknown")
        multi_result = self.multi_factor_score()
        overall_score = multi_result["scores"].get(node_id, 0.0)
        signals = multi_result.get("signals", {}).get(node_id, {})
        contribs = self.feature_contributions(node_id)
        conf = self.confidence_score(node_id)
        feats = {k: v for k, v in features[node_id].items() if not k.startswith("__")}
        bl = self._baseline.get_all_baselines().get(entity_type, {})
        signal_details: dict[str, Any] = {}
        for signal_name in ["zscore", "iqr", "degree_outlier", "temporal", "community"]:
            detected = bool(signals.get(signal_name, 0.0))
            intensity = signals.get(f"{signal_name}_intensity", 0.0)
            detail: dict[str, Any] = {
                "score": round(float(intensity), 4) if detected else 0.0,
                "contribution": (
                    contribs.get(signal_name, 0.0)
                    if detailed
                    else round(contribs.get(signal_name, 0.0), 4)
                ),
                "detected": detected,
            }
            if detailed:
                detail["feature_values"] = feats
                detail["baseline"] = bl
            signal_details[signal_name] = detail
        influence_signal = {
            "score": round(signals.get("influence_score", 0.0), 6),
            "contribution": (
                contribs.get("influence_score", 0.0)
                if detailed
                else round(contribs.get("influence_score", 0.0), 4)
            ),
            "detected": bool(signals.get("influence_score", 0.0) > 0.1),
        }
        signal_details["influence"] = influence_signal
        top_contributors = sorted(contribs.items(), key=lambda x: -x[1])[:3]
        baseline_deviation = sum(
            abs(feats.get(k, 0.0) - bl.get(k, {}).get("mean", 0.0))
            / max(bl.get(k, {}).get("std", 1e-10), 1e-10)
            for k in feats
            if k in bl and bl[k].get("std", 0) > 0
        )
        result: dict[str, Any] = {
            "schema_version": EXPLANATION_SCHEMA_VERSION,
            "node_id": node_id,
            "found": True,
            "overall_score": round(overall_score, 6),
            "confidence": conf,
            "severity": (
                "high" if overall_score > 0.7 else ("medium" if overall_score > 0.4 else "low")
            ),
            "signals": signal_details,
            "top_contributors": [
                {"feature": k, "weight": round(v, 4)} for k, v in top_contributors
            ],
            "entity_type": entity_type,
            "graph_version": self._graph_version,
            "baseline_deviation": round(baseline_deviation, 4),
        }
        if detailed:
            result["feature_values"] = feats
            result["entity_type_baseline"] = bl
            result["network_context"] = {
                "degree": len(self._graph.adjacency.get(node_id, set())),
                "neighbors": sorted(self._graph.adjacency.get(node_id, set())),
            }
        return result

    def explain(self, node_id: str) -> dict[str, Any]:
        return self._build_explanation(node_id, detailed=False)

    def explain_detail(self, node_id: str) -> dict[str, Any]:
        return self._build_explanation(node_id, detailed=True)
