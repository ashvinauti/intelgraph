import json

import click

from intelgraph.core.storage import SQLiteBackend
from intelgraph.core.verification import VerificationManager


@click.group(name="verify", help="Verify entities and relationships")
def verify_group() -> None:
    pass


def _get_manager(ctx: click.Context) -> VerificationManager:
    config = ctx.obj.get("config", {})
    storage_cfg = config.get("storage", {})
    db_path = storage_cfg.get("path", "intelgraph.db")
    backend = SQLiteBackend(db_path)
    backend.connect()
    backend.initialize_schema()
    mgr = VerificationManager(backend)
    mgr.initialize()
    return mgr


@verify_group.command(name="status", help="Get verification status for an entity")
@click.argument("entity_id")
@click.pass_context
def verify_status(ctx: click.Context, entity_id: str) -> None:
    mgr = _get_manager(ctx)
    record = mgr.get_verification(entity_id)
    if record is None:
        click.echo(
            json.dumps(
                {"error": f"No verification record found for {entity_id}", "entity_id": entity_id},
                indent=2,
            )
        )
        return
    click.echo(json.dumps(record.to_dict(), indent=2))


@verify_group.command(name="list", help="List verification records")
@click.option("--status", "-s", default=None, help="Filter by verification state")
@click.option("--operational", "-o", default=None, help="Filter by operational state")
@click.option("--min-confidence", "-mc", type=float, default=None, help="Minimum confidence filter")
@click.option("--high-impact", is_flag=True, default=False, help="Show only high-impact entities")
@click.pass_context
def verify_list(
    ctx: click.Context,
    status: str | None,
    operational: str | None,
    min_confidence: float | None,
    high_impact: bool,
) -> None:
    mgr = _get_manager(ctx)
    records = mgr.list_verifications(
        status=status,
        operational=operational,
        min_confidence=min_confidence,
        high_impact_only=high_impact,
    )
    click.echo(json.dumps(records, indent=2, default=str))


@verify_group.command(name="recompute", help="Recompute verification for an entity")
@click.argument("entity_id")
@click.option("--force", is_flag=True, default=False, help="Force recompute even if unchanged")
@click.pass_context
def verify_recompute(ctx: click.Context, entity_id: str, force: bool) -> None:
    mgr = _get_manager(ctx)
    record = mgr.recompute(entity_id)
    if record is None:
        click.echo(
            json.dumps(
                {"error": f"No evidence chain found for {entity_id}; cannot compute verification"},
                indent=2,
            )
        )
        return
    click.echo(json.dumps(record.to_dict(), indent=2, default=str))


@verify_group.command(name="recompute-all", help="Recompute all verification records")
@click.pass_context
def verify_recompute_all(ctx: click.Context) -> None:
    mgr = _get_manager(ctx)
    count = mgr.recompute_all()
    click.echo(json.dumps({"recomputed": count}, indent=2))


@verify_group.command(name="stats", help="Show verification statistics")
@click.pass_context
def verify_stats(ctx: click.Context) -> None:
    mgr = _get_manager(ctx)
    stats = mgr.stats()
    click.echo(json.dumps(stats, indent=2))


@verify_group.command(name="high-impact", help="List high-impact unverified entities")
@click.pass_context
def verify_high_impact(ctx: click.Context) -> None:
    mgr = _get_manager(ctx)
    unverified = mgr.get_high_impact_unverified()
    click.echo(json.dumps(unverified, indent=2, default=str))


@verify_group.command(name="history", help="Show verification history for an entity")
@click.argument("entity_id")
@click.pass_context
def verify_history(ctx: click.Context, entity_id: str) -> None:
    mgr = _get_manager(ctx)
    history = mgr.get_history(entity_id)
    click.echo(json.dumps(history, indent=2, default=str))


@verify_group.command(name="safety", help="Run safety check on an entity")
@click.argument("entity_id")
@click.pass_context
def verify_safety(ctx: click.Context, entity_id: str) -> None:
    from intelgraph.core.verification.safety import SafetyChecker

    mgr = _get_manager(ctx)
    record = mgr.get_verification(entity_id)
    if record is None:
        click.echo(json.dumps({"error": f"No verification record for {entity_id}"}, indent=2))
        return

    source_trust_scores = []
    source_domains = []

    chain = mgr.get_chain_by_entity(entity_id)
    if chain:
        for e in chain.get("evidence", []):
            source_trust_scores.append(int(e.get("confidence", 0)))
            if e.get("source_id", "").startswith("http"):
                source_domains.append(e.get("source_id", ""))

    safety = SafetyChecker.full_check(
        source_trust_scores=source_trust_scores,
        source_domains=source_domains,
        contradiction=record.contradiction,
        verification_state=record.verification_state.name_lower,
    )
    click.echo(
        json.dumps(
            {
                "entity_id": entity_id,
                "is_safe": safety.is_safe,
                "severity": safety.severity,
                "flags": safety.flags,
                "warnings": safety.warnings,
            },
            indent=2,
        )
    )


@verify_group.command(name="set", help="Manually set verification or operational state")
@click.argument("entity_id")
@click.option(
    "--state",
    "-s",
    default=None,
    help="Verification state: confirmed, probable, possible, speculative",
)
@click.option(
    "--operational",
    "-o",
    default=None,
    help="Operational state: active, contested, debunked, archived",
)
@click.option("--reason", "-r", default="", help="Reason for the change")
@click.pass_context
def verify_set(
    ctx: click.Context,
    entity_id: str,
    state: str | None,
    operational: str | None,
    reason: str,
) -> None:
    mgr = _get_manager(ctx)

    try:
        record = mgr.update_state(
            entity_id,
            verification_state=state,
            operational_state=operational,
            reasoning=reason,
        )
    except KeyError as e:
        click.echo(
            json.dumps(
                {
                    "error": f"Invalid state: {e}. Valid verification: confirmed, probable, possible, speculative. Valid operational: active, contested, debunked, archived"
                },
                indent=2,
            )
        )
        return

    if record is None:
        click.echo(json.dumps({"error": f"No verification record for {entity_id}"}, indent=2))
        return

    click.echo(json.dumps(record.to_dict(), indent=2, default=str))
