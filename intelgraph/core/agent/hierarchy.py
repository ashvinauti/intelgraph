from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

AGENT_SCHEMA_VERSION = "1.0"


class AgentRole(Enum):
    MASTER = "master"
    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    MONITOR = "monitor"
    SUB_AGENT = "sub_agent"


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    WAITING = "waiting"
    ERROR = "error"
    TERMINATED = "terminated"


class TaskStatus(Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class ExecutionMode(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"


@dataclass
class Agent:
    agent_id: str
    role: AgentRole
    status: AgentStatus = AgentStatus.IDLE
    parent_id: str = ""
    capabilities: list[str] = field(default_factory=list)
    created_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "status": self.status.value,
            "parent_id": self.parent_id,
            "capabilities": self.capabilities,
            "created_at": self.created_at,
        }


@dataclass
class TaskNode:
    task_id: str
    description: str
    parent_task_id: str = ""
    assigned_agent: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    sub_tasks: list[TaskNode] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    result: Any = None
    error: str = ""
    created_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "parent_task_id": self.parent_task_id,
            "assigned_agent": self.assigned_agent,
            "status": self.status.value,
            "priority": self.priority,
            "execution_mode": self.execution_mode.value,
            "sub_task_count": len(self.sub_tasks),
            "dependencies": self.dependencies,
            "error": self.error,
            "task_duration_ms": (
                round((self.completed_at - self.created_at) * 1000, 2) if self.completed_at else 0
            ),
        }


@dataclass
class ExecutionPlan:
    plan_id: str
    goal: str
    root_task: TaskNode
    agent_assignments: dict[str, str]
    estimated_cost: float
    alternative_plans: list[str] = field(default_factory=list)
    rollback_plan_id: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "root_task": self.root_task.to_dict(),
            "agent_assignments": self.agent_assignments,
            "estimated_cost": round(self.estimated_cost, 4),
            "alternative_plan_count": len(self.alternative_plans),
            "rollback_plan_id": self.rollback_plan_id,
        }


class AgentOrchestrator:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = config or {}
        self._agents: dict[str, Agent] = {}
        self._tasks: dict[str, TaskNode] = {}
        self._plans: list[ExecutionPlan] = []
        self._deadlock_detector = DeadlockDetector()
        self._conflict_resolver = ConflictResolver()
        self._priority_arbiter = PriorityArbiter()
        self._master = self._create_agent(
            AgentRole.MASTER, "master_orchestrator", ["plan", "delegate", "monitor", "terminate"]
        )

    def _create_agent(
        self,
        role: AgentRole,
        agent_id: str | None = None,
        capabilities: list[str] | None = None,
        parent_id: str = "",
    ) -> Agent:
        aid = agent_id or f"agent_{uuid.uuid4().hex[:12]}"
        agent = Agent(
            agent_id=aid,
            role=role,
            capabilities=capabilities or [],
            parent_id=parent_id,
            created_at=time.time(),
        )
        self._agents[aid] = agent
        return agent

    def spawn_agent(
        self, role: AgentRole, parent_id: str = "", capabilities: list[str] | None = None
    ) -> Agent:
        return self._create_agent(role, parent_id=parent_id, capabilities=capabilities)

    def terminate_agent(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if not agent or agent.role == AgentRole.MASTER:
            return False
        agent.status = AgentStatus.TERMINATED
        return True

    def decompose_task(self, goal: str, max_depth: int = 3) -> TaskNode:
        root_id = f"task_{uuid.uuid4().hex[:12]}"
        root = TaskNode(task_id=root_id, description=goal, priority=5, created_at=time.time())
        self._tasks[root_id] = root
        self._decompose(root, max_depth, 0)
        return root

    def _decompose(self, parent: TaskNode, max_depth: int, depth: int) -> None:
        if depth >= max_depth:
            return
        sub_descriptions = self._generate_sub_tasks(parent.description)
        for desc in sub_descriptions:
            child = TaskNode(
                task_id=f"task_{uuid.uuid4().hex[:12]}",
                description=desc,
                parent_task_id=parent.task_id,
                priority=max(0, parent.priority - 1),
                created_at=time.time(),
            )
            self._tasks[child.task_id] = child
            parent.sub_tasks.append(child)
            self._decompose(child, max_depth, depth + 1)

    def _generate_sub_tasks(self, description: str) -> list[str]:
        templates = {
            "analyze": ["collect_data", "process_data", "evaluate_results"],
            "investigate": ["gather_evidence", "correlate_facts", "draw_conclusions"],
            "execute": ["validate_inputs", "perform_action", "verify_outcome"],
            "respond": [
                "assess_situation",
                "select_response",
                "execute_response",
                "monitor_effect",
            ],
        }
        for key, subs in templates.items():
            if key in description.lower():
                return subs
        return ["prepare", "execute", "verify"]

    def assign_agent(self, task_id: str, agent_id: str) -> bool:
        task = self._tasks.get(task_id)
        agent = self._agents.get(agent_id)
        if not task or not agent:
            return False
        task.assigned_agent = agent_id
        agent.status = AgentStatus.BUSY
        return True

    def create_plan(self, goal: str) -> ExecutionPlan:
        root = self.decompose_task(goal)
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        agents = [
            self.spawn_agent(AgentRole.PLANNER, self._master.agent_id, ["plan"]),
            self.spawn_agent(AgentRole.EXECUTOR, self._master.agent_id, ["execute"]),
            self.spawn_agent(AgentRole.VERIFIER, self._master.agent_id, ["verify"]),
            self.spawn_agent(AgentRole.MONITOR, self._master.agent_id, ["monitor"]),
        ]
        assignments = {}
        for i, sub in enumerate(root.sub_tasks):
            if i < len(agents):
                self.assign_agent(sub.task_id, agents[i].agent_id)
                assignments[sub.task_id] = agents[i].agent_id
        plan = ExecutionPlan(
            plan_id=plan_id,
            goal=goal,
            root_task=root,
            agent_assignments=assignments,
            estimated_cost=len(root.sub_tasks) * 0.5,
            created_at=time.time(),
        )
        self._plans.append(plan)
        return plan

    def detect_deadlock(self) -> list[str]:
        return self._deadlock_detector.detect(list(self._tasks.values()))

    def resolve_conflict(self, task_a: str, task_b: str) -> str:
        return self._conflict_resolver.resolve(task_a, task_b)

    def arbitrate_priority(self, task_ids: list[str]) -> list[str]:
        return self._priority_arbiter.sort(
            [self._tasks[tid] for tid in task_ids if tid in self._tasks]
        )

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def get_task(self, task_id: str) -> TaskNode | None:
        return self._tasks.get(task_id)

    def get_plan(self, plan_id: str) -> ExecutionPlan | None:
        for p in self._plans:
            if p.plan_id == plan_id:
                return p
        return None

    def list_agents(self, role: AgentRole | None = None) -> list[Agent]:
        agents = list(self._agents.values())
        if role:
            agents = [a for a in agents if a.role == role]
        return agents

    def list_plans(self) -> list[ExecutionPlan]:
        return list(self._plans)

    def communicate(self, from_agent: str, to_agent: str, message: dict[str, Any]) -> bool:
        if from_agent not in self._agents or to_agent not in self._agents:
            return False
        return True


class DeadlockDetector:
    def detect(self, tasks: list[TaskNode]) -> list[str]:
        dep_map: dict[str, set[str]] = {}
        for t in tasks:
            dep_map[t.task_id] = set(t.dependencies)
        visited: set[str] = set()
        in_stack: set[str] = set()
        deadlocks: list[str] = []

        def _dfs(tid: str) -> bool:
            visited.add(tid)
            in_stack.add(tid)
            for dep in dep_map.get(tid, set()):
                if dep not in visited:
                    if _dfs(dep):
                        return True
                elif dep in in_stack:
                    deadlocks.append(f"Cycle: {tid} -> {dep}")
                    return True
            in_stack.discard(tid)
            return False

        for t in tasks:
            if t.task_id not in visited:
                _dfs(t.task_id)
        return deadlocks


class ConflictResolver:
    def resolve(self, task_a: str, task_b: str) -> str:
        return task_a if task_a < task_b else task_b


class PriorityArbiter:
    def sort(self, tasks: list[TaskNode]) -> list[str]:
        return [t.task_id for t in sorted(tasks, key=lambda t: (-t.priority, t.created_at))]
