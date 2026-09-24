from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from intelgraph.core.enterprise.observability import get_metrics
from intelgraph.core.explainability.interpreter import (
    CounterfactualExplainer,
    FeatureImportance,
    ModelInterpreter,
)
from intelgraph.core.governance.policy import ApprovalWorkflow, AuditTrail, ComplianceChecker
from intelgraph.core.graph.anomaly import AnomalyDetector
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.graph.prediction import Predictor
from intelgraph.core.graph.reasoning import CausalReasoner
from intelgraph.core.safety.guard import SafetyGuard

KERNEL_SCHEMA_VERSION = "1.0"
KERNEL_EXECUTION_VERSION = "1.0"


@dataclass
class KernelTrace:
    trace_id: str
    graph_version: str
    execution_mode: str
    phases: dict[str, Any]
    coherence_score: float
    started_at: float
    completed_at: float = 0.0
    execution_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "graph_version": self.graph_version,
            "execution_mode": self.execution_mode,
            "phases": self.phases,
            "coherence_score": round(self.coherence_score, 4),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "execution_fingerprint": self.execution_fingerprint,
            "schema_version": KERNEL_SCHEMA_VERSION,
            "kernel_version": KERNEL_EXECUTION_VERSION,
        }


class CrossSystemConsistency:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    def coherence_score(
        self,
        anomaly_result: dict[str, Any] | None,
        causal_result: dict[str, Any] | None,
        prediction_result: dict[str, Any] | None,
    ) -> float:
        score = 1.0
        if anomaly_result and causal_result:
            anom_scores = anomaly_result.get("scores", {})
            if causal_result.get("root_causes"):
                len(causal_result["root_causes"])
            overlap = 0
            for nid in anom_scores:
                for rc in causal_result.get("root_causes", []):
                    if nid == rc.get("root_cause_node"):
                        overlap += 1
            if max(len(anom_scores), 1) > 0:
                score *= 1.0 - 0.2 * (1.0 - overlap / max(len(anom_scores), 1))
        if causal_result and prediction_result:
            score *= 0.95
        if anomaly_result and prediction_result:
            score *= 0.95
        return max(0.0, round(score, 4))

    def detect_conflicts(
        self,
        anomaly_result: dict[str, Any] | None,
        causal_result: dict[str, Any] | None,
        prediction_result: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        if anomaly_result and causal_result:
            anom_scores = anomaly_result.get("scores", {})
            top_anom_nodes = set(sorted(anom_scores, key=lambda k: -anom_scores[k])[:5])
            causal_nodes = set()
            for rc in causal_result.get("root_causes", []):
                causal_nodes.add(rc.get("root_cause_node", ""))
            missing = top_anom_nodes - causal_nodes
            if missing:
                conflicts.append(
                    {
                        "type": "anomaly_causal_mismatch",
                        "severity": "warning",
                        "detail": f"Anomaly nodes {missing} have no causal root cause path",
                        "resolution_hint": "increase causal max_depth or check graph connectivity",
                    }
                )
        if prediction_result and anomaly_result:
            pred_scores = [p.get("value", 0.0) for p in prediction_result.get("predictions", [])]
            if pred_scores and max(pred_scores) > 0.8:
                anom_scores = anomaly_result.get("scores", {})
                if anom_scores and max(anom_scores.values()) < 0.3:
                    conflicts.append(
                        {
                            "type": "prediction_anomaly_divergence",
                            "severity": "warning",
                            "detail": "High prediction scores but low anomaly scores",
                            "resolution_hint": "check feature freshness and model calibration",
                        }
                    )
        return conflicts


class UnifiedExecutionKernel:
    def __init__(
        self,
        graph: IntelligenceGraph,
        config: dict[str, Any] | None = None,
        weight_fn: Callable[[Any], float] | None = None,
        deterministic: bool = True,
    ) -> None:
        self._graph = graph
        self._config = config or {}
        self._weight_fn = weight_fn or (lambda e: 1.0)
        self._deterministic = deterministic
        self._graph_version = self._compute_graph_version()
        self._metrics = get_metrics()
        self._consistency = CrossSystemConsistency(config)
        self._anomaly_detector = AnomalyDetector(graph, config, weight_fn)
        self._causal_reasoner = CausalReasoner(graph, config, weight_fn, deterministic)
        self._predictor = Predictor(graph, config, weight_fn, deterministic)
        self._feature_importance = FeatureImportance(config)
        self._model_interpreter = ModelInterpreter(config)
        self._counterfactual_explainer = CounterfactualExplainer(config)
        self._audit_trail = AuditTrail(
            max_entries=self._config.get("governance", {}).get("audit_max_entries", 10000),
        )
        self._compliance_checker = ComplianceChecker(
            self._config.get("governance", {}).get("compliance_rules", {}),
        )
        self._approval_workflow = ApprovalWorkflow(
            risk_threshold=self._config.get("governance", {}).get("risk_threshold", 0.7),
            auto_approve_low_risk=self._config.get("governance", {}).get(
                "auto_approve_low_risk", True
            ),
        )
        self._safety_guard = SafetyGuard(
            bounds=self._config.get("safety", {}).get("bounds", {}),
            fallbacks=(
                {
                    pt: self._config.get("safety", {}).get("fallback_default", 0.0)
                    for pt in [
                        "risk_forecast",
                        "temporal_trend",
                        "influence_trajectory",
                        "anomaly_likelihood",
                        "attack_path_probability",
                        "community_evolution",
                    ]
                }
                if self._config.get("safety", {}).get("enabled", True)
                else {}
            ),
        )

    def _compute_graph_version(self) -> str:
        node_ids = sorted(self._graph.nodes.keys())
        edge_ids = sorted(self._graph.edges.keys())
        raw = "|".join(node_ids) + "||" + "|".join(edge_ids)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _generate_trace_id(self) -> str:
        return f"kt_{uuid.uuid4().hex[:16]}"

    def _fingerprint(self, trace_id: str, inputs: dict[str, Any]) -> str:
        raw = f"{trace_id}:{self._graph_version}:{inputs}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def execute(
        self,
        anomaly_node: str | None = None,
        enable_anomaly: bool = True,
        enable_causal: bool = True,
        enable_prediction: bool = True,
        horizon: int = 1,
    ) -> dict[str, Any]:
        t0 = time.perf_counter_ns()
        trace_id = self._generate_trace_id()
        inputs = {
            "anomaly_node": anomaly_node,
            "enable_anomaly": enable_anomaly,
            "enable_causal": enable_causal,
            "enable_prediction": enable_prediction,
            "horizon": horizon,
        }
        fingerprint = self._fingerprint(trace_id, inputs)
        trace = KernelTrace(
            trace_id=trace_id,
            graph_version=self._graph_version,
            execution_mode="deterministic" if self._deterministic else "non-deterministic",
            phases={},
            coherence_score=1.0,
            started_at=time.time(),
            execution_fingerprint=fingerprint,
        )
        anomaly_result = None
        causal_result = None
        prediction_result = None
        all_anomaly_scores: dict[str, float] = {}
        all_influence_scores: dict[str, float] = {}
        communities: dict[str, list[str]] = {}
        if enable_anomaly:
            try:
                anomaly_result = self._anomaly_detector.multi_factor_score()
                all_anomaly_scores = anomaly_result.get("scores", {})
                self._anomaly_detector._baseline.record_snapshot(
                    self._anomaly_detector._compute_features()
                )
                self._anomaly_detector._baseline.compute_baselines(
                    self._anomaly_detector._compute_features()
                )
                self._causal_reasoner._anomaly_scores = all_anomaly_scores
                self._predictor._anomaly_scores = all_anomaly_scores
                trace.phases["anomaly"] = {
                    "status": "completed",
                    "node_count": len(all_anomaly_scores),
                }
            except Exception as e:
                trace.phases["anomaly"] = {"status": "failed", "error": str(e)}
        if enable_causal and anomaly_node:
            try:
                causal_result = self._causal_reasoner.top_causes(
                    anomaly_node, max_depth=5, top_n=10
                )
                if causal_result.get("found"):
                    all_influence_scores = {
                        rc.get("root_cause_node", ""): rc.get("confidence", 0.0)
                        for rc in causal_result.get("root_causes", [])
                    }
                    self._predictor._influence_scores = all_influence_scores
                trace.phases["causal"] = {
                    "status": "completed",
                    "root_cause_count": len(causal_result.get("root_causes", [])),
                }
            except Exception as e:
                causal_result = {"found": False, "error": str(e)}
                trace.phases["causal"] = {"status": "failed", "error": str(e)}
        if enable_prediction:
            try:
                nodes_to_forecast = (
                    [anomaly_node] if anomaly_node else list(self._graph.nodes.keys())[:5]
                )
                all_predictions: list[dict[str, Any]] = []
                for nid in nodes_to_forecast:
                    if nid in self._graph.nodes:
                        fcast = self._predictor.full_forecast(nid, communities)
                        all_predictions.append(fcast)
                prediction_result = {
                    "forecasts": all_predictions,
                    "total_forecasts": len(all_predictions),
                }
                trace.phases["prediction"] = {
                    "status": "completed",
                    "forecast_count": len(all_predictions),
                }
            except Exception as e:
                prediction_result = {"forecasts": [], "total_forecasts": 0, "error": str(e)}
                trace.phases["prediction"] = {"status": "failed", "error": str(e)}
        coherence = self._consistency.coherence_score(
            anomaly_result, causal_result, prediction_result
        )
        conflicts = self._consistency.detect_conflicts(
            anomaly_result, causal_result, prediction_result
        )
        trace.coherence_score = coherence
        trace.completed_at = time.time()
        duration = time.perf_counter_ns() - t0
        self._metrics.set_gauge("kernel_execution_duration_ms", duration / 1_000_000)
        self._metrics.set_gauge("kernel_coherence_score", coherence)
        explainability_result = None
        safety_result = None
        governance_result = None
        if enable_prediction and prediction_result:
            all_pred_dicts: list[dict[str, Any]] = []
            for fc in prediction_result.get("forecasts", []):
                all_pred_dicts.extend(fc.get("predictions", []))
            if all_pred_dicts:
                try:
                    fi = self._feature_importance
                    contribs: dict[str, float] = {}
                    features_map: dict[str, float] = {}
                    for pred in all_pred_dicts:
                        for k, v in pred.get("contributions", {}).items():
                            contribs[k] = contribs.get(k, 0.0) + abs(v)
                        for k, v in pred.get("features", {}).items():
                            features_map[k] = v
                    explanation = fi.compute_importance(
                        features=features_map,
                        contributions=contribs,
                        top_n=self._config.get("explainability", {}).get("max_top_features", 5),
                    )
                    explainability_result = {
                        "feature_importance": [e.to_dict() for e in explanation],
                        "summary": f"Top {len(explanation)} features contribute to prediction",
                        "model_fidelity": 0.85,
                    }
                except Exception as e:
                    trace.phases["explainability"] = {"status": "failed", "error": str(e)}
                else:
                    trace.phases["explainability"] = {
                        "status": "completed",
                        "feature_count": len(explanation),
                    }

                pred_value = all_pred_dicts[0].get("value", 0.0)
                pred_type = all_pred_dicts[0].get("prediction_type", "unknown")

                try:
                    safety_result = self._safety_guard.check_prediction(
                        prediction_type=pred_type,
                        value=pred_value,
                    )
                    trace.phases["safety"] = {"status": "completed", "passed": safety_result.passed}
                except Exception as e:
                    safety_result = SafetyGuard().check_prediction(pred_type, pred_value)
                    trace.phases["safety"] = {"status": "failed", "error": str(e)}

                try:
                    entity_risk = max((p.get("value", 0.0) for p in all_pred_dicts), default=0.0)
                    compliance_report = self._compliance_checker.check(
                        prediction_type=pred_type,
                        value=pred_value,
                        entity_risk=entity_risk,
                    )
                    governance_result = compliance_report.to_dict()
                    trace.phases["governance"] = {
                        "status": "completed",
                        "compliant": compliance_report.status.name == "COMPLIANT",
                    }
                except Exception as e:
                    governance_result = {"status": "non_compliant", "error": str(e)}
                    trace.phases["governance"] = {"status": "failed", "error": str(e)}

                self._audit_trail.record(
                    action="kernel_execute",
                    entity_id=anomaly_node or "all",
                    prediction_type=pred_type,
                    value=pred_value,
                    actor="kernel",
                    metadata={
                        "coherence": coherence,
                        "safety_passed": safety_result.passed if safety_result else True,
                    },
                )

        return {
            "trace": trace.to_dict(),
            "anomaly": anomaly_result,
            "causal": causal_result,
            "prediction": prediction_result,
            "explainability": explainability_result,
            "safety": safety_result.to_dict() if safety_result else None,
            "governance": governance_result,
            "coherence": {
                "score": coherence,
                "conflicts": conflicts,
                "cross_phase_consistent": len(conflicts) == 0,
            },
            "execution_time_ms": round(duration / 1_000_000, 2),
        }


def build_graph_from_container() -> IntelligenceGraph:
    from intelgraph.api.main import _container

    g = IntelligenceGraph()
    for entity in _container.backend.list_entities():
        eid = entity.id
        g.nodes[eid] = Node(entity=entity)
        g.adjacency.setdefault(eid, set())
        g.forward_adjacency.setdefault(eid, set())
        g.reverse_adjacency.setdefault(eid, set())
        g.node_edges.setdefault(eid, set())
    for rel in _container.backend.list_relationships():
        src = rel.source_id
        tgt = rel.target_id
        if src in g.nodes and tgt in g.nodes:
            from intelgraph.core.graph.edge import Edge

            g.adjacency.setdefault(src, set()).add(tgt)
            g.adjacency.setdefault(tgt, set()).add(src)
            g.forward_adjacency.setdefault(src, set()).add(tgt)
            g.reverse_adjacency.setdefault(tgt, set()).add(src)
            g.node_edges.setdefault(src, set()).add(rel.id)
            g.node_edges.setdefault(tgt, set()).add(rel.id)
            g.edge_node_map[rel.id] = (src, tgt)
            e = Edge(relationship=rel)
            g.edges[rel.id] = e
    return g
