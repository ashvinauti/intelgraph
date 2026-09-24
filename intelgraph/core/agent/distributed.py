from __future__ import annotations

import random
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from intelgraph.core.agent.hierarchy import TaskStatus


@dataclass
class TaskRecord:
    task_id: str
    priority: int
    status: TaskStatus
    node_id: str = ""
    retry_count: int = 0
    created_at: float = 0.0
    assigned_at: float = 0.0
    completed_at: float = 0.0


@dataclass
class NodeRecord:
    node_id: str
    host: str
    port: int
    healthy: bool = True
    last_heartbeat: float = 0.0
    load: float = 0.0
    tasks_completed: int = 0


class SharedWorkQueue:
    def __init__(self) -> None:
        self._queue: dict[str, TaskRecord] = {}
        self._order: list[str] = []

    def push(self, task_id: str, priority: int = 0) -> None:
        rec = TaskRecord(
            task_id=task_id, priority=priority, status=TaskStatus.PENDING, created_at=time.time()
        )
        self._queue[task_id] = rec
        self._order.append(task_id)
        self._order.sort(key=lambda tid: (-self._queue[tid].priority, self._queue[tid].created_at))

    def pop(self) -> TaskRecord | None:
        pending = [tid for tid in self._order if self._queue[tid].status == TaskStatus.PENDING]
        if not pending:
            return None
        tid = pending[0]
        rec = self._queue[tid]
        rec.status = TaskStatus.EXECUTING
        rec.assigned_at = time.time()
        return rec

    def complete(self, task_id: str, success: bool) -> None:
        rec = self._queue.get(task_id)
        if rec:
            rec.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
            rec.completed_at = time.time()

    def requeue(self, task_id: str) -> bool:
        rec = self._queue.get(task_id)
        if rec and rec.retry_count < 3:
            rec.status = TaskStatus.PENDING
            rec.retry_count += 1
            return True
        return False

    def peek(self, limit: int = 10) -> list[TaskRecord]:
        pending = [
            self._queue[tid] for tid in self._order if self._queue[tid].status == TaskStatus.PENDING
        ]
        return pending[:limit]

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for rec in self._queue.values():
            counts[rec.status.value] += 1
        return dict(counts)


class MultiNodeOrchestrator:
    def __init__(self) -> None:
        self._nodes: dict[str, NodeRecord] = {}
        self._queue = SharedWorkQueue()

    def register_node(self, host: str, port: int) -> NodeRecord:
        nid = f"node_{uuid.uuid4().hex[:8]}"
        node = NodeRecord(node_id=nid, host=host, port=port, last_heartbeat=time.time())
        self._nodes[nid] = node
        return node

    def heartbeat(self, node_id: str) -> bool:
        node = self._nodes.get(node_id)
        if not node:
            return False
        node.last_heartbeat = time.time()
        node.healthy = True
        return True

    def detect_failures(self, timeout: float = 30.0) -> list[str]:
        now = time.time()
        failed = []
        for nid, node in self._nodes.items():
            if now - node.last_heartbeat > timeout:
                node.healthy = False
                failed.append(nid)
        return failed

    def route_task(self, task_id: str, strategy: str = "round_robin") -> str | None:
        healthy = [n for n in self._nodes.values() if n.healthy]
        if not healthy:
            return None
        if strategy == "round_robin":
            idx = len(self._queue._order) % len(healthy)
            return healthy[idx].node_id
        if strategy == "least_loaded":
            return min(healthy, key=lambda n: n.load).node_id
        return healthy[0].node_id

    def get_node(self, node_id: str) -> NodeRecord | None:
        return self._nodes.get(node_id)

    def list_nodes(self) -> list[NodeRecord]:
        return list(self._nodes.values())


class RetryWithBackoff:
    def __init__(
        self, max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 60.0
    ) -> None:
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay

    def execute(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        last_exception = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self._max_attempts:
                    delay = min(
                        self._base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.1),
                        self._max_delay,
                    )
                    time.sleep(delay)
        raise last_exception


class FaultTolerantRouter:
    def __init__(self, orchestrator: MultiNodeOrchestrator) -> None:
        self._orchestrator = orchestrator
        self._failover_map: dict[str, list[str]] = {}

    def route_with_failover(self, task_id: str, primary: str, fallbacks: list[str]) -> str | None:
        candidates = [primary] + fallbacks
        for node_id in candidates:
            node = self._orchestrator.get_node(node_id)
            if node and node.healthy:
                return node_id
        return None

    def get_failover_path(self, task_id: str) -> list[str]:
        return self._failover_map.get(task_id, [])


class LoadBalancer:
    def __init__(self) -> None:
        self._rr_counter: dict[str, int] = defaultdict(int)

    def select_node(self, nodes: list[Any], strategy: str = "round_robin") -> Any | None:
        if not nodes:
            return None
        if strategy == "round_robin":
            key = "default"
            idx = self._rr_counter[key] % len(nodes)
            self._rr_counter[key] += 1
            return nodes[idx]
        if strategy == "least_loaded":
            return min(nodes, key=lambda n: getattr(n, "load", 0))
        return nodes[0]


class StateSynchronizer:
    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}
        self._versions: dict[str, int] = {}

    def broadcast_state(self, node_id: str, state: dict[str, Any]) -> None:
        self._states[node_id] = state
        self._versions[node_id] = self._versions.get(node_id, 0) + 1

    def reconcile(self, node_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {nid: self._states.get(nid, {}) for nid in node_ids}
