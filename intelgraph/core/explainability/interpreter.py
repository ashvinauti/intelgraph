from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from typing import Any

from intelgraph.core.graph.prediction import PredictionResult

EXPLAINABILITY_SCHEMA_VERSION = "1.0"


@dataclass
class FeatureContribution:
    feature_name: str
    raw_value: float
    contribution: float
    direction: str
    importance_percentile: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "raw_value": round(self.raw_value, 4),
            "contribution": round(self.contribution, 4),
            "direction": self.direction,
            "importance_percentile": round(self.importance_percentile, 4),
        }


@dataclass
class PredictionExplanation:
    explanation_id: str
    entity_id: str
    prediction_type: str
    top_contributions: list[FeatureContribution]
    summary: str
    confidence: float
    uncertainty: float
    model_fidelity: float
    timestamp: float = 0.0
    schema_version: str = EXPLAINABILITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "explanation_id": self.explanation_id,
            "entity_id": self.entity_id,
            "prediction_type": self.prediction_type,
            "top_contributions": [c.to_dict() for c in self.top_contributions],
            "summary": self.summary,
            "confidence": round(self.confidence, 4),
            "uncertainty": round(self.uncertainty, 4),
            "model_fidelity": round(self.model_fidelity, 4),
            "timestamp": self.timestamp or time.time(),
            "schema_version": self.schema_version,
        }


class FeatureImportance:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    def compute_importance(
        self,
        features: dict[str, float],
        contributions: dict[str, float],
        top_n: int = 5,
    ) -> list[FeatureContribution]:
        if not contributions:
            return []
        sorted_items = sorted(contributions.items(), key=lambda x: -abs(x[1]))
        total_abs = sum(abs(v) for v in contributions.values()) or 1.0
        result: list[FeatureContribution] = []
        for _i, (name, contribution) in enumerate(sorted_items[:top_n]):
            raw = features.get(name, 0.0)
            direction = "positive" if contribution >= 0 else "negative"
            importance_pct = abs(contribution) / total_abs
            result.append(
                FeatureContribution(
                    feature_name=name,
                    raw_value=raw,
                    contribution=contribution,
                    direction=direction,
                    importance_percentile=importance_pct,
                )
            )
        return result

    def global_importance(
        self,
        all_predictions: list[dict[str, Any]],
        top_n: int = 10,
    ) -> dict[str, float]:
        accum: dict[str, float] = {}
        for pred in all_predictions:
            contribs = pred.get("contributions", {})
            for k, v in contribs.items():
                accum[k] = accum.get(k, 0.0) + abs(v)
        sorted_items = sorted(accum.items(), key=lambda x: -x[1])
        return dict(sorted_items[:top_n])


@dataclass
class ModelInterpretabilityReport:
    report_id: str
    model_name: str
    prediction_count: int
    top_features: dict[str, float]
    average_confidence: float
    average_uncertainty: float
    feature_stability: dict[str, float]
    timestamp: float = 0.0
    schema_version: str = EXPLAINABILITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "model_name": self.model_name,
            "prediction_count": self.prediction_count,
            "top_features": {k: round(v, 4) for k, v in self.top_features.items()},
            "average_confidence": round(self.average_confidence, 4),
            "average_uncertainty": round(self.average_uncertainty, 4),
            "feature_stability": {k: round(v, 4) for k, v in self.feature_stability.items()},
            "timestamp": self.timestamp or time.time(),
            "schema_version": self.schema_version,
        }


class ModelInterpreter:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    def generate_report(
        self,
        model_name: str,
        predictions: list[PredictionResult | dict[str, Any]],
    ) -> ModelInterpretabilityReport:
        n = len(predictions)
        if n == 0:
            return ModelInterpretabilityReport(
                report_id=self._generate_id(),
                model_name=model_name,
                prediction_count=0,
                top_features={},
                average_confidence=0.0,
                average_uncertainty=0.0,
                feature_stability={},
            )
        confs: list[float] = []
        uncs: list[float] = []
        all_contribs: list[dict[str, float]] = []
        for p in predictions:
            if isinstance(p, dict):
                confs.append(p.get("confidence", 0.0))
                uncs.append(p.get("uncertainty", 0.0))
                all_contribs.append(p.get("contributions", {}))
            else:
                confs.append(getattr(p, "confidence", 0.0))
                uncs.append(getattr(p, "uncertainty", 0.0))
                all_contribs.append(getattr(p, "contributions", {}))
        avg_conf = sum(confs) / n
        avg_unc = sum(uncs) / n
        fi = FeatureImportance(self._config)
        global_imp = fi.global_importance(
            [{"contributions": c} for c in all_contribs],
            top_n=10,
        )
        stability: dict[str, float] = {}
        feature_values: dict[str, list[float]] = {}
        for contrib in all_contribs:
            for k, v in contrib.items():
                feature_values.setdefault(k, []).append(v)
        for k, vals in feature_values.items():
            if len(vals) > 1:
                mean = sum(vals) / len(vals)
                variance = sum((v - mean) ** 2 for v in vals) / len(vals)
                stability[k] = 1.0 - min(math.sqrt(variance) / max(abs(mean), 1e-10), 1.0)
            else:
                stability[k] = 1.0
        return ModelInterpretabilityReport(
            report_id=self._generate_id(),
            model_name=model_name,
            prediction_count=n,
            top_features=global_imp,
            average_confidence=avg_conf,
            average_uncertainty=avg_unc,
            feature_stability=stability,
        )

    def _generate_id(self) -> str:
        return f"mir_{uuid.uuid4().hex[:12]}"


class CounterfactualExplainer:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    def minimal_change(
        self,
        current_features: dict[str, float],
        target_value: float,
        current_value: float,
        feature_bounds: dict[str, tuple[float, float]] | None = None,
        max_iterations: int = 100,
    ) -> list[dict[str, Any]]:
        if not current_features:
            return []
        needed_change = target_value - current_value
        if abs(needed_change) < 1e-6:
            return [{"message": "already at target", "changes": {}}]
        candidates: list[dict[str, Any]] = []
        for feat_name, feat_val in current_features.items():
            bounds = feature_bounds.get(feat_name, (0.0, 1.0)) if feature_bounds else (0.0, 1.0)
            min_b, max_b = bounds
            for direction in [1.0, -1.0]:
                delta = direction * 0.1
                new_val = feat_val + delta
                if new_val < min_b or new_val > max_b:
                    continue
                impact = delta * needed_change / max(abs(feat_val), 1e-10)
                candidates.append(
                    {
                        "feature": feat_name,
                        "current_value": round(feat_val, 4),
                        "suggested_value": round(new_val, 4),
                        "delta": round(delta, 4),
                        "estimated_impact": round(impact, 4),
                        "direction": "increase" if delta > 0 else "decrease",
                    }
                )
        candidates.sort(key=lambda x: -abs(x["estimated_impact"]))
        return candidates[:5]

    def what_if_summary(
        self,
        feature_name: str,
        current_value: float,
        suggested_value: float,
        forecast_value_before: float,
        forecast_value_after: float,
    ) -> dict[str, Any]:
        delta = suggested_value - current_value
        impact = forecast_value_after - forecast_value_before
        return {
            "feature": feature_name,
            "current_value": round(current_value, 4),
            "suggested_value": round(suggested_value, 4),
            "delta": round(delta, 4),
            "forecast_before": round(forecast_value_before, 4),
            "forecast_after": round(forecast_value_after, 4),
            "impact": round(impact, 4),
            "impact_direction": (
                "increase" if impact > 0 else "decrease" if impact < 0 else "neutral"
            ),
        }
