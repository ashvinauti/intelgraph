from __future__ import annotations

import json

import click

from intelgraph.core.orchestrator import TaskManager


@click.group(name="task")
def task_group() -> None:
    """Manage async tasks."""


def _get_manager() -> TaskManager:
    m = TaskManager()
    m.initialize()
    return m


@task_group.command("list")
def list_tasks() -> None:
    """List all tasks."""
    tm = _get_manager()
    tasks = tm.list_tasks()
    if not tasks:
        click.echo("No tasks found.")
        return
    for t in tasks:
        click.echo(f"{t['id']:26s}  {t['type']:20s}  {t['status']:12s}  retry={t['retry_count']}")


@task_group.command("get")
@click.argument("task_id")
def get_task(task_id: str) -> None:
    """Get task details by ID."""
    tm = _get_manager()
    t = tm.get_task(task_id)
    if t is None:
        click.echo(f"Task {task_id} not found.")
        return
    click.echo(json.dumps(t, indent=2))


@task_group.command("collect")
@click.argument("entity_id")
def collect(entity_id: str) -> None:
    """Enqueue a collect_entity task."""
    tm = _get_manager()
    task = tm.enqueue("collect_entity", payload=entity_id.encode("utf-8"))
    click.echo(f"Enqueued collect_entity task: {task.id}")


@task_group.command("verify")
@click.argument("entity_id")
def verify(entity_id: str) -> None:
    """Enqueue a verify_entity task."""
    tm = _get_manager()
    task = tm.enqueue("verify_entity", payload=entity_id.encode("utf-8"))
    click.echo(f"Enqueued verify_entity task: {task.id}")


@task_group.command("report")
@click.argument("entity_id")
def report(entity_id: str) -> None:
    """Enqueue a generate_report task."""
    tm = _get_manager()
    task = tm.enqueue("generate_report", payload=entity_id.encode("utf-8"))
    click.echo(f"Enqueued generate_report task: {task.id}")
