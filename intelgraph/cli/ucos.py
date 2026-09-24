from __future__ import annotations

import json
import sys
from typing import Any

import click

from intelgraph.core.ucos import (
    ClosedLoopIntelligenceSystem,
    ConsolidationEngine,
    DependencyValidator,
    GlobalHealthIndex,
    SimplificationEngine,
    SingleSourceOfTruth,
    UnifiedAlertingCore,
    UnifiedCognitiveCore,
    UnifiedExecutionRuntime,
    UnifiedPolicyControlPlane,
    UnifiedSafetyLayer,
    UnifiedTelemetryCore,
)


@click.group(name="ucos")
def ucos_group() -> None:
    """Unified Cognitive Operating System (UCOS)."""


@ucos_group.command("query")
@click.argument("key", required=False, default="")
def query(key: str) -> None:
    """Query unified system state."""
    state = SingleSourceOfTruth()
    if key:
        entry = state.get(key)
        _print_json(entry.to_dict() if entry else {"error": "not found"})
    else:
        _print_json({k: v.to_dict() for k, v in state.get_all().items()})


@ucos_group.command("reason")
@click.argument("query_str", type=str)
def reason(query_str: str) -> None:
    """Execute unified reasoning."""
    cog = UnifiedCognitiveCore()
    result = cog.reason(query_str)
    _print_json(result.to_dict())


@ucos_group.command("act")
@click.argument("goal", type=str)
@click.option("--risk", type=float, default=0.5, help="Action risk score")
def act(goal: str, risk: float) -> None:
    """Execute an action through unified runtime."""
    policy = UnifiedPolicyControlPlane()
    safety = UnifiedSafetyLayer()
    decision = policy.evaluate("act", risk)
    if not decision.allowed:
        click.echo(f"Policy denied: {decision.reason}", err=True)
        sys.exit(1)
    safety_check = safety.check_safety({"type": "act", "risk": risk})
    if not safety_check["safe"]:
        click.echo(f"Safety denied: {safety_check['reason']}", err=True)
        sys.exit(1)
    runtime = UnifiedExecutionRuntime()
    result = runtime.execute(goal)
    _print_json(result.to_dict())


@ucos_group.command("observe")
@click.option("--reasoning-quality", type=float, default=0.5)
@click.option("--success", is_flag=True, default=True)
@click.option("--latency-ms", type=float, default=0)
def observe(reasoning_quality: float, success: bool, latency_ms: float) -> None:
    """Record telemetry observation."""
    tel = UnifiedTelemetryCore()
    snap = tel.record(reasoning_quality, success, latency_ms)
    _print_json(snap.to_dict())


@ucos_group.command("policy")
@click.option("--evaluate", "do_evaluate", is_flag=True, help="Evaluate policy")
@click.option("--action-type", default="read", help="Action type")
@click.option("--risk", type=float, default=0.3, help="Risk score")
def policy(do_evaluate: bool, action_type: str, risk: float) -> None:
    """Manage unified policy."""
    p = UnifiedPolicyControlPlane()
    if do_evaluate:
        decision = p.evaluate(action_type, risk)
        _print_json(decision.to_dict())
    else:
        rules = p.get_rules()
        _print_json(rules)


@ucos_group.command("health")
def health() -> None:
    """Show global system health index."""
    h = GlobalHealthIndex()
    tel = UnifiedTelemetryCore()
    latest = tel.get_latest()
    result = h.compute(
        cognitive=latest.reasoning_quality if latest else 0.5,
        execution=latest.execution_success_rate if latest else 0.5,
        policy=0.8,
    )
    _print_json(result)


@ucos_group.command("consolidate")
@click.option("--scan", "do_scan", is_flag=True, help="Scan for duplicates")
def consolidate(do_scan: bool) -> None:
    """Consolidate system architecture."""
    eng = ConsolidationEngine()
    if do_scan:
        plan = eng.consolidation_plan()
        _print_json(plan)
    else:
        engines = eng.get_engines()
        _print_json([e.to_dict() for e in engines])


@ucos_group.command("simplify")
def simplify() -> None:
    """Check system simplification."""
    sim = SimplificationEngine()
    dups = sim.check_no_duplicates()
    owners = sim.check_single_owner()
    _print_json(
        {
            "duplicate_violations": dups,
            "owner_violations": owners,
            "complexity_index": round(sim.compute_system_complexity(), 4),
        }
    )


@ucos_group.command("closed-loop")
@click.argument("query_str", type=str)
@click.option("--latency", type=float, default=50, help="Observed latency")
def closed_loop(query_str: str, latency: float) -> None:
    """Run a closed-loop intelligence cycle."""
    cog = UnifiedCognitiveCore()
    runtime = UnifiedExecutionRuntime()
    loop = ClosedLoopIntelligenceSystem()
    reasoning = cog.reason(query_str)
    execution = runtime.execute(query_str)
    entry = loop.run_cycle(
        {"summary": query_str},
        reasoning.to_dict(),
        execution.to_dict(),
        {"latency_ms": latency},
    )
    _print_json(entry.to_dict())


@ucos_group.command("safety")
@click.option("--check", "do_check", is_flag=True, help="Check action safety")
@click.option("--action-type", default="read", help="Action type")
@click.option("--risk", type=float, default=0.3, help="Risk score")
@click.option("--kill-switch", "do_kill", is_flag=True, help="Toggle kill switch")
def safety(do_check: bool, action_type: str, risk: float, do_kill: bool) -> None:
    """Manage system safety."""
    s = UnifiedSafetyLayer()
    if do_kill:
        if s._kill_switch:
            s.disengage_kill_switch()
            click.echo("Kill switch disengaged")
        else:
            s.engage_kill_switch()
            click.echo("Kill switch engaged")
    elif do_check:
        result = s.check_safety({"type": action_type, "risk": risk})
        _print_json(result)
    else:
        _print_json(s.get_status())


@ucos_group.command("alerts")
@click.option("--category", default="", help="Filter by category")
def alerts(category: str) -> None:
    """Show system alerts."""
    ac = UnifiedAlertingCore()
    alerts_list = ac.get_alerts(category or None)
    _print_json(alerts_list)


@ucos_group.command("dependency")
@click.option("--register", "do_register", is_flag=True, help="Register dependencies")
@click.option("--module-id", default="", help="Module ID")
@click.option("--deps", default="", help="Comma-separated dependencies")
def dependency(do_register: bool, module_id: str, deps: str) -> None:
    """Validate system dependencies."""
    dv = DependencyValidator()
    if do_register:
        if not module_id:
            click.echo("--module-id is required", err=True)
            sys.exit(1)
        dep_list = [d.strip() for d in deps.split(",") if d.strip()]
        dv.register_module(module_id, dep_list)
        cycles = dv.validate_no_circular()
        _print_json({"module_id": module_id, "dependencies": dep_list, "cycles": cycles})
    else:
        _print_json(dv.get_violations())


@ucos_group.command("state")
@click.option("--set", "do_set", is_flag=True, help="Set state value")
@click.option("--key", default="", help="State key")
@click.option("--value", default="", help="State value")
@click.option("--source", default="ucos", help="Value source")
def state(do_set: bool, key: str, value: str, source: str) -> None:
    """Manage single source of truth."""
    s = SingleSourceOfTruth()
    if do_set:
        if not key:
            click.echo("--key is required", err=True)
            sys.exit(1)
        result = s.set(key, value, source)
        _print_json(result)
    else:
        if key:
            entry = s.get(key)
            _print_json(entry.to_dict() if entry else {"error": "not found"})
        else:
            _print_json({k: v.to_dict() for k, v in s.get_all().items()})


def _print_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, default=str))
