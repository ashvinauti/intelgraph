from __future__ import annotations

import json

import click

from intelgraph.core.graph.anomaly import AnomalyDetector
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node


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


@click.group(name="anomaly", help="Graph anomaly detection and analysis")
def anomaly_group() -> None:
    pass


@anomaly_group.command(name="detect", help="Run full anomaly detection across the graph")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.option("--pretty/--no-pretty", default=True, help="Pretty-print output")
@click.pass_context
def detect(ctx: click.Context, output: str | None, pretty: bool) -> None:
    graph = _build_graph(ctx)
    detector = AnomalyDetector(graph)
    result = detector.detect()
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2 if pretty else None)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2 if pretty else None))


@anomaly_group.command(name="top-n", help="Get top N anomalous nodes")
@click.argument("n", type=int, default=10)
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def top_n(ctx: click.Context, n: int, output: str | None) -> None:
    if n < 1 or n > 1000:
        click.echo("n must be between 1 and 1000", err=True)
        raise click.Abort()
    graph = _build_graph(ctx)
    detector = AnomalyDetector(graph)
    result = detector.top_anomalies(n)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))


@anomaly_group.command(name="timeline", help="Get anomaly timeline for a node")
@click.argument("node_id")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def timeline(ctx: click.Context, node_id: str, output: str | None) -> None:
    graph = _build_graph(ctx)
    detector = AnomalyDetector(graph)
    result = detector.timeline()
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))
