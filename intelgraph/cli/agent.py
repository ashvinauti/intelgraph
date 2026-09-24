from __future__ import annotations

import json
import sys
import uuid
from typing import Any

import click

from intelgraph.core.agent.audit import ExecutionAudit
from intelgraph.core.agent.distributed import SharedWorkQueue
from intelgraph.core.agent.hierarchy import (
    AgentOrchestrator,
    TaskStatus,
)
from intelgraph.core.agent.memory import ExecutionMemory
from intelgraph.core.agent.safety import SafetyGovernor
from intelgraph.core.agent.simulation import ChaosInjector, SimulationEngine
from intelgraph.core.agent.tools import ToolExecutor, ToolType


@click.group(name="agent")
def agent_group() -> None:
    """Autonomous agent orchestration and execution."""


@agent_group.command("plan")
@click.argument("goal", type=str)
def plan(goal: str) -> None:
    """Create an execution plan for a goal."""
    orchestrator = AgentOrchestrator()
    plan = orchestrator.create_plan(goal)
    _print_json(plan.to_dict())


@agent_group.command("execute")
@click.argument("goal", type=str)
@click.option("--sandbox", default="medium", help="Sandbox level: none/light/medium/strict")
def execute(goal: str, sandbox: str) -> None:
    """Execute a goal through the agent system."""
    orchestrator = AgentOrchestrator()
    plan = orchestrator.create_plan(goal)
    executor = ToolExecutor()
    safety = SafetyGovernor()
    audit = ExecutionAudit()
    results = []
    for task_id, agent_id in plan.agent_assignments.items():
        task = orchestrator.get_task(task_id)
        if not task:
            continue
        action_type = "execute" if "execute" in task.description.lower() else "analyze"
        risk = 0.5 if action_type == "execute" else 0.3
        check = safety.check_action(action_type, task.description, risk)
        if not check.approved:
            results.append({"task_id": task_id, "status": "denied", "reason": check.violations})
            continue
        call = executor.execute(ToolType.INTERNAL, action_type, {"task": task.description}, sandbox)
        outcome = "success" if call.success else "failure"
        task.status = TaskStatus.COMPLETED if call.success else TaskStatus.FAILED
        audit.record(
            call.call_id, agent_id, task_id, action_type, task.description, outcome, risk, 0.0
        )
        results.append(
            {"task_id": task_id, "agent_id": agent_id, "status": outcome, "tool_call": call.call_id}
        )
    _print_json({"plan_id": plan.plan_id, "goal": goal, "results": results})


@agent_group.command("rollback")
@click.argument("plan-id", type=str)
def rollback(plan_id: str) -> None:
    """Rollback an execution plan."""
    orchestrator = AgentOrchestrator()
    plan = orchestrator.get_plan(plan_id)
    if not plan:
        click.echo(f"Plan {plan_id} not found", err=True)
        sys.exit(1)
    executor = ToolExecutor()
    calls = executor.get_history()
    rolled_back = []
    for call in calls:
        if executor.rollback(call.call_id):
            rolled_back.append(call.call_id)
    _print_json({"plan_id": plan_id, "rolled_back": rolled_back, "count": len(rolled_back)})


@agent_group.command("submit")
@click.argument("goal", type=str)
@click.option("--priority", type=int, default=0, help="Task priority (higher = more important)")
def submit(goal: str, priority: int) -> None:
    """Submit a task to the distributed queue."""
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    queue = SharedWorkQueue()
    queue.push(task_id, priority)
    _print_json({"task_id": task_id, "goal": goal, "priority": priority, "status": "submitted"})


@agent_group.command("status")
@click.argument("task-id", type=str)
def status(task_id: str) -> None:
    """Get task execution status."""
    orchestrator = AgentOrchestrator()
    task = orchestrator.get_task(task_id)
    if not task:
        click.echo(f"Task {task_id} not found", err=True)
        sys.exit(1)
    _print_json(task.to_dict())


@agent_group.command("validate")
@click.argument("plan-id", type=str, required=False)
def validate(plan_id: str | None) -> None:
    """Validate an execution plan for safety."""
    orchestrator = AgentOrchestrator()
    safety = SafetyGovernor()
    if plan_id:
        plan = orchestrator.get_plan(plan_id)
        if not plan:
            click.echo(f"Plan {plan_id} not found", err=True)
            sys.exit(1)
        checks = []
        for task_id in plan.agent_assignments:
            result = safety.check_action("validate", f"Validate task {task_id}", 0.3)
            checks.append(result.to_dict())
        _print_json({"plan_id": plan_id, "checks": checks})
    else:
        plans = orchestrator.list_plans()
        results = []
        for p in plans:
            safe = all(
                safety.check_action("validate", f"Task {tid}", 0.3).approved
                for tid in p.agent_assignments
            )
            results.append({"plan_id": p.plan_id, "safe": safe})
        _print_json({"plans": results})


@agent_group.command("simulate")
@click.argument("goal", type=str)
@click.option("--chaos", is_flag=True, help="Inject chaos failures")
def simulate(goal: str, chaos: bool) -> None:
    """Simulate execution of a goal."""
    sim = SimulationEngine()
    chaos_injector = ChaosInjector()
    plan_dict = {"goal": goal, "sub_tasks": [{"description": goal}]}
    if chaos:
        chaos_result = chaos_injector.inject_failure(plan_dict)
        plan_dict["chaos"] = chaos_result
    result = sim.simulate(goal, plan_dict)
    _print_json(result.to_dict())


@agent_group.command("replay")
@click.argument("trace-id", type=str)
def replay(trace_id: str) -> None:
    """Replay execution from audit trace."""
    audit = ExecutionAudit()
    entry = audit.get(trace_id)
    if not entry:
        click.echo(f"Trace {trace_id} not found", err=True)
        sys.exit(1)
    _print_json(entry.to_dict())


@agent_group.command("kill-switch")
@click.option(
    "--scope",
    type=click.Choice(["global", "agent", "task"]),
    default="global",
    help="Kill switch scope",
)
@click.option("--target", default="", help="Target ID (for agent/task scope)")
@click.option("--disengage", is_flag=True, help="Disengage instead of engage")
def kill_switch(scope: str, target: str, disengage: bool) -> None:
    """Engage or disengage kill switch."""
    safety = SafetyGovernor()
    if disengage:
        success = safety.disengage_kill_switch(scope, target)
        action = "disengaged"
    else:
        success = safety.engage_kill_switch(scope, target)
        action = "engaged"
    if success:
        click.echo(f"Kill switch {action} ({scope}/{target})")
    else:
        click.echo(f"Failed to {action} kill switch", err=True)
        sys.exit(1)


@agent_group.command("config")
@click.option("--show", is_flag=True, help="Show agent configuration")
def config(show: bool) -> None:
    """Get or set agent configuration."""
    if show:
        _print_json(
            {
                "default_sandbox": "medium",
                "max_agents": 10,
                "heartbeat_interval": 30,
                "forbidden_actions": ["shutdown", "destroy", "nuke"],
            }
        )


@agent_group.command("audit")
@click.option("--task-id", default="", help="Filter by task ID")
@click.option("--agent-id", default="", help="Filter by agent ID")
@click.option("--limit", type=int, default=100, help="Max entries")
def audit(task_id: str, agent_id: str, limit: int) -> None:
    """Query execution audit trail."""
    audit = ExecutionAudit()
    entries = audit.query(task_id=task_id or None, agent_id=agent_id or None, limit=limit)
    _print_json([e.to_dict() for e in entries])


@agent_group.command("memory")
@click.argument("entity-id", type=str, required=False)
@click.option("--key", default="", help="Memory key")
def memory(entity_id: str | None, key: str) -> None:
    """Query execution memory."""
    mem = ExecutionMemory()
    if entity_id:
        records = mem.recall(entity_id, key or None)
        _print_json(
            [
                {"memory_id": r.memory_id, "key": r.key, "value": r.value, "outcome": r.outcome}
                for r in records
            ]
        )
    else:
        all_mem = mem.get_memory(limit=100)
        _print_json(
            {r.entity_id: {"key": r.key, "value": r.value, "outcome": r.outcome} for r in all_mem}
        )


def _print_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, default=str))
