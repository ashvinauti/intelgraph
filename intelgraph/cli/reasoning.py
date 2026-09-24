from __future__ import annotations

import json

import click

from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.node import Node
from intelgraph.core.graph.reasoning import CausalReasoner


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


@click.group(name="reasoning", help="Causal analysis and reasoning engine")
def reasoning_group() -> None:
    pass


@reasoning_group.command(name="root-cause", help="Root cause analysis from an anomaly node")
@click.argument("anomaly_node")
@click.option("--max-depth", default=5, type=int, help="Maximum causal depth")
@click.option("--max-causes", default=10, type=int, help="Maximum root causes to return")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def root_cause(
    ctx: click.Context, anomaly_node: str, max_depth: int, max_causes: int, output: str | None
) -> None:
    graph = _build_graph(ctx)
    reasoner = CausalReasoner(graph)
    result = reasoner.root_cause_analysis(anomaly_node, max_depth, max_causes)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))


@reasoning_group.command(name="causal-path", help="Discover causal path between two nodes")
@click.argument("source")
@click.argument("target")
@click.option("--max-depth", default=5, type=int, help="Maximum path depth")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def causal_path(
    ctx: click.Context, source: str, target: str, max_depth: int, output: str | None
) -> None:
    graph = _build_graph(ctx)
    reasoner = CausalReasoner(graph)
    result = reasoner.causal_path(source, target, max_depth)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))


@reasoning_group.command(name="explain", help="Get causal explanation for a node")
@click.argument("node_id")
@click.option("--max-depth", default=5, type=int, help="Maximum ancestor/descendant depth")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def explain(ctx: click.Context, node_id: str, max_depth: int, output: str | None) -> None:
    graph = _build_graph(ctx)
    reasoner = CausalReasoner(graph)
    result = reasoner.explain(node_id, max_depth)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))


@reasoning_group.command(name="chains", help="Get causal chains for a node")
@click.argument("node_id")
@click.option("--max-depth", default=5, type=int, help="Maximum chain depth")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def chains(ctx: click.Context, node_id: str, max_depth: int, output: str | None) -> None:
    graph = _build_graph(ctx)
    reasoner = CausalReasoner(graph)
    result = reasoner.chains(node_id, max_depth)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))


@reasoning_group.command(name="top-causes", help="Get top ranked root causes")
@click.argument("node_id")
@click.option("--max-depth", default=5, type=int, help="Maximum causal depth")
@click.option("--top-n", default=10, type=int, help="Number of top causes to return")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def top_causes(
    ctx: click.Context, node_id: str, max_depth: int, top_n: int, output: str | None
) -> None:
    graph = _build_graph(ctx)
    reasoner = CausalReasoner(graph)
    result = reasoner.top_causes(node_id, max_depth, top_n)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))
