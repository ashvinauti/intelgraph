from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.request import Request, urlopen

from intelgraph.core.enterprise.observability import get_metrics

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    category: str
    severity: str
    timestamp: str
    current_value: float
    threshold_value: float
    message: str = ""


class AlertEngine:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        metrics_collector: Any = None,
    ) -> None:
        self._lock = threading.Lock()
        self._config = config or {}
        self._alerts: list[Alert] = []
        self._cooldowns: dict[str, float] = {}
        self._metrics = metrics_collector

    def evaluate(self) -> list[Alert]:
        triggered: list[Alert] = []
        now = time.time()

        thresholds = self._config.get("thresholds", {})
        cooldown_sec = self._config.get("cooldown_seconds", 300)
        mc = self._metrics if self._metrics is not None else get_metrics()
        metrics = mc.snapshot()
        ts = datetime.now(UTC).isoformat()

        error_threshold = thresholds.get("error_rate", {})
        if error_threshold.get("enabled", False):
            current_err = metrics.get("total_errors", 0)
            max_err = error_threshold.get("max", 10)
            key = "error_rate"
            if current_err > max_err and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="error_rate",
                    severity=error_threshold.get("severity", "warning"),
                    timestamp=ts,
                    current_value=float(current_err),
                    threshold_value=float(max_err),
                    message=f"Error count {current_err} exceeds threshold {max_err}",
                )
                triggered.append(alert)

        latency_threshold = thresholds.get("request_latency", {})
        if latency_threshold.get("enabled", False):
            avg_lat = metrics.get("avg_duration_ms", 0.0)
            max_lat = latency_threshold.get("max_ms", 1000.0)
            key = "request_latency"
            if avg_lat > max_lat and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="request_latency",
                    severity=latency_threshold.get("severity", "warning"),
                    timestamp=ts,
                    current_value=avg_lat,
                    threshold_value=max_lat,
                    message=f"Average latency {avg_lat:.2f}ms exceeds threshold {max_lat}ms",
                )
                triggered.append(alert)

        rl_threshold = thresholds.get("rate_limit_hits", {})
        if rl_threshold.get("enabled", False):
            status_counts = metrics.get("status_codes", {})
            hits = int(status_counts.get("429", 0))
            max_hits = rl_threshold.get("max", 50)
            key = "rate_limit_hits"
            if hits > max_hits and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="rate_limit_hits",
                    severity=rl_threshold.get("severity", "warning"),
                    timestamp=ts,
                    current_value=float(hits),
                    threshold_value=float(max_hits),
                    message=f"Rate limit hits {hits} exceeds threshold {max_hits}",
                )
                triggered.append(alert)

        pagerank_threshold = thresholds.get("pagerank_convergence", {})
        if pagerank_threshold.get("enabled", False):
            gauges = metrics.get("gauges", {})
            pr_duration = gauges.get("influence_page_rank_duration_ms", 0.0)
            max_pr_time = pagerank_threshold.get("max_duration_ms", 10000.0)
            key = "pagerank_convergence"
            if pr_duration > max_pr_time and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="pagerank_convergence",
                    severity=pagerank_threshold.get("severity", "warning"),
                    timestamp=ts,
                    current_value=pr_duration,
                    threshold_value=max_pr_time,
                    message=f"PageRank computation took {pr_duration:.2f}ms (threshold: {max_pr_time}ms)",
                )
                triggered.append(alert)

        influence_time_threshold = thresholds.get("influence_computation_time", {})
        if influence_time_threshold.get("enabled", False):
            gauges = metrics.get("gauges", {})
            max_infl_time = influence_time_threshold.get("max_duration_ms", 30000.0)
            for gname, gval in gauges.items():
                if gname.startswith("influence_") and gname.endswith("_duration_ms"):
                    key = f"influence_time_{gname}"
                    if gval > max_infl_time and self._can_alert(key, now, cooldown_sec):
                        alert = Alert(
                            category="influence_computation_time",
                            severity=influence_time_threshold.get("severity", "warning"),
                            timestamp=ts,
                            current_value=gval,
                            threshold_value=max_infl_time,
                            message=f"{gname} took {gval:.2f}ms (threshold: {max_infl_time}ms)",
                        )
                        triggered.append(alert)

        anomaly_threshold = thresholds.get("influence_score_anomaly", {})
        if anomaly_threshold.get("enabled", False):
            gauges = metrics.get("gauges", {})
            top_influence = gauges.get("influence_top_node_score", 0.0)
            mean_influence = gauges.get("influence_mean_score", 0.0)
            max_ratio = anomaly_threshold.get("max_top_to_mean_ratio", 100.0)
            key = "influence_score_anomaly"
            if (
                mean_influence > 0.0
                and (top_influence / mean_influence) > max_ratio
                and self._can_alert(key, now, cooldown_sec)
            ):
                alert = Alert(
                    category="influence_score_anomaly",
                    severity=anomaly_threshold.get("severity", "warning"),
                    timestamp=ts,
                    current_value=round(top_influence / mean_influence, 2),
                    threshold_value=max_ratio,
                    message=f"Influence score top/mean ratio {top_influence / mean_influence:.2f} exceeds {max_ratio}",
                )
                triggered.append(alert)

        anomaly_spike_threshold = thresholds.get("anomaly_spike", {})
        if anomaly_spike_threshold.get("enabled", False):
            gauges = metrics.get("gauges", {})
            high_count = gauges.get("anomaly_high_count", 0.0)
            max_high = anomaly_spike_threshold.get("max_high_count", 10)
            key = "anomaly_spike"
            if high_count > max_high and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="anomaly_spike",
                    severity=anomaly_spike_threshold.get("severity", "warning"),
                    timestamp=ts,
                    current_value=high_count,
                    threshold_value=float(max_high),
                    message=f"High-severity anomaly count {high_count:.0f} exceeds threshold {max_high}",
                )
                triggered.append(alert)

        anomaly_critical_threshold = thresholds.get("anomaly_critical_threshold", {})
        if anomaly_critical_threshold.get("enabled", False):
            gauges = metrics.get("gauges", {})
            max_score = gauges.get("anomaly_max_score", 0.0)
            min_anomaly = anomaly_critical_threshold.get("min_anomaly_score", 0.9)
            key = "anomaly_critical_threshold"
            if max_score > min_anomaly and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="anomaly_critical_threshold",
                    severity=anomaly_critical_threshold.get("severity", "critical"),
                    timestamp=ts,
                    current_value=max_score,
                    threshold_value=min_anomaly,
                    message=f"Critical anomaly score {max_score:.4f} exceeds threshold {min_anomaly}",
                )
                triggered.append(alert)

        anomaly_dist_shift = thresholds.get("anomaly_distribution_shift", {})
        if anomaly_dist_shift.get("enabled", False):
            gauges = metrics.get("gauges", {})
            mean_score = gauges.get("anomaly_mean_score", 0.0)
            max_change = anomaly_dist_shift.get("max_mean_score_change", 0.3)
            key = "anomaly_distribution_shift"
            if (
                mean_score > 0.0
                and abs(mean_score - gauges.get("anomaly_mean_score_prev", 0.0)) > max_change
                and self._can_alert(key, now, cooldown_sec)
            ):
                alert = Alert(
                    category="anomaly_distribution_shift",
                    severity=anomaly_dist_shift.get("severity", "warning"),
                    timestamp=ts,
                    current_value=round(mean_score, 4),
                    threshold_value=max_change,
                    message=f"Anomaly mean score shift {mean_score:.4f} exceeds threshold {max_change}",
                )
                triggered.append(alert)

        anomaly_baseline_drift = thresholds.get("anomaly_baseline_drift_surge", {})
        if anomaly_baseline_drift.get("enabled", False):
            gauges = metrics.get("gauges", {})
            drift = gauges.get("anomaly_baseline_drift", 0.0)
            max_drift = anomaly_baseline_drift.get("max_baseline_drift", 3.0)
            key = "anomaly_baseline_drift_surge"
            if drift > max_drift and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="anomaly_baseline_drift_surge",
                    severity=anomaly_baseline_drift.get("severity", "warning"),
                    timestamp=ts,
                    current_value=drift,
                    threshold_value=max_drift,
                    message=f"Baseline drift {drift:.4f} exceeds threshold {max_drift}",
                )
                triggered.append(alert)

        attack_path_high_risk = thresholds.get("attack_path_high_risk", {})
        if attack_path_high_risk.get("enabled", False):
            gauges = metrics.get("gauges", {})
            max_risk = gauges.get("attack_path_max_risk_score", 0.0)
            risk_thresh = attack_path_high_risk.get("max_risk_score", 0.8)
            key = "attack_path_high_risk"
            if max_risk > risk_thresh and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="attack_path_high_risk",
                    severity=attack_path_high_risk.get("severity", "critical"),
                    timestamp=ts,
                    current_value=max_risk,
                    threshold_value=risk_thresh,
                    message=f"High-risk attack path detected: score {max_risk:.4f} exceeds threshold {risk_thresh}",
                )
                triggered.append(alert)

        attack_path_surface = thresholds.get("attack_path_surface_expansion", {})
        if attack_path_surface.get("enabled", False):
            gauges = metrics.get("gauges", {})
            surface_growth = gauges.get("attack_path_surface_growth", 0.0)
            max_growth = attack_path_surface.get("max_surface_growth", 0.5)
            key = "attack_path_surface_expansion"
            if surface_growth > max_growth and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="attack_path_surface_expansion",
                    severity=attack_path_surface.get("severity", "warning"),
                    timestamp=ts,
                    current_value=surface_growth,
                    threshold_value=max_growth,
                    message=f"Attack surface growth {surface_growth:.2f} exceeds threshold {max_growth}",
                )
                triggered.append(alert)

        attack_path_inconsistency = thresholds.get("attack_path_inconsistency", {})
        if attack_path_inconsistency.get("enabled", False):
            gauges = metrics.get("gauges", {})
            deviation = gauges.get("attack_path_cross_version_deviation", 0.0)
            max_dev = attack_path_inconsistency.get("max_score_deviation", 0.2)
            key = "attack_path_inconsistency"
            if deviation > max_dev and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="attack_path_inconsistency",
                    severity=attack_path_inconsistency.get("severity", "warning"),
                    timestamp=ts,
                    current_value=deviation,
                    threshold_value=max_dev,
                    message=f"Cross-version attack path inconsistency: deviation {deviation:.4f} exceeds threshold {max_dev}",
                )
                triggered.append(alert)

        causal_cascading = thresholds.get("causal_cascading_anomaly", {})
        if causal_cascading.get("enabled", False):
            gauges = metrics.get("gauges", {})
            cascade_depth = gauges.get("causal_cascade_max_depth", 0.0)
            max_cascade = causal_cascading.get("max_cascade_depth", 3)
            key = "causal_cascading_anomaly"
            if cascade_depth > max_cascade and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="causal_cascading_anomaly",
                    severity=causal_cascading.get("severity", "warning"),
                    timestamp=ts,
                    current_value=cascade_depth,
                    threshold_value=float(max_cascade),
                    message=f"Cascading anomaly depth {cascade_depth:.0f} exceeds threshold {max_cascade}",
                )
                triggered.append(alert)

        causal_confidence = thresholds.get("causal_confidence_threshold_breach", {})
        if causal_confidence.get("enabled", False):
            gauges = metrics.get("gauges", {})
            mean_conf = gauges.get("causal_root_cause_mean_confidence", 0.0)
            min_conf = causal_confidence.get("min_root_cause_confidence", 0.5)
            key = "causal_confidence_threshold_breach"
            if mean_conf < min_conf and self._can_alert(key, now, cooldown_sec):
                alert = Alert(
                    category="causal_confidence_threshold_breach",
                    severity=causal_confidence.get("severity", "warning"),
                    timestamp=ts,
                    current_value=mean_conf,
                    threshold_value=min_conf,
                    message=f"Root cause mean confidence {mean_conf:.4f} below threshold {min_conf}",
                )
                triggered.append(alert)

        prediction_risk_threshold = thresholds.get("prediction_risk_threshold_breach", {})
        if prediction_risk_threshold.get("enabled", False):
            gauges = metrics.get("gauges", {})
            max_risk = gauges.get("prediction_max_risk", 0.0)
            risk_thresh = prediction_risk_threshold.get("max_risk_score", 0.85)
            key = "prediction_risk_threshold_breach"
            if max_risk > risk_thresh and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="prediction_risk_threshold_breach",
                        severity=prediction_risk_threshold.get("severity", "critical"),
                        timestamp=ts,
                        current_value=max_risk,
                        threshold_value=risk_thresh,
                        message=f"Max forecast risk {max_risk:.4f} exceeds threshold {risk_thresh}",
                    )
                )

        prediction_confidence_collapse = thresholds.get("prediction_confidence_collapse", {})
        if prediction_confidence_collapse.get("enabled", False):
            gauges = metrics.get("gauges", {})
            min_conf_pred = gauges.get("prediction_min_confidence", 1.0)
            min_thresh = prediction_confidence_collapse.get("min_confidence", 0.2)
            key = "prediction_confidence_collapse"
            if min_conf_pred < min_thresh and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="prediction_confidence_collapse",
                        severity=prediction_confidence_collapse.get("severity", "warning"),
                        timestamp=ts,
                        current_value=min_conf_pred,
                        threshold_value=min_thresh,
                        message=f"Min prediction confidence {min_conf_pred:.4f} below threshold {min_thresh}",
                    )
                )

        prediction_drift = thresholds.get("prediction_drift_breach", {})
        if prediction_drift.get("enabled", False):
            gauges = metrics.get("gauges", {})
            drift = gauges.get("prediction_max_drift", 0.0)
            max_drift = prediction_drift.get("max_drift", 0.3)
            key = "prediction_drift_breach"
            if drift > max_drift and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="prediction_drift_breach",
                        severity=prediction_drift.get("severity", "warning"),
                        timestamp=ts,
                        current_value=drift,
                        threshold_value=max_drift,
                        message=f"Prediction drift {drift:.4f} exceeds threshold {max_drift}",
                    )
                )

        prediction_model_degradation = thresholds.get("prediction_model_degradation", {})
        if prediction_model_degradation.get("enabled", False):
            gauges = metrics.get("gauges", {})
            perf = gauges.get("prediction_model_performance", 1.0)
            min_perf = prediction_model_degradation.get("min_performance", 0.6)
            key = "prediction_model_degradation"
            if perf < min_perf and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="prediction_model_degradation",
                        severity=prediction_model_degradation.get("severity", "warning"),
                        timestamp=ts,
                        current_value=perf,
                        threshold_value=min_perf,
                        message=f"Model performance {perf:.4f} below threshold {min_perf}",
                    )
                )

        coherence_collapse = thresholds.get("kernel_coherence_collapse", {})
        if coherence_collapse.get("enabled", False):
            gauges = metrics.get("gauges", {})
            coherence = gauges.get("kernel_coherence_score", 1.0)
            min_coherence = coherence_collapse.get("min_coherence", 0.3)
            key = "kernel_coherence_collapse"
            if coherence < min_coherence and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="kernel_coherence_collapse",
                        severity=coherence_collapse.get("severity", "critical"),
                        timestamp=ts,
                        current_value=coherence,
                        threshold_value=min_coherence,
                        message=f"Kernel coherence {coherence:.4f} below threshold {min_coherence}",
                    )
                )

        safety_violation = thresholds.get("safety_violation_detected", {})
        if safety_violation.get("enabled", False):
            gauges = metrics.get("gauges", {})
            violation_count = gauges.get("safety_violation_count", 0)
            max_allowed = safety_violation.get("max_violations", 5)
            key = "safety_violation_detected"
            if violation_count > max_allowed and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="safety_violation_detected",
                        severity=safety_violation.get("severity", "critical"),
                        timestamp=ts,
                        current_value=float(violation_count),
                        threshold_value=float(max_allowed),
                        message=f"Safety violations {violation_count} exceed max {max_allowed}",
                    )
                )

        governance_breach = thresholds.get("governance_compliance_breach", {})
        if governance_breach.get("enabled", False):
            gauges = metrics.get("gauges", {})
            breach_count = gauges.get("governance_breach_count", 0)
            max_breach = governance_breach.get("max_breaches", 3)
            key = "governance_compliance_breach"
            if breach_count > max_breach and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="governance_compliance_breach",
                        severity=governance_breach.get("severity", "critical"),
                        timestamp=ts,
                        current_value=float(breach_count),
                        threshold_value=float(max_breach),
                        message=f"Governance breaches {breach_count} exceed max {max_breach}",
                    )
                )

        nlp_extraction_failure = thresholds.get("nlp_extraction_failure_spike", {})
        if nlp_extraction_failure.get("enabled", False):
            gauges = metrics.get("gauges", {})
            failure_rate = gauges.get("nlp_extraction_failure_rate", 0.0)
            max_rate = nlp_extraction_failure.get("max_failure_rate", 0.2)
            key = "nlp_extraction_failure_spike"
            if failure_rate > max_rate and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="nlp_extraction_failure_spike",
                        severity=nlp_extraction_failure.get("severity", "warning"),
                        timestamp=ts,
                        current_value=failure_rate,
                        threshold_value=max_rate,
                        message=f"NLP extraction failure rate {failure_rate:.4f} exceeds threshold {max_rate}",
                    )
                )

        nlp_model_load = thresholds.get("nlp_model_load_failure", {})
        if nlp_model_load.get("enabled", False):
            gauges = metrics.get("gauges", {})
            load_fails = gauges.get("nlp_model_load_failures", 0)
            max_fails = nlp_model_load.get("max_load_failures", 3)
            key = "nlp_model_load_failure"
            if load_fails > max_fails and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="nlp_model_load_failure",
                        severity=nlp_model_load.get("severity", "critical"),
                        timestamp=ts,
                        current_value=float(load_fails),
                        threshold_value=float(max_fails),
                        message=f"NLP model load failures {load_fails} exceed threshold {max_fails}",
                    )
                )

        nlp_link_accuracy = thresholds.get("nlp_link_accuracy_degradation", {})
        if nlp_link_accuracy.get("enabled", False):
            gauges = metrics.get("gauges", {})
            accuracy = gauges.get("nlp_link_accuracy", 1.0)
            min_acc = nlp_link_accuracy.get("min_accuracy", 0.5)
            key = "nlp_link_accuracy_degradation"
            if accuracy < min_acc and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="nlp_link_accuracy_degradation",
                        severity=nlp_link_accuracy.get("severity", "warning"),
                        timestamp=ts,
                        current_value=accuracy,
                        threshold_value=min_acc,
                        message=f"NLP link accuracy {accuracy:.4f} below threshold {min_acc}",
                    )
                )

        nlp_class_conf = thresholds.get("nlp_classification_confidence_collapse", {})
        if nlp_class_conf.get("enabled", False):
            gauges = metrics.get("gauges", {})
            confidence = gauges.get("nlp_classification_confidence", 1.0)
            min_conf = nlp_class_conf.get("min_confidence", 0.3)
            key = "nlp_classification_confidence_collapse"
            if confidence < min_conf and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="nlp_classification_confidence_collapse",
                        severity=nlp_class_conf.get("severity", "warning"),
                        timestamp=ts,
                        current_value=confidence,
                        threshold_value=min_conf,
                        message=f"NLP classification confidence {confidence:.4f} below threshold {min_conf}",
                    )
                )

        reasoning_divergence = thresholds.get("reasoning_divergence_detected", {})
        if reasoning_divergence.get("enabled", False):
            gauges = metrics.get("gauges", {})
            divergence = gauges.get("reasoning_divergence", 0.0)
            max_div = reasoning_divergence.get("max_divergence", 0.5)
            key = "reasoning_divergence_detected"
            if divergence > max_div and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="reasoning_divergence_detected",
                        severity=reasoning_divergence.get("severity", "warning"),
                        timestamp=ts,
                        current_value=divergence,
                        threshold_value=max_div,
                        message=f"Reasoning divergence {divergence:.4f} exceeds threshold {max_div}",
                    )
                )

        contradiction_explosion = thresholds.get("contradiction_explosion", {})
        if contradiction_explosion.get("enabled", False):
            gauges = metrics.get("gauges", {})
            contradictions = gauges.get("contradiction_count", 0)
            max_ct = contradiction_explosion.get("max_contradictions", 20)
            key = "contradiction_explosion"
            if contradictions > max_ct and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="contradiction_explosion",
                        severity=contradiction_explosion.get("severity", "critical"),
                        timestamp=ts,
                        current_value=float(contradictions),
                        threshold_value=float(max_ct),
                        message=f"Contradiction count {contradictions} exceeds threshold {max_ct}",
                    )
                )

        learning_instability = thresholds.get("learning_loop_instability", {})
        if learning_instability.get("enabled", False):
            gauges = metrics.get("gauges", {})
            instability = gauges.get("learning_instability", 0.0)
            max_inst = learning_instability.get("max_instability", 0.3)
            key = "learning_loop_instability"
            if instability > max_inst and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="learning_loop_instability",
                        severity=learning_instability.get("severity", "warning"),
                        timestamp=ts,
                        current_value=instability,
                        threshold_value=max_inst,
                        message=f"Learning instability {instability:.4f} exceeds threshold {max_inst}",
                    )
                )

        hypothesis_collapse = thresholds.get("hypothesis_confidence_collapse", {})
        if hypothesis_collapse.get("enabled", False):
            gauges = metrics.get("gauges", {})
            conf = gauges.get("hypothesis_mean_confidence", 1.0)
            min_conf = hypothesis_collapse.get("min_confidence", 0.2)
            key = "hypothesis_confidence_collapse"
            if conf < min_conf and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="hypothesis_confidence_collapse",
                        severity=hypothesis_collapse.get("severity", "warning"),
                        timestamp=ts,
                        current_value=conf,
                        threshold_value=min_conf,
                        message=f"Hypothesis mean confidence {conf:.4f} below threshold {min_conf}",
                    )
                )

        inference_drift = thresholds.get("inference_drift_detected", {})
        if inference_drift.get("enabled", False):
            gauges = metrics.get("gauges", {})
            drift = gauges.get("inference_drift", 0.0)
            max_drift = inference_drift.get("max_drift", 0.15)
            key = "inference_drift_detected"
            if drift > max_drift and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="inference_drift_detected",
                        severity=inference_drift.get("severity", "warning"),
                        timestamp=ts,
                        current_value=drift,
                        threshold_value=max_drift,
                        message=f"Inference drift {drift:.4f} exceeds threshold {max_drift}",
                    )
                )

        agent_deadlock = thresholds.get("agent_deadlock_detected", {})
        if agent_deadlock.get("enabled", False):
            gauges = metrics.get("gauges", {})
            deadlock_count = gauges.get("agent_deadlock_count", 0)
            max_dl = agent_deadlock.get("max_deadlocks", 5)
            key = "agent_deadlock_detected"
            if deadlock_count > max_dl and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="agent_deadlock_detected",
                        severity=agent_deadlock.get("severity", "critical"),
                        timestamp=ts,
                        current_value=float(deadlock_count),
                        threshold_value=float(max_dl),
                        message=f"Agent deadlock count {deadlock_count} exceeds threshold {max_dl}",
                    )
                )

        agent_execution_failure = thresholds.get("agent_execution_failure_spike", {})
        if agent_execution_failure.get("enabled", False):
            gauges = metrics.get("gauges", {})
            failure_rate = gauges.get("agent_execution_failure_rate", 0.0)
            max_rate = agent_execution_failure.get("max_failure_rate", 0.3)
            key = "agent_execution_failure_spike"
            if failure_rate > max_rate and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="agent_execution_failure_spike",
                        severity=agent_execution_failure.get("severity", "critical"),
                        timestamp=ts,
                        current_value=failure_rate,
                        threshold_value=max_rate,
                        message=f"Agent execution failure rate {failure_rate:.4f} exceeds threshold {max_rate}",
                    )
                )

        agent_safety_violation = thresholds.get("agent_safety_violation_surge", {})
        if agent_safety_violation.get("enabled", False):
            gauges = metrics.get("gauges", {})
            violations = gauges.get("agent_safety_violations", 0)
            max_v = agent_safety_violation.get("max_violations", 10)
            key = "agent_safety_violation_surge"
            if violations > max_v and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="agent_safety_violation_surge",
                        severity=agent_safety_violation.get("severity", "critical"),
                        timestamp=ts,
                        current_value=float(violations),
                        threshold_value=float(max_v),
                        message=f"Agent safety violations {violations} exceeds threshold {max_v}",
                    )
                )

        agent_kill_switch_engaged = thresholds.get("agent_kill_switch_engaged", {})
        if agent_kill_switch_engaged.get("enabled", False):
            gauges = metrics.get("gauges", {})
            engaged = gauges.get("agent_kill_switch_engaged", False)
            key = "agent_kill_switch_engaged"
            if engaged and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="agent_kill_switch_engaged",
                        severity=agent_kill_switch_engaged.get("severity", "critical"),
                        timestamp=ts,
                        current_value=1.0,
                        threshold_value=0.0,
                        message="Agent kill switch has been engaged",
                    )
                )

        agent_feedback_drift = thresholds.get("agent_feedback_drift_detected", {})
        if agent_feedback_drift.get("enabled", False):
            gauges = metrics.get("gauges", {})
            drift = gauges.get("agent_feedback_drift", 0.0)
            max_drift = agent_feedback_drift.get("max_drift", 0.2)
            key = "agent_feedback_drift_detected"
            if drift > max_drift and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="agent_feedback_drift_detected",
                        severity=agent_feedback_drift.get("severity", "warning"),
                        timestamp=ts,
                        current_value=drift,
                        threshold_value=max_drift,
                        message=f"Agent feedback drift {drift:.4f} exceeds threshold {max_drift}",
                    )
                )

        agent_simulation_risk = thresholds.get("agent_simulation_risk_breach", {})
        if agent_simulation_risk.get("enabled", False):
            gauges = metrics.get("gauges", {})
            risk = gauges.get("agent_simulation_risk", 0.0)
            max_risk = agent_simulation_risk.get("max_risk", 0.8)
            key = "agent_simulation_risk_breach"
            if risk > max_risk and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="agent_simulation_risk_breach",
                        severity=agent_simulation_risk.get("severity", "warning"),
                        timestamp=ts,
                        current_value=risk,
                        threshold_value=max_risk,
                        message=f"Agent simulation risk {risk:.4f} exceeds threshold {max_risk}",
                    )
                )

        agent_memory_corruption = thresholds.get("agent_memory_corruption_detected", {})
        if agent_memory_corruption.get("enabled", False):
            gauges = metrics.get("gauges", {})
            corruption = gauges.get("agent_memory_corruption", 0.0)
            max_c = agent_memory_corruption.get("max_corruption", 0.1)
            key = "agent_memory_corruption_detected"
            if corruption > max_c and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="agent_memory_corruption_detected",
                        severity=agent_memory_corruption.get("severity", "critical"),
                        timestamp=ts,
                        current_value=corruption,
                        threshold_value=max_c,
                        message=f"Agent memory corruption {corruption:.4f} exceeds threshold {max_c}",
                    )
                )

        for metaintel_key in [
            "reasoning_collapse",
            "cross_phase_inconsistency",
            "execution_reasoning_mismatch",
            "knowledge_corruption",
            "policy_conflict_explosion",
            "autonomous_instability",
            "global_drift_exceeded",
            "architecture_divergence",
        ]:
            mt_threshold = thresholds.get(metaintel_key, {})
            if mt_threshold.get("enabled", False):
                gauges = metrics.get("gauges", {})
                metric_key = mt_threshold.get("metric_key", metaintel_key)
                current = gauges.get(metric_key, 0.0)
                max_val = mt_threshold.get("max", 1.0)
                key = metaintel_key
                if current > max_val and self._can_alert(key, now, cooldown_sec):
                    triggered.append(
                        Alert(
                            category=metaintel_key,
                            severity=mt_threshold.get("severity", "warning"),
                            timestamp=ts,
                            current_value=current,
                            threshold_value=float(max_val),
                            message=f"Meta-intel alert [{metaintel_key}]: {current:.4f} exceeds {max_val}",
                        )
                    )

        for ucos_key in [
            "duplicate_engine_detected",
            "reasoning_divergence",
            "execution_inconsistency",
            "governance_conflict",
            "system_complexity_growth",
            "uncontrolled_self_modification",
        ]:
            ucos_threshold = thresholds.get(ucos_key, {})
            if ucos_threshold.get("enabled", False):
                gauges = metrics.get("gauges", {})
                metric_key = ucos_threshold.get("metric_key", ucos_key)
                current = gauges.get(metric_key, 0.0)
                max_val = ucos_threshold.get("max", 1.0)
                key = ucos_key
                if current > max_val and self._can_alert(key, now, cooldown_sec):
                    triggered.append(
                        Alert(
                            category=ucos_key,
                            severity=ucos_threshold.get("severity", "warning"),
                            timestamp=ts,
                            current_value=current,
                            threshold_value=float(max_val),
                            message=f"UCOS alert [{ucos_key}]: {current:.4f} exceeds {max_val}",
                        )
                    )

        cross_disagreement = thresholds.get("kernel_cross_model_disagreement", {})
        if cross_disagreement.get("enabled", False):
            gauges = metrics.get("gauges", {})
            disagreement = gauges.get("kernel_cross_modality_disagreement", 0.0)
            max_dis = cross_disagreement.get("max_disagreement", 0.4)
            key = "kernel_cross_model_disagreement"
            if disagreement > max_dis and self._can_alert(key, now, cooldown_sec):
                triggered.append(
                    Alert(
                        category="kernel_cross_model_disagreement",
                        severity=cross_disagreement.get("severity", "warning"),
                        timestamp=ts,
                        current_value=disagreement,
                        threshold_value=max_dis,
                        message=f"Kernel model disagreement {disagreement:.4f} exceeds threshold {max_dis}",
                    )
                )

        with self._lock:
            self._alerts.extend(triggered)

        for alert in triggered:
            self._log_alert(alert)
            self._fire_webhook(alert)

        return triggered

    def _can_alert(self, key: str, now: float, cooldown: float) -> bool:
        with self._lock:
            last = self._cooldowns.get(key, 0.0)
            if now - last < cooldown:
                return False
            self._cooldowns[key] = now
            return True

    def _log_alert(self, alert: Alert) -> None:
        logger.warning(
            "ALERT: %s [%s] current=%.2f threshold=%.2f %s",
            alert.category,
            alert.severity,
            alert.current_value,
            alert.threshold_value,
            alert.message,
        )

    def _fire_webhook(self, alert: Alert) -> None:
        webhook_url = self._config.get("webhook_url", "")
        if not webhook_url:
            return
        payload = {
            "category": alert.category,
            "severity": alert.severity,
            "timestamp": alert.timestamp,
            "current_value": alert.current_value,
            "threshold_value": alert.threshold_value,
            "message": alert.message,
        }
        try:
            data = json.dumps(payload).encode()
            req = Request(webhook_url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            resp = urlopen(req, timeout=5)
            logger.debug("webhook sent to %s (status=%d)", webhook_url, resp.status)
        except Exception as exc:
            logger.error("webhook failed for %s: %s", webhook_url, exc)

    def get_alerts(self, category: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            result = [
                {
                    "category": a.category,
                    "severity": a.severity,
                    "timestamp": a.timestamp,
                    "current_value": a.current_value,
                    "threshold_value": a.threshold_value,
                    "message": a.message,
                }
                for a in self._alerts
            ]
        if category:
            result = [a for a in result if a["category"] == category]
        return result[-limit:]


_alert_engine: AlertEngine | None = None


def get_alert_engine(config: dict[str, Any] | None = None) -> AlertEngine:
    global _alert_engine
    if _alert_engine is None:
        _alert_engine = AlertEngine(config)
    return _alert_engine
