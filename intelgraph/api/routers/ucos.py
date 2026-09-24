from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from intelgraph.api.auth_middleware import require_permission
from intelgraph.core.enterprise import get_metrics as _get_metrics
from intelgraph.core.ucos import (
    ClosedLoopIntelligenceSystem,
    ConsolidationEngine,
    DependencyValidator,
    GlobalHealthIndex,
    SelfStabilizingMetaControl,
    SimplificationEngine,
    SingleSourceOfTruth,
    UnifiedAlertingCore,
    UnifiedCognitiveCore,
    UnifiedExecutionRuntime,
    UnifiedPolicyControlPlane,
    UnifiedSafetyLayer,
    UnifiedTelemetryCore,
    UnifiedTruthEngine,
)

router = APIRouter(prefix="/system", tags=["UCOS"])


def get_consolidation() -> ConsolidationEngine:
    return ConsolidationEngine()


def get_cognitive() -> UnifiedCognitiveCore:
    return UnifiedCognitiveCore()


def get_closed_loop() -> ClosedLoopIntelligenceSystem:
    return ClosedLoopIntelligenceSystem()


def get_policy() -> UnifiedPolicyControlPlane:
    return UnifiedPolicyControlPlane()


def get_truth() -> UnifiedTruthEngine:
    return UnifiedTruthEngine()


def get_runtime() -> UnifiedExecutionRuntime:
    return UnifiedExecutionRuntime()


def get_telemetry() -> UnifiedTelemetryCore:
    return UnifiedTelemetryCore()


def get_safety() -> UnifiedSafetyLayer:
    return UnifiedSafetyLayer()


def get_meta_control() -> SelfStabilizingMetaControl:
    return SelfStabilizingMetaControl()


def get_simplification() -> SimplificationEngine:
    return SimplificationEngine()


def get_health() -> GlobalHealthIndex:
    return GlobalHealthIndex()


def get_alerting() -> UnifiedAlertingCore:
    return UnifiedAlertingCore()


def get_dependency() -> DependencyValidator:
    return DependencyValidator()


def get_state() -> SingleSourceOfTruth:
    return SingleSourceOfTruth()


@router.post("/query", summary="Query the unified knowledge state")
async def system_query(
    body: dict[str, Any],
    state: SingleSourceOfTruth = Depends(get_state),
    truth: UnifiedTruthEngine = Depends(get_truth),
    _=require_permission("ucos:read"),
):
    key = body.get("key", "")
    if key:
        entry = state.get(key)
        truth_entry = truth.read(key)
        return {"state_entry": entry.to_dict() if entry else None, "truth_entry": truth_entry}
    return {"state": {k: v.to_dict() for k, v in state.get_all().items()}, "truth": truth.query()}


@router.post("/reason", summary="Execute unified reasoning query")
async def system_reason(
    body: dict[str, Any],
    cognitive: UnifiedCognitiveCore = Depends(get_cognitive),
    _=require_permission("ucos:read"),
):
    query = body.get("query", "")
    context = body.get("context", {})
    if not query:
        raise HTTPException(status_code=422, detail="query is required")
    result = cognitive.reason(query, context)
    _get_metrics().set_gauge("ucos_reasoning_confidence", result.total_confidence)
    _get_metrics().set_gauge("ucos_reasoning_latency", result.duration_ms)
    return result.to_dict()


@router.post("/act", summary="Execute an action through the unified runtime")
async def system_act(
    body: dict[str, Any],
    runtime: UnifiedExecutionRuntime = Depends(get_runtime),
    policy: UnifiedPolicyControlPlane = Depends(get_policy),
    safety: UnifiedSafetyLayer = Depends(get_safety),
    _=require_permission("ucos:write"),
):
    goal = body.get("goal", "")
    steps = body.get("steps")
    if not goal:
        raise HTTPException(status_code=422, detail="goal is required")
    risk = body.get("risk", 0.5)
    decision = policy.evaluate("act", risk)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=f"Policy denied: {decision.reason}")
    safety_check = safety.check_safety({"type": "act", "risk": risk})
    if not safety_check["safe"]:
        raise HTTPException(status_code=403, detail=f"Safety denied: {safety_check['reason']}")
    result = runtime.execute(goal, steps)
    _get_metrics().set_gauge("ucos_execution_success", 1.0 if result.success else 0.0)
    return result.to_dict()


@router.post("/observe", summary="Record a telemetry observation")
async def system_observe(
    body: dict[str, Any],
    telemetry: UnifiedTelemetryCore = Depends(get_telemetry),
    _=require_permission("ucos:read"),
):
    reasoning_quality = float(body.get("reasoning_quality", 0.5))
    execution_success = bool(body.get("execution_success", True))
    latency_ms = float(body.get("latency_ms", 0))
    drift = float(body.get("drift", 0))
    pipelines = int(body.get("active_pipelines", 0))
    snapshot = telemetry.record(reasoning_quality, execution_success, latency_ms, drift, pipelines)
    return snapshot.to_dict()


@router.post("/policy/evaluate", summary="Evaluate a policy decision")
async def system_policy_evaluate(
    body: dict[str, Any],
    policy: UnifiedPolicyControlPlane = Depends(get_policy),
    _=require_permission("ucos:read"),
):
    action_type = body.get("action_type", "")
    risk = float(body.get("risk", 0))
    role = body.get("role", "user")
    if not action_type:
        raise HTTPException(status_code=422, detail="action_type is required")
    decision = policy.evaluate(action_type, risk, role)
    return decision.to_dict()


@router.post("/policy/override", summary="Override a policy decision")
async def system_policy_override(
    body: dict[str, Any],
    policy: UnifiedPolicyControlPlane = Depends(get_policy),
    _=require_permission("ucos:admin"),
):
    decision_id = body.get("decision_id", "")
    reason = body.get("reason", "")
    if not decision_id:
        raise HTTPException(status_code=422, detail="decision_id is required")
    success = policy.override_decision(decision_id, reason)
    if not success:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    return {"decision_id": decision_id, "status": "overridden", "reason": reason}


@router.get("/state", summary="Get unified system state")
async def system_state(
    state: SingleSourceOfTruth = Depends(get_state),
    _=require_permission("ucos:read"),
):
    return {
        "entries": {k: v.to_dict() for k, v in state.get_all().items()},
        "count": len(state.get_all()),
    }


@router.post("/state/set", summary="Set a value in the unified state")
async def system_state_set(
    body: dict[str, Any],
    state: SingleSourceOfTruth = Depends(get_state),
    truth: UnifiedTruthEngine = Depends(get_truth),
    _=require_permission("ucos:write"),
):
    key = body.get("key", "")
    value = body.get("value")
    source = body.get("source", "ucos")
    confidence = float(body.get("confidence", 0.5))
    if not key:
        raise HTTPException(status_code=422, detail="key is required")
    state_result = state.set(key, value, source, confidence)
    truth.write(key, value, source, confidence)
    return {"state_result": state_result}


@router.post("/state/snapshot", summary="Create a system state snapshot")
async def system_state_snapshot(
    state: SingleSourceOfTruth = Depends(get_state),
    _=require_permission("ucos:admin"),
):
    snap = state.snapshot()
    return snap


@router.post("/consolidation/scan", summary="Scan for duplicate engines and consolidation plan")
async def consolidation_scan(
    engine: ConsolidationEngine = Depends(get_consolidation),
    _=require_permission("ucos:admin"),
):
    plan = engine.consolidation_plan()
    _get_metrics().set_gauge("ucos_duplicates_found", plan["duplicates_found"])
    return plan


@router.post("/consolidation/apply", summary="Apply simplification rules")
async def consolidation_apply(
    sim: SimplificationEngine = Depends(get_simplification),
    _=require_permission("ucos:admin"),
):
    dups = sim.check_no_duplicates()
    owners = sim.check_single_owner()
    complexity = sim.compute_system_complexity()
    return {
        "duplicate_violations": dups,
        "owner_violations": owners,
        "complexity_index": round(complexity, 4),
        "complexity_decreasing": sim.is_complexity_decreasing(),
    }


@router.get("/health", summary="Get global system health index")
async def system_health(
    health: GlobalHealthIndex = Depends(get_health),
    telemetry: UnifiedTelemetryCore = Depends(get_telemetry),
    _=require_permission("ucos:read"),
):
    tel = telemetry.get_latest()
    result = health.compute(
        cognitive=tel.reasoning_quality if tel else 0.5,
        execution=tel.execution_success_rate if tel else 0.5,
        policy=0.8,
    )
    _get_metrics().set_gauge("ucos_global_health", result["overall_health"])
    return result


@router.post("/closed-loop", summary="Execute a closed-loop intelligence cycle")
async def closed_loop(
    body: dict[str, Any],
    loop: ClosedLoopIntelligenceSystem = Depends(get_closed_loop),
    cognitive: UnifiedCognitiveCore = Depends(get_cognitive),
    runtime: UnifiedExecutionRuntime = Depends(get_runtime),
    _=require_permission("ucos:write"),
):
    query = body.get("query", "")
    steps = body.get("steps")
    input_data = body.get("input", {})
    if not query:
        raise HTTPException(status_code=422, detail="query is required")
    reasoning = cognitive.reason(query, body.get("context", {}))
    execution = runtime.execute(query, steps)
    observation = body.get("observation", {})
    entry = loop.run_cycle(input_data, reasoning.to_dict(), execution.to_dict(), observation)
    _get_metrics().set_gauge("ucos_cycle_success", 1.0 if entry.success else 0.0)
    return entry.to_dict()


@router.post("/safety/check", summary="Check safety of an action")
async def safety_check(
    body: dict[str, Any],
    safety: UnifiedSafetyLayer = Depends(get_safety),
    _=require_permission("ucos:read"),
):
    action = body.get("action", {})
    return safety.check_safety(action)


@router.post("/safety/kill-switch", summary="Toggle global kill switch")
async def safety_kill_switch(
    body: dict[str, Any],
    safety: UnifiedSafetyLayer = Depends(get_safety),
    _=require_permission("ucos:admin"),
):
    if body.get("disengage", False):
        safety.disengage_kill_switch()
        return {"status": "kill_switch_disengaged"}
    safety.engage_kill_switch()
    return {"status": "kill_switch_engaged"}


@router.get("/alerts", summary="Get unified system alerts")
async def system_alerts(
    category: str = "",
    limit: int = 100,
    alerting: UnifiedAlertingCore = Depends(get_alerting),
    _=require_permission("ucos:read"),
):
    alerts = alerting.get_alerts(category or None, limit)
    return {"alerts": alerts, "count": len(alerts)}


@router.post("/dependency/register", summary="Register a module dependency")
async def dependency_register(
    body: dict[str, Any],
    dep: DependencyValidator = Depends(get_dependency),
    _=require_permission("ucos:admin"),
):
    module_id = body.get("module_id", "")
    dependencies = body.get("dependencies", [])
    if not module_id:
        raise HTTPException(status_code=422, detail="module_id is required")
    dep.register_module(module_id, dependencies)
    cycles = dep.validate_no_circular()
    return {"module_id": module_id, "dependencies": dependencies, "cycles": cycles}


@router.post("/simplify/check", summary="Check system for simplification violations")
async def simplify_check(
    sim: SimplificationEngine = Depends(get_simplification),
    _=require_permission("ucos:read"),
):
    dups = sim.check_no_duplicates()
    return {
        "duplicate_violations": dups,
        "complexity_index": round(sim.compute_system_complexity(), 4),
        "is_complexity_decreasing": sim.is_complexity_decreasing(),
    }


@router.post("/meta-control/propose", summary="Propose a controlled system change")
async def meta_propose(
    body: dict[str, Any],
    meta: SelfStabilizingMetaControl = Depends(get_meta_control),
    _=require_permission("ucos:admin"),
):
    description = body.get("description", "")
    target = body.get("target", "")
    change_type = body.get("change_type", "config")
    risk = float(body.get("risk", 0.5))
    if not description or not target:
        raise HTTPException(status_code=422, detail="description and target are required")
    proposal = meta.propose_change(description, target, change_type, risk)
    return proposal
