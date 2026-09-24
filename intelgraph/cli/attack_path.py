from __future__ import annotations

import json

import click

from intelgraph.core.graph.attack_path import AttackPathAnalyzer
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


@click.group(name="attack-path", help="Attack path analysis for threat hunting")
def attack_path_group() -> None:
    pass


@attack_path_group.command(name="find", help="Find shortest attack path between two nodes")
@click.argument("source")
@click.argument("target")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def find(ctx: click.Context, source: str, target: str, output: str | None) -> None:
    graph = _build_graph(ctx)
    analyzer = AttackPathAnalyzer(graph)
    result = analyzer.find_shortest_path(source, target)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))


@attack_path_group.command(name="all", help="Enumerate all attack paths from a source")
@click.argument("source")
@click.option("--target", default=None, help="Target node ID (optional)")
@click.option("--max-depth", default=5, type=int, help="Maximum path depth")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def all_paths(
    ctx: click.Context, source: str, target: str | None, max_depth: int, output: str | None
) -> None:
    if max_depth < 1 or max_depth > 10:
        click.echo("max-depth must be between 1 and 10", err=True)
        raise click.Abort()
    graph = _build_graph(ctx)
    analyzer = AttackPathAnalyzer(graph)
    result = analyzer.find_all_paths(source, target, max_depth)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))


@attack_path_group.command(name="critical-nodes", help="Identify critical bottleneck nodes")
@click.option("--max-depth", default=5, type=int, help="Maximum path depth for sampling")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def critical_nodes(ctx: click.Context, max_depth: int, output: str | None) -> None:
    graph = _build_graph(ctx)
    analyzer = AttackPathAnalyzer(graph)
    result = analyzer.critical_nodes(max_depth)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))


@attack_path_group.command(name="surface", help="Map attack surface for an entity")
@click.argument("entity_id")
@click.option("--max-depth", default=4, type=int, help="Maximum traversal depth")
@click.option("--output", "-o", default=None, help="Output file path (JSON)")
@click.pass_context
def surface(ctx: click.Context, entity_id: str, max_depth: int, output: str | None) -> None:
    if max_depth < 1 or max_depth > 10:
        click.echo("max-depth must be between 1 and 10", err=True)
        raise click.Abort()
    graph = _build_graph(ctx)
    analyzer = AttackPathAnalyzer(graph)
    result = analyzer.attack_surface(entity_id, max_depth)
    if output:
        with open(output, "w") as f:
            json.dump(result, f, indent=2)
        click.echo(f"Results written to {output}")
    else:
        click.echo(json.dumps(result, indent=2))
