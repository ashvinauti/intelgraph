from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from intelgraph.core.storage.audit import AuditEntry

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get_task_manager() -> Any:
    from intelgraph.api.main import _container

    return _container.task_manager


def _get_audit() -> Any:
    from intelgraph.api.main import _container

    return _container.audit


def _get_actor(request: Any) -> str:
    uid = getattr(request.state, "user_id", "")
    return uid or "anonymous"


@router.get(
    "",
    summary="List tasks",
    description="List all tasks, optionally filtered by status.",
)
def list_tasks(
    status: str | None = None,
    tm: Any = Depends(_get_task_manager),
):
    return tm.list_tasks(status=status)


@router.get(
    "/{task_id}",
    summary="Get task by ID",
    description="Retrieve a single task by its unique identifier.",
)
def get_task(task_id: str, tm: Any = Depends(_get_task_manager)):
    t = tm.get_task(task_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return t


def _enqueue_and_audit(task_type: str, tm: Any, request: Any, audit_type: str) -> dict:
    task = tm.enqueue(task_type)
    if request:
        _get_audit().log(
            AuditEntry(
                entity_id=task.id,
                entity_type="task",
                operation=audit_type,
                new_data={"task_type": task_type},
                actor=_get_actor(request),
            )
        )
    return {"task_id": task.id, "task_type": task_type, "status": task.status.value}


@router.post(
    "/collect_entity",
    summary="Enqueue entity collection task",
    description="Enqueue a task to collect an entity from external sources.",
)
def enqueue_collect_entity(tm: Any = Depends(_get_task_manager), request: Request = None):
    return _enqueue_and_audit("collect_entity", tm, request, "CREATE")


@router.post(
    "/verify_entity",
    summary="Enqueue entity verification task",
    description="Enqueue a task to verify an entity against available evidence.",
)
def enqueue_verify_entity(tm: Any = Depends(_get_task_manager), request: Request = None):
    return _enqueue_and_audit("verify_entity", tm, request, "CREATE")


@router.post(
    "/generate_report",
    summary="Enqueue report generation task",
    description="Enqueue a task to generate a report.",
)
def enqueue_generate_report(tm: Any = Depends(_get_task_manager), request: Request = None):
    return _enqueue_and_audit("generate_report", tm, request, "CREATE")
