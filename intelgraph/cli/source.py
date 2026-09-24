import json

import click

from intelgraph.core.source_registry import SourceRegistryService
from intelgraph.core.storage import SQLiteBackend


@click.group(name="source", help="Manage intelligence sources")
def source_group() -> None:
    pass


@source_group.command(name="add", help="Register a new intelligence source")
@click.argument("url")
@click.option("--name", "-n", default=None, help="Human-readable source name")
@click.option(
    "--tier",
    "-t",
    type=click.Choice(["1", "2", "3"]),
    default="3",
    help="Source trust tier (1=high, 2=medium, 3=low)",
)
@click.option("--classify", "-c", default=None, help="Source classification label")
@click.pass_context
def source_add(
    ctx: click.Context, url: str, name: str | None, tier: str, classify: str | None
) -> None:
    registry = _get_registry(ctx)
    result = registry.add_source(
        source_url=url,
        source_name=name,
        source_tier=int(tier),
        classification=classify,
    )
    click.echo(json.dumps(result, indent=2, default=str))


@source_group.command(name="list", help="List all registered sources")
@click.option("--rank/--no-rank", default=True, help="Apply trust-weighted ranking")
@click.option("--min-trust", type=int, default=None, help="Minimum trust score filter")
@click.option("--tier", type=click.Choice(["1", "2", "3"]), default=None, help="Filter by tier")
@click.option("--domain", default=None, help="Filter by domain substring")
@click.pass_context
def source_list(
    ctx: click.Context,
    rank: bool,
    min_trust: int | None,
    tier: str | None,
    domain: str | None,
) -> None:
    registry = _get_registry(ctx)
    if any([min_trust, tier, domain]):
        sources = registry.query_sources(
            min_trust=min_trust,
            tier=int(tier) if tier else None,
            domain=domain,
        )
    else:
        sources = registry.list_sources(apply_rank=rank)
    click.echo(json.dumps(sources, indent=2, default=str))


@source_group.command(name="get", help="Get source details by ID")
@click.argument("source_id")
@click.pass_context
def source_get(ctx: click.Context, source_id: str) -> None:
    registry = _get_registry(ctx)
    result = registry.get_source(source_id)
    if result is None:
        click.echo(f"Source '{source_id}' not found", err=True)
        return
    click.echo(json.dumps(result, indent=2, default=str))


@source_group.command(name="update-trust", help="Override trust score for a source")
@click.argument("source_id")
@click.argument("score", type=int)
@click.pass_context
def source_update_trust(ctx: click.Context, source_id: str, score: int) -> None:
    if not 0 <= score <= 100:
        click.echo("Score must be between 0 and 100", err=True)
        return
    registry = _get_registry(ctx)
    result = registry.update_trust_score(source_id, score)
    if result is None:
        click.echo(f"Source '{source_id}' not found", err=True)
        return
    click.echo(json.dumps(result, indent=2, default=str))


@source_group.command(name="verify", help="Mark a source as re-validated")
@click.argument("source_id")
@click.pass_context
def source_verify(ctx: click.Context, source_id: str) -> None:
    registry = _get_registry(ctx)
    result = registry.verify_source(source_id)
    if result is None:
        click.echo(f"Source '{source_id}' not found", err=True)
        return
    click.echo(json.dumps(result, indent=2, default=str))


@source_group.command(name="stats", help="Show source registry statistics")
@click.pass_context
def source_stats(ctx: click.Context) -> None:
    registry = _get_registry(ctx)
    stats = registry.get_source_stats()
    click.echo(json.dumps(stats, indent=2, default=str))


def _get_registry(ctx: click.Context) -> SourceRegistryService:
    config = ctx.obj.get("config", {})
    storage_cfg = config.get("storage", {})
    db_path = storage_cfg.get("path", "intelgraph.db")
    backend = SQLiteBackend(db_path)
    backend.connect()
    backend.initialize_schema()
    return SourceRegistryService(backend)
