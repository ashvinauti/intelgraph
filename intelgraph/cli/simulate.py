"""CLI for generating synthetic adversary-network simulations.

`intelgraph simulate network` produces seeded, parameterized simulated
threat-actor campaigns as pipeline-ingestible narrative text (and an
optional JSON manifest), using only reserved/documentation address space.
It can write the data to a file for `intelgraph pipeline run --file`, or
feed a running IntelGraph server (local or on AWS) directly with `--feed`.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import click
import httpx

from intelgraph.core.simulation import SimulationConfig, generate_simulation


@click.group(name="simulate", help="Generate synthetic adversary-network simulations for testing")
def simulate_group() -> None:
    pass


@simulate_group.command(
    name="network",
    help="Generate a seeded synthetic malicious-network simulation (documentation address space only)",
)
@click.option("--seed", type=int, default=1337, show_default=True, help="Deterministic seed")
@click.option("--campaigns", type=int, default=3, show_default=True, help="Number of campaigns")
@click.option(
    "--indicators",
    "indicators_per_campaign",
    type=int,
    default=8,
    show_default=True,
    help="Approximate indicators per campaign (>= 3)",
)
@click.option(
    "--overlap",
    type=float,
    default=0.35,
    show_default=True,
    help="Probability (0-1) a campaign reuses shared C2 infrastructure (creates graph pivots)",
)
@click.option("--ipv6/--no-ipv6", default=False, show_default=True, help="Also emit RFC 3849 IPv6 C2 addresses")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json", "both"]),
    default="text",
    show_default=True,
    help="Output format",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write to this path (stem reused for .txt/.json when --format both). Prints to stdout if omitted.",
)
@click.option(
    "--feed",
    is_flag=True,
    default=False,
    help="Run the generated data through the pipeline and POST it to a running server's dashboard",
)
@click.option(
    "--base-url",
    default="http://localhost:8000",
    show_default=True,
    help="Base URL of a running IntelGraph API server (used with --feed)",
)
@click.pass_context
def simulate_network(
    ctx: click.Context,
    seed: int,
    campaigns: int,
    indicators_per_campaign: int,
    overlap: float,
    ipv6: bool,
    fmt: str,
    output: str | None,
    feed: bool,
    base_url: str,
) -> None:
    try:
        config = SimulationConfig(
            seed=seed,
            campaigns=campaigns,
            indicators_per_campaign=indicators_per_campaign,
            overlap=overlap,
            ipv6=ipv6,
        )
    except ValueError as e:
        raise click.UsageError(str(e)) from e

    sim = generate_simulation(config)
    text = sim.render_text()
    manifest = sim.to_manifest()

    if output:
        out = Path(output)
        if fmt in ("text", "both"):
            text_path = out if fmt == "text" else out.with_suffix(".txt")
            text_path.write_text(text)
            click.echo(f"Wrote {sim.indicator_count} indicators to {text_path}")
        if fmt in ("json", "both"):
            json_path = out if fmt == "json" else out.with_suffix(".json")
            json_path.write_text(json.dumps(manifest, indent=2))
            click.echo(f"Wrote manifest to {json_path}")
    else:
        click.echo(text if fmt != "json" else json.dumps(manifest, indent=2))

    click.echo(
        f"# {config.campaigns} campaigns, {sim.indicator_count} indicators, "
        f"{len(sim.shared_indicators)} shared (seed={config.seed})",
        err=True,
    )

    if feed:
        _feed_dashboard(sim, text, base_url)


def _feed_dashboard(sim: Any, text: str, base_url: str) -> None:
    """Run the rendered simulation through the pipeline and POST to the dashboard.

    Mirrors `intelgraph pipeline run` so a simulation can populate a running
    server (local or on AWS) in one step.
    """
    from intelgraph.core.pipeline.chain import Pipeline

    source = {
        "id": f"simulation_seed_{sim.config.seed}",
        "name": f"Synthetic network simulation (seed {sim.config.seed})",
        "text": text,
        "value": 50,
    }

    click.echo("Running pipeline over simulation...", err=True)
    pipeline = Pipeline()
    try:
        result = pipeline.run(sources=[source])
    finally:
        pipeline.cleanup()

    ner_labels = Counter(e.label for e in result.extracted_entities)
    ner_samples: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    for e in result.extracted_entities:
        bucket = ner_samples.setdefault(e.label, [])
        seen_set = seen.setdefault(e.label, set())
        if e.text not in seen_set and len(bucket) < 10:
            seen_set.add(e.text)
            bucket.append(e.text)

    result_dict = result.to_dict()
    result_dict["source_texts"] = result.source_texts
    payload = {
        "result": result_dict,
        "sources": {"Simulation": {"iocs": sim.indicator_count, "campaigns": sim.config.campaigns}},
        "ner_counts": dict(ner_labels),
        "ner_samples": ner_samples,
    }

    click.echo(f"Feeding dashboard at {base_url}/dashboard/feed ...", err=True)
    try:
        resp = httpx.post(f"{base_url}/dashboard/feed", json=payload, timeout=30.0)
        resp.raise_for_status()
    except httpx.ConnectError as e:
        raise click.ClickException(
            f"Could not reach {base_url} ({e}).\n"
            "Is the IntelGraph server running and reachable? For a local server:\n"
            "  uv run uvicorn intelgraph.api.main:app --reload\n"
            "For a server on AWS, pass its public/ingress URL via --base-url."
        ) from e
    except httpx.HTTPStatusError as e:
        raise click.ClickException(
            f"Dashboard feed request failed: {e.response.status_code} {e.response.text}"
        ) from e
    click.echo(f"Done. Open {base_url}/ to view the graph.", err=True)
