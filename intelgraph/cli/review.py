import json

import click

from intelgraph.core.human_review import ReviewManager, ReviewOutcome
from intelgraph.core.storage import SQLiteBackend


@click.group(name="review", help="Manage human review workflows")
def review_group() -> None:
    pass


def _get_manager(ctx: click.Context) -> ReviewManager:
    config = ctx.obj.get("config", {})
    storage_cfg = config.get("storage", {})
    db_path = storage_cfg.get("path", "intelgraph.db")
    backend = SQLiteBackend(db_path)
    backend.connect()
    backend.initialize_schema()
    mgr = ReviewManager(backend)
    mgr.initialize()
    return mgr


@review_group.command(name="evaluate", help="Evaluate whether an entity needs review")
@click.argument("entity_id")
@click.pass_context
def review_evaluate(ctx: click.Context, entity_id: str) -> None:
    mgr = _get_manager(ctx)
    result = mgr.evaluate(entity_id)
    click.echo(
        json.dumps(
            {
                "entity_id": entity_id,
                "needs_review": result.needs_review,
                "reason": result.reason,
                "suggested_action": result.suggested_action,
            },
            indent=2,
        )
    )


@review_group.command(name="enqueue", help="Add entity to review queue")
@click.argument("entity_id")
@click.option("--type", "-t", "entity_type", default="", help="Entity type label")
@click.pass_context
def review_enqueue(ctx: click.Context, entity_id: str, entity_type: str) -> None:
    mgr = _get_manager(ctx)
    queue_id = mgr.enqueue_for_review(entity_id, entity_type)
    if queue_id is None:
        click.echo(json.dumps({"message": "Entity does not need review (auto-approved)"}, indent=2))
    else:
        click.echo(json.dumps({"queue_id": queue_id, "entity_id": entity_id}, indent=2))


@review_group.command(name="approve", help="Approve evidence for an entity")
@click.argument("entity_id")
@click.option("--reviewer", "-r", default="cli-user", help="Reviewer identifier")
@click.option("--notes", "-n", default="", help="Review notes")
@click.option("--queue-id", default=None, help="Review queue ID if dequeued")
@click.pass_context
def review_approve(
    ctx: click.Context, entity_id: str, reviewer: str, notes: str, queue_id: str | None
) -> None:
    mgr = _get_manager(ctx)
    try:
        record = mgr.process_review(
            entity_id, ReviewOutcome.APPROVED_REVIEW, reviewer, notes, queue_id
        )
        click.echo(json.dumps(record.to_dict(), indent=2))
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}, indent=2), err=True)


@review_group.command(name="reject", help="Reject evidence for an entity")
@click.argument("entity_id")
@click.option("--reviewer", "-r", default="cli-user", help="Reviewer identifier")
@click.option("--notes", "-n", default="", help="Review notes")
@click.option("--queue-id", default=None, help="Review queue ID if dequeued")
@click.pass_context
def review_reject(
    ctx: click.Context, entity_id: str, reviewer: str, notes: str, queue_id: str | None
) -> None:
    mgr = _get_manager(ctx)
    try:
        record = mgr.process_review(
            entity_id, ReviewOutcome.REJECTED_REVIEW, reviewer, notes, queue_id
        )
        click.echo(json.dumps(record.to_dict(), indent=2))
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}, indent=2), err=True)


@review_group.command(name="needs-more", help="Request more evidence for an entity")
@click.argument("entity_id")
@click.option("--reviewer", "-r", default="cli-user", help="Reviewer identifier")
@click.option("--notes", "-n", default="", help="Review notes")
@click.option("--queue-id", default=None, help="Review queue ID if dequeued")
@click.pass_context
def review_needs_more(
    ctx: click.Context, entity_id: str, reviewer: str, notes: str, queue_id: str | None
) -> None:
    mgr = _get_manager(ctx)
    try:
        record = mgr.process_review(
            entity_id, ReviewOutcome.NEEDS_MORE_EVIDENCE, reviewer, notes, queue_id
        )
        click.echo(json.dumps(record.to_dict(), indent=2))
    except ValueError as e:
        click.echo(json.dumps({"error": str(e)}, indent=2), err=True)


@review_group.command(name="list", help="List review records")
@click.option("--entity-id", default=None, help="Filter by entity ID")
@click.option("--pending", is_flag=True, default=False, help="Show pending queue items")
@click.pass_context
def review_list(ctx: click.Context, entity_id: str | None, pending: bool) -> None:
    mgr = _get_manager(ctx)
    if pending:
        items = mgr.list_pending_reviews()
    else:
        items = mgr.get_reviews(entity_id=entity_id)
    click.echo(json.dumps(items, indent=2, default=str))


@review_group.command(name="stats", help="Review system statistics")
@click.pass_context
def review_stats(ctx: click.Context) -> None:
    mgr = _get_manager(ctx)
    click.echo(json.dumps(mgr.review_stats(), indent=2, default=str))
