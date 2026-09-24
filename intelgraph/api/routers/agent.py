from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from intelgraph.api.auth_middleware import require_permission
from intelgraph.core.agent.audit import ExecutionAudit
from intelgraph.core.agent.compiler import ReasoningCompiler
from intelgraph.core.agent.distributed import SharedWorkQueue
from intelgraph.core.agent.feedback import ExecutionFeedbackLoop
from intelgraph.core.agent.hierarchy import (
    AgentOrchestrator,
    TaskStatus,
)
from intelgraph.core.agent.memory import ExecutionMemory
from intelgraph.core.agent.safety import SafetyGovernor
from intelgraph.core.agent.simulation import ChaosInjector, SimulationEngine
from intelgraph.core.agent.tools import ToolExecutor, ToolType
from intelgraph.core.enterprise import get_metrics as _get_metrics

router = APIRouter(prefix="/agent", tags=["Agent"])


def get_orchestrator() -> AgentOrchestrator:
    return AgentOrchestrator()


def get_executor() -> ToolExecutor:
    return ToolExecutor()


def get_safety() -> SafetyGovernor:
    return SafetyGovernor()


def get_audit() -> ExecutionAudit:
    return ExecutionAudit()


def get_simulator() -> SimulationEngine:
    return SimulationEngine()


def get_memory() -> ExecutionMemory:
    return ExecutionMemory()


def get_feedback() -> ExecutionFeedbackLoop:
    return ExecutionFeedbackLoop()


def get_compiler() -> ReasoningCompiler:
    return ReasoningCompiler()


@router.post("/plan", summary="Create an execution plan from a goal description")
async def create_plan(
    body: dict[str, Any],
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    _=require_permission("agent:read"),
):
    goal = body.get("goal", "")
    if not goal:
        raise HTTPException(status_code=422, detail="goal is required")
    plan = orchestrator.create_plan(goal)
    _get_metrics().set_gauge("agent_plan_count", len(orchestrator.list_plans()))
    return plan.to_dict()


@router.post("/execute", summary="Execute a goal through the agent system")
async def execute_goal(
    body: dict[str, Any],
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    executor: ToolExecutor = Depends(get_executor),
    safety: SafetyGovernor = Depends(get_safety),
    audit: ExecutionAudit = Depends(get_audit),
    _=require_permission("agent:write"),
):
    goal = body.get("goal", "")
    sandbox = body.get("sandbox", "medium")
    if not goal:
        raise HTTPException(status_code=422, detail="goal is required")
    plan = orchestrator.create_plan(goal)
    results = []
    for task_id, agent_id in plan.agent_assignments.items():
        task = orchestrator.get_task(task_id)
        if not task:
            continue
        action_type = "execute" if "execute" in task.description.lower() else "analyze"
        risk = 0.5 if action_type == "execute" else 0.3
        check = safety.check_action(action_type, task.description, risk)
        if not check.approved:
            results.append({"task_id": task_id, "status": "denied", "violations": check.violations})
            continue
        call = executor.execute(ToolType.INTERNAL, action_type, {"task": task.description}, sandbox)
        outcome = "success" if call.success else "failure"
        task.status = TaskStatus.COMPLETED if call.success else TaskStatus.FAILED
        audit.record(
            call.call_id, agent_id, task_id, action_type, task.description, outcome, risk, 0.0
        )
        results.append({"task_id": task_id, "agent_id": agent_id, "status": outcome})
    _get_metrics().set_gauge("agent_execution_count", len(results))
    _get_metrics().set_gauge(
        "agent_execution_success_rate",
        sum(1 for r in results if r["status"] == "success") / max(len(results), 1),
    )
    return {"plan_id": plan.plan_id, "goal": goal, "results": results}


@router.post("/rollback", summary="Rollback an execution plan")
async def rollback_plan(
    body: dict[str, Any],
    executor: ToolExecutor = Depends(get_executor),
    _=require_permission("agent:write"),
):
    plan_id = body.get("plan_id", "")
    if not plan_id:
        raise HTTPException(status_code=422, detail="plan_id is required")
    calls = executor.get_history()
    rolled = []
    for call in calls:
        if executor.rollback(call.call_id):
            rolled.append(call.call_id)
    return {"plan_id": plan_id, "rolled_back": rolled, "count": len(rolled)}


@router.post(
    "/task/submit",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a task to the distributed queue",
)
async def submit_task(
    body: dict[str, Any],
    _=require_permission("agent:write"),
):
    goal = body.get("goal", "")
    priority = int(body.get("priority", 0))
    if not goal:
        raise HTTPException(status_code=422, detail="goal is required")
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    queue = SharedWorkQueue()
    queue.push(task_id, priority)
    _get_metrics().set_gauge("agent_submitted_tasks", len(queue._queue))
    return {"task_id": task_id, "goal": goal, "priority": priority, "status": "submitted"}


@router.get("/task/status/{task_id}", summary="Get task execution status")
async def task_status(
    task_id: str,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    _=require_permission("agent:read"),
):
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task.to_dict()


@router.post("/validate/execution", summary="Validate an execution plan for safety")
async def validate_execution(
    body: dict[str, Any],
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
    safety: SafetyGovernor = Depends(get_safety),
    _=require_permission("agent:read"),
):
    plan_id = body.get("plan_id", "")
    if plan_id:
        plan = orchestrator.get_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
        checks = []
        for task_id in plan.agent_assignments:
            result = safety.check_action("validate", f"Validate task {task_id}", 0.3)
            checks.append(result.to_dict())
        return {"plan_id": plan_id, "safe": all(c["approved"] for c in checks), "checks": checks}
    plans = orchestrator.list_plans()
    results = []
    for p in plans:
        safe = all(
            safety.check_action("validate", f"Task {tid}", 0.3).approved
            for tid in p.agent_assignments
        )
        results.append({"plan_id": p.plan_id, "safe": safe})
    return {"plans": results}


@router.post("/simulate", summary="Simulate execution of a goal")
async def simulate_execution(
    body: dict[str, Any],
    simulator: SimulationEngine = Depends(get_simulator),
    _=require_permission("agent:read"),
):
    goal = body.get("goal", "")
    chaos = body.get("chaos", False)
    if not goal:
        raise HTTPException(status_code=422, detail="goal is required")
    plan_dict = {"goal": goal, "sub_tasks": [{"description": goal}]}
    if chaos:
        chaos_injector = ChaosInjector()
        chaos_result = chaos_injector.inject_failure(plan_dict)
        plan_dict["chaos"] = chaos_result
    result = simulator.simulate(goal, plan_dict)
    _get_metrics().set_gauge("agent_simulation_probability", result.success_probability)
    return result.to_dict()


@router.post("/replay", summary="Replay execution from audit trace")
async def replay_execution(
    body: dict[str, Any],
    audit: ExecutionAudit = Depends(get_audit),
    _=require_permission("agent:read"),
):
    trace_id = body.get("trace_id", "")
    if not trace_id:
        raise HTTPException(status_code=422, detail="trace_id is required")
    entry = audit.get(trace_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return entry.to_dict()


@router.post("/kill-switch", summary="Engage or disengage kill switch")
async def kill_switch(
    body: dict[str, Any],
    safety: SafetyGovernor = Depends(get_safety),
    _=require_permission("agent:admin"),
):
    scope = body.get("scope", "global")
    target = body.get("target", "")
    disengage = body.get("disengage", False)
    if disengage:
        success = safety.disengage_kill_switch(scope, target)
        action = "disengaged"
    else:
        success = safety.engage_kill_switch(scope, target)
        action = "engaged"
    if not success:
        raise HTTPException(
            status_code=400, detail=f"Failed to {action} kill switch ({scope}/{target})"
        )
    return {"status": f"kill_switch_{action}", "scope": scope, "target": target}


@router.get("/config", summary="Get agent system configuration")
async def agent_config(
    _=require_permission("agent:read"),
):
    return {
        "default_sandbox": "medium",
        "max_agents": 10,
        "heartbeat_interval": 30,
        "forbidden_actions": ["shutdown", "destroy", "nuke"],
    }


@router.get("/audit", summary="Query execution audit trail")
async def query_audit(
    task_id: str = "",
    agent_id: str = "",
    limit: int = 100,
    audit: ExecutionAudit = Depends(get_audit),
    _=require_permission("agent:read"),
):
    entries = audit.query(task_id=task_id or None, agent_id=agent_id or None, limit=limit)
    return {"entries": [e.to_dict() for e in entries], "count": len(entries)}


@router.post("/feedback", summary="Record execution feedback for self-learning")
async def record_feedback(
    body: dict[str, Any],
    feedback: ExecutionFeedbackLoop = Depends(get_feedback),
    _=require_permission("agent:write"),
):
    task_id = body.get("task_id", "")
    success = body.get("success", True)
    confidence = float(body.get("confidence", 0.5))
    duration_ms = float(body.get("duration_ms", 0))
    error = body.get("error", "")
    if not task_id:
        raise HTTPException(status_code=422, detail="task_id is required")
    outcome = feedback.record_outcome(task_id, success, confidence, duration_ms, error)
    _get_metrics().set_gauge("agent_feedback_success_rate", feedback.overall_success_rate())
    return outcome.to_dict()


@router.get("/memory/{entity_id}", summary="Query execution memory for an entity")
async def query_memory(
    entity_id: str,
    key: str = "",
    memory: ExecutionMemory = Depends(get_memory),
    _=require_permission("agent:read"),
):
    records = memory.recall(entity_id, key or None)
    return {
        "entity_id": entity_id,
        "records": [
            {"memory_id": r.memory_id, "key": r.key, "value": r.value, "outcome": r.outcome}
            for r in records
        ],
        "count": len(records),
    }
