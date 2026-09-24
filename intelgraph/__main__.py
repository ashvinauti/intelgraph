import click

from intelgraph import __version__
from intelgraph.cli.agent import agent_group
from intelgraph.cli.anomaly import anomaly_group
from intelgraph.cli.attack_path import attack_path_group
from intelgraph.cli.cognitive import cognitive_group
from intelgraph.cli.collect import collect_group
from intelgraph.cli.datasource import datasource_group
from intelgraph.cli.evidence import evidence_group
from intelgraph.cli.graph import graph_group
from intelgraph.cli.metaintel import metaintel_group
from intelgraph.cli.nlp import nlp_group
from intelgraph.cli.ops import ops_group
from intelgraph.cli.prediction import prediction_group
from intelgraph.cli.reasoning import reasoning_group
from intelgraph.cli.report import report_group
from intelgraph.cli.review import review_group
from intelgraph.cli.source import source_group
from intelgraph.cli.task import task_group
from intelgraph.cli.ucos import ucos_group
from intelgraph.cli.verify import verify_group
from intelgraph.core.config import load_config
from intelgraph.core.correlation import CorrelationID
from intelgraph.core.enterprise import load_env_overrides, validate_config
from intelgraph.core.logging import setup_logging


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to config file",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose output",
)
@click.option(
    "--correlation-id",
    "-cid",
    default=None,
    help="Correlation ID for the session",
)
@click.version_option(version=__version__, prog_name="intelgraph")
@click.pass_context
def main(ctx: click.Context, config: str | None, verbose: bool, correlation_id: str | None) -> None:
    ctx.ensure_object(dict)

    correlation = CorrelationID(correlation_id)

    cfg = load_config(config)
    env_overrides = load_env_overrides()
    for key, val in env_overrides.items():
        cfg[key] = val
    try:
        validate_config(cfg)
    except Exception:
        pass
    setup_logging(verbose=verbose, correlation_id=correlation.id, config=cfg)

    ctx.obj["config"] = cfg
    ctx.obj["correlation_id"] = correlation.id
    ctx.obj["verbose"] = verbose

    log = ctx.obj.get("log")
    if log:
        log.debug("session started", version=__version__, correlation_id=correlation.id)


main.add_command(collect_group)
main.add_command(graph_group)
main.add_command(verify_group)
main.add_command(report_group)
main.add_command(task_group)
main.add_command(ops_group)
main.add_command(source_group)
main.add_command(evidence_group)
main.add_command(review_group)
main.add_command(datasource_group)
main.add_command(anomaly_group)
main.add_command(attack_path_group)
main.add_command(reasoning_group)
main.add_command(prediction_group)
main.add_command(nlp_group)
main.add_command(cognitive_group)
main.add_command(agent_group)
main.add_command(metaintel_group)
main.add_command(ucos_group)


if __name__ == "__main__":
    main(obj={})
