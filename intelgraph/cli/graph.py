import json
import sys
from pathlib import Path

import click

from intelgraph.core.graph.algorithms import GraphAlgorithms
from intelgraph.core.graph.analytics import GraphAnalytics
from intelgraph.core.graph.export import ExportSettings, GraphExporter
from intelgraph.core.graph.graph import IntelligenceGraph
from intelgraph.core.graph.influence import InfluencePropagation
from intelgraph.core.graph.node import Node


def _build_graph(ctx: click.Context) -> IntelligenceGraph:
    from intelgraph.core.storage import SQLiteBackend

    cfg = ctx.obj["config"]
    storage_cfg = cfg.get("storage", {})
    db_path = storage_cfg.get("path", "intelgraph.db")
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
            g.adjacency.setdefault(src, set()).add(tgt)
            g.adjacency.setdefault(tgt, set()).add(src)
            g.forward_adjacency.setdefault(src, set()).add(tgt)
            g.reverse_adjacency.setdefault(tgt, set()).add(src)
            g.node_edges.setdefault(src, set()).add(rel.id)
            g.node_edges.setdefault(tgt, set()).add(rel.id)
            g.edge_node_map[rel.id] = (src, tgt)
            from intelgraph.core.graph.edge import Edge

            g.edges[rel.id] = Edge(relationship=rel)
    backend.disconnect()
    return g


@click.group(name="graph", help="Query, inspect, and analyze the intelligence graph")
def graph_group() -> None:
    pass


@graph_group.command(name="query", help="Query entities in the graph")
@click.argument("entity_id")
@click.pass_context
def graph_query(ctx: click.Context, entity_id: str) -> None:
    click.echo(f"query entity: {entity_id} (not yet implemented)")


@graph_group.command(name="centrality", help="Compute centrality for a node")
@click.argument("node_id")
@click.option(
    "--algorithm",
    "-a",
    default="degree",
    type=click.Choice(["degree", "pagerank", "betweenness", "closeness"], case_sensitive=False),
    help="Centrality algorithm",
)
@click.pass_context
def graph_centrality(ctx: click.Context, node_id: str, algorithm: str) -> None:
    g = _build_graph(ctx)
    if node_id not in g.nodes:
        click.echo(f"Error: node '{node_id}' not found in graph", err=True)
        raise click.Abort()
    analytics = GraphAnalytics(g)
    if algorithm == "pagerank":
        result = analytics.page_rank(node_id)
    elif algorithm == "betweenness":
        result = analytics.betweenness_centrality(node_id)
    elif algorithm == "closeness":
        result = analytics.closeness_centrality(node_id)
    else:
        result = analytics.degree_centrality(node_id)
    click.echo(f"Node: {node_id}")
    click.echo(f"Algorithm: {algorithm}")
    click.echo(f"Centrality: {result:.6f}")


@graph_group.command(name="stats", help="Show graph statistics")
@click.option(
    "--detail", is_flag=True, default=False, help="Show detailed statistics (clustering, histogram)"
)
@click.pass_context
def graph_stats(ctx: click.Context, detail: bool) -> None:
    g = _build_graph(ctx)
    analytics = GraphAnalytics(g)
    s = analytics.stats(detail=detail)
    click.echo("Graph Statistics")
    click.echo(f"  Nodes:           {s['node_count']}")
    click.echo(f"  Edges:           {s['edge_count']}")
    click.echo(f"  Density:         {s['density']}")
    click.echo(f"  Average Degree:  {s['average_degree']}")
    if detail:
        click.echo(f"  Clustering Coeff:{s['clustering_coefficient']}")
        click.echo(f"  Max Degree:      {s['max_degree']}")
        click.echo(f"  Min Degree:      {s['min_degree']}")
        click.echo("  Degree Histogram:")
        for entry in s.get("degree_histogram", []):
            click.echo(f"    degree={entry['degree']}: count={entry['count']}")


@graph_group.command(name="export", help="Export graph in GraphML, DOT, or JSON format")
@click.option(
    "--format",
    "-f",
    "fmt",
    default="graphml",
    type=click.Choice(["graphml", "dot", "json"], case_sensitive=False),
    help="Export format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False),
    default=None,
    help="Output file path (default: stdout)",
)
@click.option("--pretty", is_flag=True, default=False, help="Pretty-print output")
@click.option("--gzip", "-z", is_flag=True, default=False, help="Gzip-compress output")
@click.option("--entity-type", multiple=True, help="Include only specific entity types")
@click.option("--exclude-entity-type", multiple=True, help="Exclude specific entity types")
@click.option("--relationship-type", multiple=True, help="Include only specific relationship types")
@click.option(
    "--exclude-relationship-type", multiple=True, help="Exclude specific relationship types"
)
@click.option("--min-confidence", type=int, default=0, help="Minimum confidence score (0-100)")
@click.option("--min-trust-weight", type=int, default=0, help="Minimum trust weight (0-100)")
@click.option("--subgraph-node", default=None, help="Export subgraph from this node")
@click.option("--subgraph-depth", type=int, default=1, help="Subgraph traversal depth")
@click.pass_context
def graph_export(
    ctx: click.Context,
    fmt: str,
    output: str | None,
    pretty: bool,
    gzip: bool,
    entity_type: tuple[str, ...],
    exclude_entity_type: tuple[str, ...],
    relationship_type: tuple[str, ...],
    exclude_relationship_type: tuple[str, ...],
    min_confidence: int,
    min_trust_weight: int,
    subgraph_node: str | None,
    subgraph_depth: int,
) -> None:
    g = _build_graph(ctx)
    if g.node_count == 0:
        click.echo("Error: graph is empty, nothing to export.", err=True)
        raise click.Abort()

    settings = ExportSettings(
        include_entity_types=set(entity_type) if entity_type else None,
        exclude_entity_types=set(exclude_entity_type) if exclude_entity_type else None,
        include_relationship_types=set(relationship_type) if relationship_type else None,
        exclude_relationship_types=(
            set(exclude_relationship_type) if exclude_relationship_type else None
        ),
        min_confidence=min_confidence,
        min_trust_weight=min_trust_weight,
        subgraph_node_id=subgraph_node,
        subgraph_depth=subgraph_depth,
        include_metadata=True,
        pretty=pretty,
        compressed=gzip,
    )

    exporter = GraphExporter(g, settings)
    try:
        content = exporter.export(fmt)
    except Exception as e:
        click.echo(f"Export failed: {e}", err=True)
        raise click.Abort()

    if output:
        out_path = Path(output)
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(out_path, mode) as f:
            f.write(content)
        click.echo(f"Exported to {out_path} ({len(content)} bytes)")
    else:
        if isinstance(content, bytes):
            sys.stdout.buffer.write(content)
        else:
            click.echo(content)


@graph_group.command(name="mst", help="Compute minimum spanning tree")
@click.option(
    "--algorithm",
    "-a",
    default="kruskal",
    type=click.Choice(["kruskal", "prim"], case_sensitive=False),
    help="MST algorithm",
)
@click.pass_context
def graph_mst(ctx: click.Context, algorithm: str) -> None:
    g = _build_graph(ctx)
    if g.node_count == 0:
        click.echo("Error: graph is empty.", err=True)
        raise click.Abort()
    algs = GraphAlgorithms(g)
    if algorithm == "prim":
        result = algs.mst_prim()
    else:
        result = algs.mst_kruskal()
    click.echo(f"Minimum Spanning Tree ({algorithm.upper()})")
    click.echo(f"  Edges:          {result['edge_count']}")
    click.echo(f"  Total Weight:   {result['total_weight']}")
    click.echo(f"  Execution Time: {result['execution_time_ms']}ms")
    if result["edges"]:
        click.echo("  Edges:")
        for e in result["edges"]:
            click.echo(f"    {e['source'][:8]} -- {e['target'][:8]}  (w={e['weight']})")


@graph_group.command(name="scc", help="Find strongly connected components (Tarjan)")
@click.pass_context
def graph_scc(ctx: click.Context) -> None:
    g = _build_graph(ctx)
    if g.node_count == 0:
        click.echo("Error: graph is empty.", err=True)
        raise click.Abort()
    algs = GraphAlgorithms(g)
    result = algs.scc_tarjan()
    click.echo("Strongly Connected Components (Tarjan)")
    click.echo(f"  Components:     {result['count']}")
    click.echo(f"  Execution Time: {result['execution_time_ms']}ms")
    for label, members in result["components"].items():
        click.echo(f"  {label}: {len(members)} nodes")
        for mid in members:
            click.echo(f"    - {mid}")


@graph_group.command(name="diameter", help="Compute graph diameter")
@click.pass_context
def graph_diameter(ctx: click.Context) -> None:
    g = _build_graph(ctx)
    if g.node_count == 0:
        click.echo("Error: graph is empty.", err=True)
        raise click.Abort()
    algs = GraphAlgorithms(g)
    result = algs.diameter()
    click.echo("Graph Diameter")
    click.echo(f"  Diameter:       {result['diameter']}")
    click.echo(f"  From:           {result.get('from_node', '?')[:8]}")
    click.echo(f"  To:             {result.get('to_node', '?')[:8]}")
    click.echo(f"  Path:           {' -> '.join(p[:8] for p in result['path'])}")
    click.echo(f"  Execution Time: {result['execution_time_ms']}ms")


@graph_group.command(name="shortest-path", help="Find shortest path between two nodes")
@click.argument("source_id")
@click.argument("target_id")
@click.option(
    "--algorithm",
    "-a",
    default="astar",
    type=click.Choice(["astar"], case_sensitive=False),
    help="Path algorithm",
)
@click.pass_context
def graph_shortest_path(ctx: click.Context, source_id: str, target_id: str, algorithm: str) -> None:
    g = _build_graph(ctx)
    if source_id not in g.nodes:
        click.echo(f"Error: source node '{source_id}' not found", err=True)
        raise click.Abort()
    if target_id not in g.nodes:
        click.echo(f"Error: target node '{target_id}' not found", err=True)
        raise click.Abort()
    algs = GraphAlgorithms(g)
    result = algs.astar(source_id, target_id)
    if result["path"]:
        click.echo("Shortest Path (A*)")
        click.echo(f"  Length:         {result['length']}")
        click.echo(f"  Total Cost:     {result.get('total_cost', 'N/A')}")
        click.echo(f"  Nodes Visited:  {result.get('nodes_visited', 'N/A')}")
        click.echo(f"  Execution Time: {result['execution_time_ms']}ms")
        click.echo("  Path:")
        for i, pid in enumerate(result["path"]):
            marker = " -> " if i < len(result["path"]) - 1 else ""
            click.echo(f"    {i + 1}. {pid}{marker}")
    else:
        click.echo(f"No path found between {source_id[:8]} and {target_id[:8]}")


def _get_influence(ctx: click.Context) -> InfluencePropagation:
    return InfluencePropagation(_build_graph(ctx))


@graph_group.command(name="pagerank", help="Compute standard PageRank")
@click.option("--damping", "-d", default=0.85, type=float, help="Damping factor (0-1)")
@click.option("--max-iterations", "-i", default=100, type=int, help="Maximum iterations")
@click.option("--tolerance", "-t", default=1e-8, type=float, help="Convergence tolerance")
@click.option("--top", "-n", default=None, type=int, help="Show only top N nodes")
@click.pass_context
def graph_pagerank(
    ctx: click.Context, damping: float, max_iterations: int, tolerance: float, top: int | None
) -> None:
    infl = _get_influence(ctx)
    result = infl.page_rank(damping, max_iterations, tolerance)
    click.echo(
        f"PageRank ({'converged' if result['converged'] else 'did not converge'} in {result['iterations']} iterations)"
    )
    click.echo(f"  Execution Time: {result['execution_time_ms']}ms")
    scores = result["scores"]
    items = list(scores.items())[:top] if top else list(scores.items())
    for nid, score in items:
        click.echo(f"  {nid}: {score}")
    if top and len(scores) > top:
        click.echo(f"  ... and {len(scores) - top} more")


@graph_group.command(
    name="weighted-pagerank", help="Compute weighted PageRank using edge confidence/trust weights"
)
@click.option("--damping", "-d", default=0.85, type=float, help="Damping factor (0-1)")
@click.option("--max-iterations", "-i", default=100, type=int, help="Maximum iterations")
@click.option("--tolerance", "-t", default=1e-8, type=float, help="Convergence tolerance")
@click.option("--top", "-n", default=None, type=int, help="Show only top N nodes")
@click.pass_context
def graph_weighted_pagerank(
    ctx: click.Context, damping: float, max_iterations: int, tolerance: float, top: int | None
) -> None:
    g = _build_graph(ctx)

    def weight_fn(e):
        return float(e.relationship.confidence_score) / 100.0 if e.relationship else 1.0

    infl = InfluencePropagation(g, weight_fn=weight_fn)
    result = infl.weighted_page_rank(damping, max_iterations, tolerance)
    click.echo(
        f"Weighted PageRank ({'converged' if result['converged'] else 'did not converge'} in {result['iterations']} iterations)"
    )
    click.echo(f"  Execution Time: {result['execution_time_ms']}ms")
    scores = result["scores"]
    items = list(scores.items())[:top] if top else list(scores.items())
    for nid, score in items:
        click.echo(f"  {nid}: {score}")
    if top and len(scores) > top:
        click.echo(f"  ... and {len(scores) - top} more")


@graph_group.command(
    name="influence-propagation", help="Run threshold-based influence propagation from seed nodes"
)
@click.option(
    "--seeds",
    "-s",
    required=True,
    help='JSON dict of seed nodes and initial influence values, e.g. \'{"id1":1.0,"id2":0.8}\'',
)
@click.option("--threshold", "-t", default=0.5, type=float, help="Activation threshold (0-1)")
@click.option("--decay", "-d", default=0.5, type=float, help="Decay factor (0-1)")
@click.option("--max-depth", "-m", default=10, type=int, help="Maximum propagation depth")
@click.pass_context
def graph_influence_propagation(
    ctx: click.Context, seeds: str, threshold: float, decay: float, max_depth: int
) -> None:
    try:
        seed_nodes = json.loads(seeds)
    except json.JSONDecodeError:
        click.echo("Error: seeds must be valid JSON", err=True)
        raise click.Abort()
    if not isinstance(seed_nodes, dict):
        click.echo("Error: seeds must be a JSON object (dict)", err=True)
        raise click.Abort()
    infl = _get_influence(ctx)
    result = infl.influence_propagation(seed_nodes, threshold, decay, max_depth)
    click.echo("Influence Propagation")
    click.echo(f"  Threshold:      {result['threshold']}")
    click.echo(f"  Decay Factor:   {result['decay_factor']}")
    click.echo(f"  Max Depth:      {result['max_depth']}")
    click.echo(f"  Seed Count:     {result['seed_count']}")
    click.echo(f"  Nodes Activated: {result['nodes_activated']}")
    click.echo(f"  Execution Time: {result['execution_time_ms']}ms")
    click.echo("  Influence Scores:")
    for nid, score in result["influence"].items():
        click.echo(f"    {nid}: {score}")


@graph_group.command(
    name="influence-scores", help="Compute composite influence scores for all nodes"
)
@click.option("--top", "-n", default=None, type=int, help="Show only top N nodes")
@click.pass_context
def graph_influence_scores(ctx: click.Context, top: int | None) -> None:
    infl = _get_influence(ctx)
    result = infl.influence_scores()
    click.echo("Influence Scores (composite: PR*0.5 + degree_norm*0.3 + outbound*0.2)")
    click.echo(f"  Execution Time: {result['execution_time_ms']}ms")
    scores = result["scores"]
    items = list(scores.items())[:top] if top else list(scores.items())
    for nid, score in items:
        click.echo(f"  {nid}: {score}")
    if top and len(scores) > top:
        click.echo(f"  ... and {len(scores) - top} more")


@graph_group.command(name="top-influence", help="Show top N influence nodes")
@click.argument("n", type=int, default=10)
@click.pass_context
def graph_top_influence(ctx: click.Context, n: int) -> None:
    infl = _get_influence(ctx)
    result = infl.top_influence_nodes(n)
    click.echo(f"Top {result['count']} Influence Nodes (of {result['total_nodes']} total)")
    click.echo(f"  Execution Time: {result['execution_time_ms']}ms")
    for nid, score in result["top_nodes"].items():
        click.echo(f"  #{list(result['top_nodes'].keys()).index(nid) + 1}: {nid} - {score}")
