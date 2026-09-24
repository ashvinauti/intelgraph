from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from intelgraph.core.features.store import get_feature_store
from intelgraph.core.graph.prediction import Predictor
from intelgraph.core.kernel.execution import UnifiedExecutionKernel, build_graph_from_container
from intelgraph.core.models.registry import get_model_registry

router = APIRouter(prefix="/graph/prediction", tags=["graph"])


@router.post("/forecast", summary="Full multi-horizon forecast for a node")
def forecast_node(body: dict[str, Any]):
    node_id = body.get("node_id", "")
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required")
    graph = build_graph_from_container()
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    predictor = Predictor(graph)
    body.get("horizon", 1)
    communities = body.get("communities")
    result = predictor.full_forecast(node_id, communities)
    return result


@router.get("/risk/{node_id}", summary="Risk forecast for a node")
def risk_forecast(node_id: str, horizon: int = 1):
    if horizon < 0 or horizon > 2:
        raise HTTPException(
            status_code=400, detail="horizon must be 0 (short), 1 (medium), or 2 (long)"
        )
    graph = build_graph_from_container()
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    predictor = Predictor(graph)
    result = predictor.risk_forecast(node_id, horizon)
    return result.to_dict()


@router.get("/trend/{node_id}", summary="Temporal trend forecast for a node")
def trend_forecast(node_id: str, horizon: int = 1):
    graph = build_graph_from_container()
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    predictor = Predictor(graph)
    result = predictor.temporal_trend(node_id, horizon)
    return result.to_dict()


@router.get("/influence-trajectory/{node_id}", summary="Influence trajectory forecast")
def influence_trajectory(node_id: str, horizon: int = 1):
    graph = build_graph_from_container()
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    predictor = Predictor(graph)
    result = predictor.influence_trajectory(node_id, horizon)
    return result.to_dict()


@router.get("/anomaly-likelihood/{node_id}", summary="Anomaly likelihood prediction")
def anomaly_likelihood(node_id: str, horizon: int = 1):
    graph = build_graph_from_container()
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    predictor = Predictor(graph)
    result = predictor.anomaly_likelihood(node_id, horizon)
    return result.to_dict()


@router.get("/attack-path-probability/{node_id}", summary="Attack path probability forecast")
def attack_path_probability(node_id: str, horizon: int = 1):
    graph = build_graph_from_container()
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    predictor = Predictor(graph)
    result = predictor.attack_path_probability(node_id, horizon)
    return result.to_dict()


@router.post("/counterfactual", summary="What-if counterfactual risk estimation")
def counterfactual_estimate(body: dict[str, Any]):
    node_id = body.get("node_id", "")
    what_if = body.get("what_if", {})
    if not node_id or not what_if:
        raise HTTPException(status_code=400, detail="node_id and what_if are required")
    graph = build_graph_from_container()
    if node_id not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    predictor = Predictor(graph)
    result = predictor.counterfactual(node_id, what_if)
    return result.to_dict()


@router.post("/execute", summary="Execute unified intelligence kernel (Phases 24-27 orchestration)")
def execute_kernel(body: dict[str, Any]):
    anomaly_node = body.get("anomaly_node")
    enable_anomaly = body.get("enable_anomaly", True)
    enable_causal = body.get("enable_causal", True)
    enable_prediction = body.get("enable_prediction", True)
    horizon = body.get("horizon", 1)
    graph = build_graph_from_container()
    kernel = UnifiedExecutionKernel(graph)
    result = kernel.execute(anomaly_node, enable_anomaly, enable_causal, enable_prediction, horizon)
    return result


@router.get("/models", summary="List registered prediction models")
def list_models():
    registry = get_model_registry()
    return registry.snapshot()


@router.get("/features/{node_id}", summary="Get feature store state for a node")
def get_features(node_id: str):
    store = get_feature_store()
    features = store.get_all(node_id)
    quality = store.data_quality_score(node_id)
    return {
        "entity_id": node_id,
        "features": [
            {"name": f.name, "value": f.value, "freshness": f.freshness_score()} for f in features
        ],
        "data_quality_score": quality,
        "stale_features": store.detect_stale(node_id),
    }


@router.post("/explain", summary="Explain a prediction with feature importance")
def explain_prediction(body: dict[str, Any]):
    from intelgraph.core.explainability.interpreter import FeatureImportance

    fi = FeatureImportance()
    features = body.get("features", {})
    contributions = body.get("contributions", {})
    top_n = body.get("top_n", 5)
    result = fi.compute_importance(features, contributions, top_n)
    return {"feature_importance": [e.to_dict() for e in result]}


@router.post("/safety-check", summary="Check prediction against safety constraints")
def safety_check(body: dict[str, Any]):
    from intelgraph.core.safety.guard import SafetyGuard

    guard = SafetyGuard(
        bounds=body.get("bounds", {}),
        fallbacks={
            pt: body.get("fallback_default", 0.0) for pt in body.get("prediction_types", [])
        },
    )
    result = guard.check_prediction(
        prediction_type=body.get("prediction_type", "risk_forecast"),
        value=body.get("value", 0.0),
    )
    return result.to_dict()


@router.post("/compliance", summary="Check prediction compliance")
def compliance_check(body: dict[str, Any]):
    from intelgraph.core.governance.policy import ComplianceChecker

    checker = ComplianceChecker(body.get("rules", {}))
    result = checker.check(
        prediction_type=body.get("prediction_type", "risk_forecast"),
        value=body.get("value", 0.0),
        entity_risk=body.get("entity_risk", 0.0),
    )
    return result.to_dict()


@router.post("/approval", summary="Request approval for high-risk prediction")
def request_approval(body: dict[str, Any]):
    from intelgraph.core.governance.policy import ApprovalWorkflow

    wf = ApprovalWorkflow(
        risk_threshold=body.get("risk_threshold", 0.7),
        auto_approve_low_risk=body.get("auto_approve_low_risk", True),
    )
    req = wf.request_approval(
        prediction_type=body.get("prediction_type", "risk_forecast"),
        entity_id=body.get("entity_id", ""),
        value=body.get("value", 0.0),
        risk_score=body.get("risk_score", 0.0),
        justification=body.get("justification", ""),
    )
    return req.to_dict()


@router.get("/audit", summary="Query audit trail")
def query_audit(entity_id: str | None = None, action: str | None = None, limit: int = 100):
    from intelgraph.core.governance.policy import AuditTrail

    trail = AuditTrail()
    entries = trail.query(entity_id=entity_id, action=action, limit=limit)
    return {"entries": [e.to_dict() for e in entries], "count": len(entries)}


@router.get("/model-report", summary="Generate model interpretability report")
def model_report(model_name: str = "default"):
    from intelgraph.core.explainability.interpreter import ModelInterpreter

    interp = ModelInterpreter()
    report = interp.generate_report(model_name, [])
    return report.to_dict()
