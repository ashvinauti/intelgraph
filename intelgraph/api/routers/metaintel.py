from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from intelgraph.api.auth_middleware import require_permission
from intelgraph.core.enterprise import get_metrics as _get_metrics
from intelgraph.core.metaintel import (
    ArchitectureEvolutionEngine,
    GlobalGovernanceEngine,
    GlobalObservabilityDashboard,
    IdentityConsistencyLayer,
    IncidentControlCenter,
    MetaReasoningEngine,
    PolicyEvolutionEngine,
    RealWorldAlignmentLayer,
    SafetyMetaControlLayer,
    SelfImprovementController,
    SystemDiagnostics,
    TruthConsistencyGovernor,
    VersionedSystemState,
)

router = APIRouter(prefix="/metaintel", tags=["Meta-Intelligence"])


def get_governance() -> GlobalGovernanceEngine:
    return GlobalGovernanceEngine()


def get_diagnostics() -> SystemDiagnostics:
    return SystemDiagnostics()


def get_policy() -> PolicyEvolutionEngine:
    return PolicyEvolutionEngine()


def get_metareasoning() -> MetaReasoningEngine:
    return MetaReasoningEngine()


def get_self_improvement() -> SelfImprovementController:
    return SelfImprovementController()


def get_architecture() -> ArchitectureEvolutionEngine:
    return ArchitectureEvolutionEngine()


def get_truth() -> TruthConsistencyGovernor:
    return TruthConsistencyGovernor()


def get_identity() -> IdentityConsistencyLayer:
    return IdentityConsistencyLayer()


def get_alignment() -> RealWorldAlignmentLayer:
    return RealWorldAlignmentLayer()


def get_safety_meta() -> SafetyMetaControlLayer:
    return SafetyMetaControlLayer()


def get_observability() -> GlobalObservabilityDashboard:
    return GlobalObservabilityDashboard()


def get_incident_control() -> IncidentControlCenter:
    return IncidentControlCenter()


def get_state() -> VersionedSystemState:
    return VersionedSystemState()


@router.get("/health", summary="Get global system health status")
async def system_health(
    governance: GlobalGovernanceEngine = Depends(get_governance),
    _=require_permission("metaintel:read"),
):
    health = governance.get_system_health()
    _get_metrics().set_gauge("metaintel_health_score", health["overall_health_score"])
    return health


@router.post("/diagnostics/run", summary="Run system diagnostics on a pipeline stage")
async def run_diagnostics(
    body: dict[str, Any],
    diagnostics: SystemDiagnostics = Depends(get_diagnostics),
    _=require_permission("metaintel:read"),
):
    stage = body.get("pipeline_stage", "")
    metrics = body.get("metrics", {})
    if not stage:
        raise HTTPException(status_code=422, detail="pipeline_stage is required")
    report = diagnostics.run_diagnostics(stage, metrics)
    _get_metrics().set_gauge("metaintel_diagnostic_health", report.health_score)
    return report.to_dict()


@router.post("/policy/generate", summary="Generate a new governance policy")
async def generate_policy(
    body: dict[str, Any],
    policy: PolicyEvolutionEngine = Depends(get_policy),
    _=require_permission("metaintel:admin"),
):
    name = body.get("name", "")
    description = body.get("description", "")
    rules = body.get("rules", [])
    risk_level = body.get("risk_level", "medium")
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    record = policy.generate_policy(name, description, rules, risk_level)
    _get_metrics().set_gauge("metaintel_policy_count", len(policy.get_policies()))
    return record.to_dict()


@router.post("/policy/refine", summary="Auto-refine policy from failure patterns")
async def refine_policy(
    body: dict[str, Any],
    policy: PolicyEvolutionEngine = Depends(get_policy),
    _=require_permission("metaintel:admin"),
):
    base_id = body.get("base_policy_id", "")
    if not base_id:
        raise HTTPException(status_code=422, detail="base_policy_id is required")
    refined = policy.refine_from_failures(base_id)
    if not refined:
        raise HTTPException(status_code=404, detail=f"Policy {base_id} not found")
    return refined.to_dict()


@router.post("/hypothesis/generate", summary="Generate a system-level meta-hypothesis")
async def generate_hypothesis(
    body: dict[str, Any],
    meta: MetaReasoningEngine = Depends(get_metareasoning),
    _=require_permission("metaintel:read"),
):
    observation = body.get("observation", "")
    target_layer = body.get("target_layer", "metaintel")
    evidence = body.get("evidence", [])
    if not observation:
        raise HTTPException(status_code=422, detail="observation is required")
    hypothesis = meta.generate_system_hypothesis(observation, target_layer, evidence)
    return hypothesis.to_dict()


@router.post("/optimization/propose", summary="Propose a system optimization")
async def propose_optimization(
    body: dict[str, Any],
    controller: SelfImprovementController = Depends(get_self_improvement),
    _=require_permission("metaintel:write"),
):
    target = body.get("target", "")
    description = body.get("description", "")
    expected_gain = float(body.get("expected_gain", 0))
    risk = float(body.get("risk", 0))
    if not target or not description:
        raise HTTPException(status_code=422, detail="target and description are required")
    proposal = controller.propose_optimization(target, description, expected_gain, risk)
    _get_metrics().set_gauge("metaintel_optimization_count", len(controller.get_proposals()))
    return proposal.to_dict()


@router.post("/optimization/{proposal_id}/approve", summary="Approve an optimization proposal")
async def approve_optimization(
    proposal_id: str,
    controller: SelfImprovementController = Depends(get_self_improvement),
    _=require_permission("metaintel:admin"),
):
    success = controller.approve_optimization(proposal_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
    return {"proposal_id": proposal_id, "status": "approved"}


@router.post("/architecture/propose", summary="Propose an architecture change")
async def propose_architecture(
    body: dict[str, Any],
    arch: ArchitectureEvolutionEngine = Depends(get_architecture),
    _=require_permission("metaintel:admin"),
):
    description = body.get("description", "")
    action = body.get("action", "")
    target = body.get("target_module", "")
    deps = body.get("new_dependencies", [])
    risk = float(body.get("risk_score", 0.5))
    if not description or not action or not target:
        raise HTTPException(
            status_code=422, detail="description, action, and target_module are required"
        )
    proposal = arch.propose_architecture_change(description, action, target, deps, risk)
    return proposal.to_dict()


@router.post("/architecture/{proposal_id}/apply", summary="Apply an architecture change")
async def apply_architecture(
    proposal_id: str,
    arch: ArchitectureEvolutionEngine = Depends(get_architecture),
    _=require_permission("metaintel:admin"),
):
    success = arch.apply_change(proposal_id)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Proposal {proposal_id} not found or not pending"
        )
    return {"proposal_id": proposal_id, "status": "applied"}


@router.post(
    "/truth/reconcile", summary="Reconcile truth across knowledge, reasoning, and execution"
)
async def reconcile_truth(
    body: dict[str, Any],
    truth: TruthConsistencyGovernor = Depends(get_truth),
    _=require_permission("metaintel:read"),
):
    knowledge = body.get("knowledge_state", {})
    reasoning = body.get("reasoning_state", {})
    execution = body.get("execution_state", {})
    unified = truth.reconcile(knowledge, reasoning, execution)
    snapshot = truth.snapshot(unified)
    return {"unified_state": unified, "snapshot": snapshot.to_dict()}


@router.post("/identity/register", summary="Register an agent identity")
async def register_identity(
    body: dict[str, Any],
    identity: IdentityConsistencyLayer = Depends(get_identity),
    _=require_permission("metaintel:write"),
):
    agent_id = body.get("agent_id", "")
    role = body.get("role", "user")
    capabilities = body.get("capabilities", [])
    scope = body.get("scope", "global")
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id is required")
    record = identity.register_agent(agent_id, role, capabilities, scope)
    return record.to_dict()


@router.post("/alignment/check", summary="Check system alignment with real-world data")
async def check_alignment(
    body: dict[str, Any],
    alignment: RealWorldAlignmentLayer = Depends(get_alignment),
    _=require_permission("metaintel:read"),
):
    system_output = body.get("system_output", {})
    real_world = body.get("real_world_data", {})
    if not system_output or not real_world:
        raise HTTPException(
            status_code=422, detail="system_output and real_world_data are required"
        )
    scores = alignment.compare_output_vs_reality(system_output, real_world)
    drifts = alignment.detect_reality_drift(scores)
    return {
        "scores": [s.to_dict() for s in scores],
        "drifts": drifts,
        "aligned": all(s.aligned for s in scores),
    }


@router.post("/safety/monitor", summary="Monitor a layer for safety incidents")
async def safety_monitor(
    body: dict[str, Any],
    safety: SafetyMetaControlLayer = Depends(get_safety_meta),
    _=require_permission("metaintel:read"),
):
    layer_id = body.get("layer_id", "")
    metrics = body.get("metrics", {})
    if not layer_id:
        raise HTTPException(status_code=422, detail="layer_id is required")
    incidents = safety.monitor_layer(layer_id, metrics)
    return {"incidents": [i.to_dict() for i in incidents], "count": len(incidents)}


@router.post("/safety/kill-switch", summary="Engage or disengage global kill switch")
async def safety_kill_switch(
    body: dict[str, Any],
    safety: SafetyMetaControlLayer = Depends(get_safety_meta),
    _=require_permission("metaintel:admin"),
):
    disengage = body.get("disengage", False)
    if disengage:
        safety.disengage_global_kill_switch()
        return {"status": "kill_switch_disengaged"}
    safety.engage_global_kill_switch()
    return {"status": "kill_switch_engaged"}


@router.get("/observability/dashboard", summary="Get global observability dashboard snapshot")
async def get_dashboard(
    observability: GlobalObservabilityDashboard = Depends(get_observability),
    _=require_permission("metaintel:read"),
):
    latest = observability.get_latest()
    if not latest:
        return {"error": "No dashboard snapshots available"}
    return latest.to_dict()


@router.post("/observability/snapshot", summary="Record an observability dashboard snapshot")
async def record_snapshot(
    body: dict[str, Any],
    observability: GlobalObservabilityDashboard = Depends(get_observability),
    _=require_permission("metaintel:write"),
):
    metrics = body.get("metrics", {})
    snapshot = observability.record_snapshot(metrics)
    return snapshot.to_dict()


@router.get("/alerts", summary="Get meta-intelligence alerts")
async def get_alerts(
    category: str = "",
    limit: int = 100,
    incident: IncidentControlCenter = Depends(get_incident_control),
    _=require_permission("metaintel:read"),
):
    alerts = incident.get_alerts(category or None, limit)
    return {"alerts": [a.to_dict() for a in alerts], "count": len(alerts)}


@router.post("/state/snapshot", summary="Create a full system state snapshot")
async def create_state_snapshot(
    body: dict[str, Any],
    state: VersionedSystemState = Depends(get_state),
    _=require_permission("metaintel:admin"),
):
    layers = body.get("layers", {})
    snapshot = state.snapshot(layers)
    return snapshot.to_dict()


@router.post("/state/restore/{snapshot_id}", summary="Restore system state from snapshot")
async def restore_state(
    snapshot_id: str,
    state: VersionedSystemState = Depends(get_state),
    _=require_permission("metaintel:admin"),
):
    success = state.restore(snapshot_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")
    return {"snapshot_id": snapshot_id, "status": "restored"}


@router.get("/state/integrity", summary="Verify system state integrity")
async def verify_state_integrity(
    state: VersionedSystemState = Depends(get_state),
    _=require_permission("metaintel:read"),
):
    valid = state.verify_integrity()
    return {"valid": valid, "snapshot_count": len(state.get_timeline())}
