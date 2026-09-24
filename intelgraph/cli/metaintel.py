from __future__ import annotations

import json
import sys
from typing import Any

import click

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


@click.group(name="metaintel")
def metaintel_group() -> None:
    """Meta-intelligence, self-governance, and system control."""


@metaintel_group.command("health")
def health() -> None:
    """Show global system health."""
    gov = GlobalGovernanceEngine()
    _print_json(gov.get_system_health())


@metaintel_group.command("diagnose")
@click.argument("pipeline-stage", type=str)
@click.option("--latency-ms", type=float, default=0, help="Pipeline latency in ms")
@click.option("--error-rate", type=float, default=0, help="Error rate")
def diagnose(pipeline_stage: str, latency_ms: float, error_rate: float) -> None:
    """Run diagnostics on a pipeline stage."""
    diag = SystemDiagnostics()
    metrics = {"latency_ms": latency_ms, "error_rate": error_rate}
    report = diag.run_diagnostics(pipeline_stage, metrics)
    _print_json(report.to_dict())


@metaintel_group.command("policy")
@click.option("--generate", "do_generate", is_flag=True, help="Generate new policy")
@click.option("--name", default="auto_policy", help="Policy name")
@click.option("--description", default="", help="Policy description")
def policy(do_generate: bool, name: str, description: str) -> None:
    """Manage governance policies."""
    engine = PolicyEvolutionEngine()
    if do_generate:
        record = engine.generate_policy(
            name, description, [{"action": "block", "condition": "risk > 0.7"}]
        )
        _print_json(record.to_dict())
    else:
        policies = engine.get_policies()
        _print_json([p.to_dict() for p in policies])


@metaintel_group.command("hypothesis")
@click.argument("observation", type=str)
@click.option("--target-layer", default="metaintel", help="Target layer")
def hypothesis(observation: str, target_layer: str) -> None:
    """Generate a system-level meta-hypothesis."""
    meta = MetaReasoningEngine()
    h = meta.generate_system_hypothesis(observation, target_layer)
    _print_json(h.to_dict())


@metaintel_group.command("optimize")
@click.option("--propose", "do_propose", is_flag=True, help="Propose optimization")
@click.option("--target", default="", help="Optimization target")
@click.option("--description", default="", help="Optimization description")
@click.option("--expected-gain", type=float, default=0.1, help="Expected gain")
@click.option("--risk", type=float, default=0.3, help="Risk score")
def optimize(
    do_propose: bool, target: str, description: str, expected_gain: float, risk: float
) -> None:
    """Propose and manage system optimizations."""
    ctrl = SelfImprovementController()
    if do_propose:
        if not target or not description:
            click.echo("--target and --description are required", err=True)
            sys.exit(1)
        prop = ctrl.propose_optimization(target, description, expected_gain, risk)
        _print_json(prop.to_dict())
    else:
        proposals = ctrl.get_proposals()
        _print_json([p.to_dict() for p in proposals])


@metaintel_group.command("architecture")
@click.option("--propose", "do_propose", is_flag=True, help="Propose architecture change")
@click.option(
    "--action",
    type=click.Choice(["add_module", "remove_module", "modify_dependencies"]),
    help="Action type",
)
@click.option("--target", default="", help="Target module")
@click.option("--description", default="", help="Change description")
def architecture(do_propose: bool, action: str, target: str, description: str) -> None:
    """Manage system architecture evolution."""
    arch = ArchitectureEvolutionEngine()
    if do_propose:
        if not action or not target:
            click.echo("--action and --target are required", err=True)
            sys.exit(1)
        prop = arch.propose_architecture_change(description or f"{action} {target}", action, target)
        _print_json(prop.to_dict())
    else:
        modules = arch.get_modules()
        _print_json([m.to_dict() for m in modules])


@metaintel_group.command("truth")
@click.option("--reconcile", "do_reconcile", is_flag=True, help="Reconcile truth across layers")
def truth(do_reconcile: bool) -> None:
    """Manage truth consistency."""
    t = TruthConsistencyGovernor()
    if do_reconcile:
        unified = t.reconcile(
            {"key": "value", "key_confidence": 0.8}, {"key": "value2", "key_confidence": 0.6}, {}
        )
        snap = t.snapshot(unified)
        _print_json({"unified": unified, "snapshot": snap.to_dict()})
    else:
        snaps = t.get_snapshots()
        _print_json([s.to_dict() for s in snaps])


@metaintel_group.command("identity")
@click.option("--register", "do_register", is_flag=True, help="Register agent identity")
@click.option("--agent-id", default="", help="Agent ID")
@click.option("--role", default="user", help="Role")
def identity(do_register: bool, agent_id: str, role: str) -> None:
    """Manage agent identities."""
    id_layer = IdentityConsistencyLayer()
    if do_register:
        if not agent_id:
            click.echo("--agent-id is required", err=True)
            sys.exit(1)
        rec = id_layer.register_agent(agent_id, role, ["default"])
        _print_json(rec.to_dict())
    else:
        ids = id_layer.list_identities()
        _print_json([i.to_dict() for i in ids])


@metaintel_group.command("alignment")
@click.option("--check", "do_check", is_flag=True, help="Check alignment")
@click.option("--output", default="{}", help="System output JSON")
@click.option("--reality", default="{}", help="Real-world data JSON")
def alignment(do_check: bool, output: str, reality: str) -> None:
    """Check real-world alignment."""
    al = RealWorldAlignmentLayer()
    if do_check:
        try:
            sys_out = json.loads(output)
            real = json.loads(reality)
        except json.JSONDecodeError:
            click.echo("Invalid JSON in --output or --reality", err=True)
            sys.exit(1)
        scores = al.compare_output_vs_reality(sys_out, real)
        _print_json([s.to_dict() for s in scores])
    else:
        scores = al.get_alignment_scores()
        _print_json([s.to_dict() for s in scores])


@metaintel_group.command("safety")
@click.option("--monitor", "do_monitor", is_flag=True, help="Monitor a layer")
@click.option("--layer", default="", help="Layer ID")
@click.option("--kill-switch", "do_kill", is_flag=True, help="Toggle global kill switch")
def safety(do_monitor: bool, layer: str, do_kill: bool) -> None:
    """Monitor system safety."""
    sm = SafetyMetaControlLayer()
    if do_kill:
        if sm.is_system_safe():
            sm.engage_global_kill_switch()
            click.echo("Kill switch engaged")
        else:
            sm.disengage_global_kill_switch()
            click.echo("Kill switch disengaged")
    elif do_monitor:
        if not layer:
            click.echo("--layer is required", err=True)
            sys.exit(1)
        incidents = sm.monitor_layer(layer, {"error_rate": 0.1, "anomaly_count": 5})
        _print_json([i.to_dict() for i in incidents])
    else:
        incidents = sm.get_incidents()
        _print_json([i.to_dict() for i in incidents])


@metaintel_group.command("dashboard")
def dashboard() -> None:
    """Show observability dashboard."""
    obs = GlobalObservabilityDashboard()
    latest = obs.get_latest()
    if latest:
        _print_json(latest.to_dict())
    else:
        click.echo("No dashboard data available. Use 'metaintel snapshot' to record.", err=True)


@metaintel_group.command("snapshot")
@click.option("--reasoning", type=float, default=0.8, help="Reasoning quality score")
@click.option("--execution", type=float, default=0.8, help="Execution reliability score")
@click.option("--consistency", type=float, default=0.8, help="Knowledge consistency score")
def snapshot(reasoning: float, execution: float, consistency: float) -> None:
    """Record an observability snapshot."""
    obs = GlobalObservabilityDashboard()
    snap = obs.record_snapshot(
        {
            "reasoning_quality": reasoning,
            "execution_reliability": execution,
            "knowledge_consistency": consistency,
            "system_drift": 0.0,
            "cross_phase_alignment": 0.8,
            "stability_index": 0.8,
            "governance_conflict_rate": 0.0,
            "improvement_velocity": 0.0,
            "architecture_mutation_rate": 0.0,
        }
    )
    _print_json(snap.to_dict())


@metaintel_group.command("alerts")
@click.option("--category", default="", help="Filter by category")
def alerts(category: str) -> None:
    """Show meta-intelligence alerts."""
    icc = IncidentControlCenter()
    alerts_list = icc.get_alerts(category or None)
    _print_json([a.to_dict() for a in alerts_list])


@metaintel_group.command("state")
@click.option("--snapshot", "do_snapshot", is_flag=True, help="Create state snapshot")
@click.option("--restore", "snapshot_id", default="", help="Restore from snapshot ID")
def state(do_snapshot: bool, snapshot_id: str) -> None:
    """Manage versioned system state."""
    vs = VersionedSystemState()
    if do_snapshot:
        snap = vs.snapshot({"metaintel": "active", "version": 1})
        _print_json(snap.to_dict())
    elif snapshot_id:
        success = vs.restore(snapshot_id)
        if not success:
            click.echo(f"Snapshot {snapshot_id} not found", err=True)
            sys.exit(1)
        click.echo(f"Restored snapshot {snapshot_id}")
    else:
        timeline = vs.get_timeline()
        _print_json(timeline)


def _print_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, default=str))
