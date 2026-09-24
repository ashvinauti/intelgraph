import json

import click

from intelgraph.core.evidence_chain import ChainManager
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.reporting.reports import ReportBuilder
from intelgraph.core.source_registry import SourceRegistryService
from intelgraph.core.storage import SQLiteBackend
from intelgraph.core.verification.manager import VerificationManager


@click.group(name="report", help="Generate investigation reports")
def report_group() -> None:
    pass


def _get_services(
    ctx: click.Context,
) -> tuple[VerificationManager, ChainManager, SourceRegistryService, IntelligenceGraph]:
    config = ctx.obj.get("config", {})
    storage_cfg = config.get("storage", {})
    db_path = storage_cfg.get("path", "intelgraph.db")
    backend = SQLiteBackend(db_path)
    backend.connect()
    backend.initialize_schema()

    vm = VerificationManager(backend)
    vm.initialize()

    cm = ChainManager(backend)
    cm.initialize()

    sr = SourceRegistryService(backend)

    g = IntelligenceGraph()

    return vm, cm, sr, g


def _build_report_builder(
    vm: VerificationManager,
    cm: ChainManager,
    sr: SourceRegistryService,
    g: IntelligenceGraph,
) -> ReportBuilder:
    return ReportBuilder(
        verification_lookup=lambda eid: (
            vm.get_verification(eid).to_dict() if vm.get_verification(eid) else None
        ),
        chain_lookup=lambda eid: (
            cm.get_chain_by_entity(eid).to_dict() if cm.get_chain_by_entity(eid) else None
        ),
        source_lookup=lambda sid: sr.get_source(sid),
        graph=g,
    )


@report_group.command(name="entity", help="Entity report")
@click.argument("entity_id")
@click.option("--format", "-f", type=click.Choice(["json", "markdown", "html"]), default="json")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default=None)
@click.pass_context
def report_entity(ctx: click.Context, entity_id: str, format: str, output: str | None) -> None:
    vm, cm, sr, g = _get_services(ctx)
    rb = _build_report_builder(vm, cm, sr, g)
    result = rb.entity_report(entity_id, fmt=format)
    if output:
        with open(output, "w") as f:
            f.write(result)
        click.echo(json.dumps({"written": output}))
    else:
        click.echo(result)


@report_group.command(name="evidence", help="Evidence report")
@click.argument("entity_id")
@click.option("--format", "-f", type=click.Choice(["json", "markdown", "html"]), default="json")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default=None)
@click.pass_context
def report_evidence(ctx: click.Context, entity_id: str, format: str, output: str | None) -> None:
    vm, cm, sr, g = _get_services(ctx)
    rb = _build_report_builder(vm, cm, sr, g)
    result = rb.evidence_report(entity_id, fmt=format)
    if output:
        with open(output, "w") as f:
            f.write(result)
        click.echo(json.dumps({"written": output}))
    else:
        click.echo(result)


@report_group.command(name="verification", help="Verification report")
@click.argument("entity_id")
@click.option("--format", "-f", type=click.Choice(["json", "markdown", "html"]), default="json")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default=None)
@click.pass_context
def report_verification(
    ctx: click.Context, entity_id: str, format: str, output: str | None
) -> None:
    vm, cm, sr, g = _get_services(ctx)
    rb = _build_report_builder(vm, cm, sr, g)
    result = rb.verification_report(entity_id, fmt=format)
    if output:
        with open(output, "w") as f:
            f.write(result)
        click.echo(json.dumps({"written": output}))
    else:
        click.echo(result)


@report_group.command(name="source", help="Source report")
@click.argument("source_id")
@click.option("--format", "-f", type=click.Choice(["json", "markdown", "html"]), default="json")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default=None)
@click.pass_context
def report_source(ctx: click.Context, source_id: str, format: str, output: str | None) -> None:
    vm, cm, sr, g = _get_services(ctx)
    rb = _build_report_builder(vm, cm, sr, g)
    result = rb.source_report(source_id, fmt=format)
    if output:
        with open(output, "w") as f:
            f.write(result)
        click.echo(json.dumps({"written": output}))
    else:
        click.echo(result)


@report_group.command(name="full", help="Full system report")
@click.option("--format", "-f", type=click.Choice(["json", "markdown", "html"]), default="json")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default=None)
@click.pass_context
def report_full(ctx: click.Context, format: str, output: str | None) -> None:
    vm, cm, sr, g = _get_services(ctx)
    rb = _build_report_builder(vm, cm, sr, g)
    result = rb.full_report(fmt=format)
    if output:
        with open(output, "w") as f:
            f.write(result)
        click.echo(json.dumps({"written": output}))
    else:
        click.echo(result)
