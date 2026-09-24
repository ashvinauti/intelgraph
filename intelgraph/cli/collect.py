import json

import click

from intelgraph.core.collection import CollectionManager
from intelgraph.core.source_registry import SourceRegistryService
from intelgraph.core.storage import SQLiteBackend


@click.group(name="collect", help="Collect intelligence from sources")
def collect_group() -> None:
    pass


def _get_manager(ctx: click.Context) -> CollectionManager:
    config = ctx.obj.get("config", {})
    storage_cfg = config.get("storage", {})
    db_path = storage_cfg.get("path", "intelgraph.db")
    backend = SQLiteBackend(db_path)
    backend.connect()
    backend.initialize_schema()
    registry = SourceRegistryService(backend)
    return CollectionManager(backend, registry, config)


@collect_group.command(name="url", help="Collect data from a URL")
@click.argument("url")
@click.option(
    "--collector",
    "-c",
    default="web_scraper",
    type=click.Choice(["http", "web_scraper", "api", "rss"]),
)
@click.option("--tier", "-t", type=click.Choice(["1", "2", "3"]), default="2")
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--force", is_flag=True, default=False)
@click.pass_context
def collect_url(
    ctx: click.Context, url: str, collector: str, tier: str, dry_run: bool, force: bool
) -> None:
    mgr = _get_manager(ctx)
    result = mgr.collect(
        collector_name=collector,
        target=url,
        source_tier=int(tier),
        dry_run=dry_run,
        force=force,
    )
    click.echo(
        json.dumps(
            {
                "collector": result.collector_name,
                "target": result.target,
                "success": result.success,
                "error": result.error,
                "documents": len(result.documents),
                "evidence_count": len(result.evidence),
                "collection_time_ms": round(result.collection_time_ms, 2),
                "provenance_id": result.provenance.collection_id if result.provenance else None,
            },
            indent=2,
            default=str,
        )
    )


@collect_group.command(name="file", help="Collect data from a local file")
@click.argument("path")
@click.option("--tier", "-t", type=click.Choice(["1", "2", "3"]), default="2")
@click.option("--force", is_flag=True, default=False)
@click.pass_context
def collect_file(ctx: click.Context, path: str, tier: str, force: bool) -> None:
    mgr = _get_manager(ctx)
    result = mgr.collect(
        collector_name="file",
        target=path,
        source_tier=int(tier),
        force=force,
    )
    click.echo(
        json.dumps(
            {
                "collector": result.collector_name,
                "target": result.target,
                "success": result.success,
                "error": result.error,
                "documents": len(result.documents),
                "evidence_count": len(result.evidence),
                "collection_time_ms": round(result.collection_time_ms, 2),
                "provenance_id": result.provenance.collection_id if result.provenance else None,
                "content_preview": (result.documents[0].content[:200] if result.documents else ""),
            },
            indent=2,
            default=str,
        )
    )


@collect_group.command(name="list-collectors", help="List available collectors")
@click.pass_context
def list_collectors(ctx: click.Context) -> None:
    mgr = _get_manager(ctx)
    click.echo(json.dumps(mgr.list_collectors(), indent=2))


@collect_group.command(name="company", help="Collect data about a company (scaffold)")
@click.argument("name")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def collect_company(ctx: click.Context, name: str, dry_run: bool) -> None:
    _get_manager(ctx)
    if dry_run:
        click.echo(json.dumps({"collector": "company", "target": name, "dry_run": True}, indent=2))
        return
    click.echo(
        json.dumps(
            {
                "collector": "company",
                "target": name,
                "message": "Company collector not yet implemented — use collect url instead",
            },
            indent=2,
        )
    )


@collect_group.command(name="person", help="Collect data about a person (scaffold)")
@click.argument("name")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def collect_person(ctx: click.Context, name: str, dry_run: bool) -> None:
    _get_manager(ctx)
    if dry_run:
        click.echo(json.dumps({"collector": "person", "target": name, "dry_run": True}, indent=2))
        return
    click.echo(
        json.dumps(
            {
                "collector": "person",
                "target": name,
                "message": "Person collector not yet implemented — use collect url instead",
            },
            indent=2,
        )
    )


@collect_group.command(name="domain", help="Collect data about a domain (scaffold)")
@click.argument("domain")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def collect_domain(ctx: click.Context, domain: str, dry_run: bool) -> None:
    _get_manager(ctx)
    if dry_run:
        click.echo(json.dumps({"collector": "domain", "target": domain, "dry_run": True}, indent=2))
        return
    click.echo(
        json.dumps(
            {
                "collector": "domain",
                "target": domain,
                "message": "Domain scaffold — use collect url instead",
            },
            indent=2,
        )
    )


@collect_group.command(name="username", help="Collect data about a username (scaffold)")
@click.argument("username")
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def collect_username(ctx: click.Context, username: str, dry_run: bool) -> None:
    _get_manager(ctx)
    if dry_run:
        click.echo(
            json.dumps({"collector": "username", "target": username, "dry_run": True}, indent=2)
        )
        return
    click.echo(
        json.dumps(
            {
                "collector": "username",
                "target": username,
                "message": "Username scaffold — use collect url instead",
            },
            indent=2,
        )
    )
