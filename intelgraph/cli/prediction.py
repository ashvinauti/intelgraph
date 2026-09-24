from __future__ import annotations

import json

import click

from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.graph.prediction import Predictor
from intelgraph.core.kernel.execution import UnifiedExecutionKernel


def _build_graph(ctx: click.Context) -> IntelligenceGraph:
    from intelgraph.core.storage.sqlite_backend import SQLiteBackend

    cfg = ctx.obj["config"]
    db_path = cfg.get("storage", {}).get("path", "intelgraph.db")
    backend = SQLiteBackend(db_path)
    backend.connect()
    g = IntelligenceGraph()
    for entity in backend.list_entities():
        eid = entity.id
        g.nodes[eid] = Node(entity=entity)
        g.adjacency.setdefault(eid, set())
        g.forward_adjacency.setdefault(eid, set())
        g.reverse_adjacency.setdefault(eid, set())
        g.node_edges.setdefault(eid, set())
    for rel in backend.list_relationships():
        src = rel.source_id
        tgt = rel.target_id
        if src in g.nodes and tgt in g.nodes:
            from intelgraph.core.graph.edge import Edge

            g.adjacency.setdefault(src, set()).add(tgt)
            g.adjacency.setdefault(tgt, set()).add(src)
            g.forward_adjacency.setdefault(src, set()).add(tgt)
            g.reverse_adjacency.setdefault(tgt, set()).add(src)
            g.node_edges.setdefault(src, set()).add(rel.id)
            g.node_edges.setdefault(tgt, set()).add(rel.id)
            g.edge_node_map[rel.id] = (src, tgt)
            g.edges[rel.id] = Edge(relationship=rel)
    return g


@click.group(name="prediction", help="Predictive analysis and forecasting engine")
def prediction_group() -> None:
    pass


@prediction_group.command(name="explain", help="Explain prediction with feature importance")
@click.argument("features_json")
@click.argument("contributions_json")
@click.option("--top-n", default=5, type=int)
@click.pass_context
def explain(ctx: click.Context, features_json: str, contributions_json: str, top_n: int) -> None:
    from intelgraph.core.explainability.interpreter import FeatureImportance

    try:
        features = json.loads(features_json)
        contributions = json.loads(contributions_json)
    except json.JSONDecodeError as e:
        click.echo(f"Invalid JSON: {e}", err=True)
        raise click.Abort()
    fi = FeatureImportance()
    result = fi.compute_importance(features, contributions, top_n)
    click.echo(json.dumps([e.to_dict() for e in result], indent=2))


@prediction_group.command(name="safety-check", help="Check prediction against safety constraints")
@click.argument("prediction_type")
@click.argument("value", type=float)
@click.pass_context
def safety_check(ctx: click.Context, prediction_type: str, value: float) -> None:
    from intelgraph.core.safety.guard import SafetyGuard

    guard = SafetyGuard()
    result = guard.check_prediction(prediction_type, value)
    click.echo(json.dumps(result.to_dict(), indent=2))


@prediction_group.command(name="compliance", help="Check prediction compliance")
@click.argument("prediction_type")
@click.argument("value", type=float)
@click.option("--entity-risk", default=0.0, type=float)
@click.pass_context
def compliance(ctx: click.Context, prediction_type: str, value: float, entity_risk: float) -> None:
    from intelgraph.core.governance.policy import ComplianceChecker

    checker = ComplianceChecker()
    result = checker.check(prediction_type, value, entity_risk)
    click.echo(json.dumps(result.to_dict(), indent=2))


@prediction_group.command(name="approve", help="Request approval for high-risk prediction")
@click.argument("prediction_type")
@click.argument("entity_id")
@click.argument("value", type=float)
@click.argument("risk_score", type=float)
@click.option("--justification", default="")
@click.pass_context
def approve(
    ctx: click.Context,
    prediction_type: str,
    entity_id: str,
    value: float,
    risk_score: float,
    justification: str,
) -> None:
    from intelgraph.core.governance.policy import ApprovalWorkflow

    wf = ApprovalWorkflow()
    req = wf.request_approval(prediction_type, entity_id, value, risk_score, justification)
    click.echo(json.dumps(req.to_dict(), indent=2))


@prediction_group.command(name="forecast", help="Full multi-horizon forecast for a node")
@click.argument("node_id")
@click.option("--horizon", default=1, type=int, help="Forecast horizon (0=short, 1=medium, 2=long)")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def forecast(ctx: click.Context, node_id: str, horizon: int, output: str | None) -> None:
    graph = _build_graph(ctx)
    if node_id not in graph.nodes:
        click.echo(f"Node {node_id} not found", err=True)
        raise click.Abort()
    predictor = Predictor(graph)
    result = predictor.full_forecast(node_id)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))


@prediction_group.command(name="risk", help="Risk forecast for a node")
@click.argument("node_id")
@click.option("--horizon", default=1, type=int, help="Forecast horizon")
@click.pass_context
def risk(ctx: click.Context, node_id: str, horizon: int) -> None:
    graph = _build_graph(ctx)
    predictor = Predictor(graph)
    result = predictor.risk_forecast(node_id, horizon)
    click.echo(json.dumps(result.to_dict(), indent=2))


@prediction_group.command(name="counterfactual", help="What-if counterfactual estimation")
@click.argument("node_id")
@click.option("--what-if", default="{}", help="JSON dict of feature adjustments")
@click.pass_context
def counterfactual(ctx: click.Context, node_id: str, what_if: str) -> None:
    graph = _build_graph(ctx)
    predictor = Predictor(graph)
    try:
        wf = json.loads(what_if)
    except json.JSONDecodeError:
        click.echo("Invalid JSON for what-if", err=True)
        raise click.Abort()
    result = predictor.counterfactual(node_id, wf)
    click.echo(json.dumps(result.to_dict(), indent=2))


@prediction_group.command(name="execute", help="Execute unified intelligence kernel (Phases 24-27)")
@click.option("--anomaly-node", default=None, help="Anomaly node ID for root cause analysis")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def execute(ctx: click.Context, anomaly_node: str | None, output: str | None) -> None:
    graph = _build_graph(ctx)
    kernel = UnifiedExecutionKernel(graph)
    result = kernel.execute(anomaly_node=anomaly_node)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))
