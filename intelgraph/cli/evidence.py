import json

import click

from intelgraph.core.evidence_chain import ChainManager
from intelgraph.core.storage import SQLiteBackend


@click.group(name="evidence", help="Manage evidence chains")
def evidence_group() -> None:
    pass


def _get_manager(ctx: click.Context) -> ChainManager:
    config = ctx.obj.get("config", {})
    storage_cfg = config.get("storage", {})
    db_path = storage_cfg.get("path", "intelgraph.db")
    backend = SQLiteBackend(db_path)
    backend.connect()
    backend.initialize_schema()
    mgr = ChainManager(backend)
    mgr.initialize()
    return mgr


@evidence_group.command(name="chain", help="Get evidence chain for an entity")
@click.argument("entity_id")
@click.option("--full", is_flag=True, default=False, help="Show full evidence items")
@click.pass_context
def evidence_chain(ctx: click.Context, entity_id: str, full: bool) -> None:
    mgr = _get_manager(ctx)
    chain = mgr.get_chain_by_entity(entity_id)
    if chain is None:
        click.echo(json.dumps({"error": f"No chain found for entity {entity_id}"}, indent=2))
        return
    d = chain.to_dict()
    if not full:
        d["evidence"] = [
            {
                "evidence_id": e["evidence_id"],
                "claim": e["claim"][:80],
                "support_type": e["support_type"],
            }
            for e in d["evidence"]
        ]
    click.echo(json.dumps(d, indent=2, default=str))


@evidence_group.command(name="list", help="List evidence chains")
@click.option(
    "--status", type=click.Choice(["verified", "contested", "unknown", "debunked"]), default=None
)
@click.option("--min-confidence", type=float, default=None)
@click.option("--contradictions", is_flag=True, default=False, help="Only contested chains")
@click.pass_context
def evidence_list(
    ctx: click.Context, status: str | None, min_confidence: float | None, contradictions: bool
) -> None:
    mgr = _get_manager(ctx)
    chains = mgr.list_chains(
        status=status, min_confidence=min_confidence, only_contradictions=contradictions
    )
    result = [
        {
            "chain_id": c.chain_id[:12],
            "entity_id": c.entity_id[:12],
            "confidence": c.confidence,
            "contradiction_score": c.contradiction_score,
            "status": c.status.name_lower,
            "evidence_count": c.evidence_count,
            "source_count": c.source_count,
        }
        for c in chains
    ]
    click.echo(json.dumps(result, indent=2, default=str))


@evidence_group.command(name="add", help="Add evidence to an entity's chain")
@click.argument("entity_id")
@click.argument("source_id")
@click.argument("document_id")
@click.argument("claim")
@click.option(
    "--support", type=click.Choice(["supports", "contradicts", "neutral"]), default="supports"
)
@click.option("--confidence", type=float, default=50.0)
@click.pass_context
def evidence_add(
    ctx: click.Context,
    entity_id: str,
    source_id: str,
    document_id: str,
    claim: str,
    support: str,
    confidence: float,
) -> None:
    mgr = _get_manager(ctx)
    chain = mgr.add_evidence(
        entity_id=entity_id,
        source_id=source_id,
        document_id=document_id,
        claim=claim,
        support_type=support,
        confidence=confidence,
    )
    d = chain.to_dict()
    d["evidence"] = [
        {
            "evidence_id": e["evidence_id"],
            "claim": e["claim"][:60],
            "support_type": e["support_type"],
        }
        for e in d["evidence"]
    ]
    click.echo(json.dumps(d, indent=2, default=str))


@evidence_group.command(name="recompute", help="Recompute confidence for an entity's chain")
@click.argument("entity_id")
@click.pass_context
def evidence_recompute(ctx: click.Context, entity_id: str) -> None:
    mgr = _get_manager(ctx)
    chain = mgr.recompute_confidence(entity_id)
    if chain is None:
        click.echo(json.dumps({"error": f"No chain found for entity {entity_id}"}, indent=2))
        return
    click.echo(
        json.dumps(
            {
                "chain_id": chain.chain_id[:12],
                "entity_id": chain.entity_id,
                "confidence": chain.confidence,
                "contradiction_score": chain.contradiction_score,
                "status": chain.status.name_lower,
                "version": chain.version,
            },
            indent=2,
            default=str,
        )
    )


@evidence_group.command(name="contradictions", help="List chains with contradictions")
@click.pass_context
def evidence_contradictions(ctx: click.Context) -> None:
    mgr = _get_manager(ctx)
    chains = mgr.get_contradictions()
    result = [
        {
            "chain_id": c.chain_id[:12],
            "entity_id": c.entity_id[:12],
            "contradiction_score": c.contradiction_score,
            "confidence": c.confidence,
            "evidence_count": c.evidence_count,
        }
        for c in chains
    ]
    click.echo(json.dumps(result, indent=2, default=str))


@evidence_group.command(name="stats", help="Evidence chain statistics")
@click.pass_context
def evidence_stats(ctx: click.Context) -> None:
    mgr = _get_manager(ctx)
    click.echo(json.dumps(mgr.stats(), indent=2, default=str))


@evidence_group.command(name="validate", help="Validate an entity's evidence chain")
@click.argument("entity_id")
@click.pass_context
def evidence_validate(ctx: click.Context, entity_id: str) -> None:
    mgr = _get_manager(ctx)
    click.echo(json.dumps(mgr.validate(entity_id), indent=2, default=str))
