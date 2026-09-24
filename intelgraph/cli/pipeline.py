"""CLI command that runs the collection/NLP/graph pipeline against live
threat feeds and feeds the result into a running IntelGraph server's
dashboard (`POST /dashboard/feed`).

This replaces the old scripts/phase7_dashboard_run.py-style dev scripts:
it fetches URLhaus live over HTTP (no API key required) and optionally
OTX pulses (if OTX_API_KEY is set), instead of depending on a
pre-downloaded local CSV file or a hardcoded API key.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import click
import httpx

from intelgraph.core.pipeline.chain import Pipeline

URLHAUS_CSV_URL = "https://urlhaus.abuse.ch/downloads/csv_recent/"


@click.group(name="pipeline", help="Run the collection/NLP/graph pipeline against live feeds")
def pipeline_group() -> None:
    pass


def _parse_urlhaus_csv(text: str, limit: int) -> tuple[dict[str, Any], int]:
    """Parse URLhaus 'recent' CSV text (the id,dateadded,url,... format) into a
    pipeline source dict, pulling just the URL column."""
    reader = csv.reader(text.splitlines())
    rows = [row for row in reader if row and not row[0].startswith("#")]
    urls = [row[2] for row in rows[:limit] if len(row) > 2]
    joined = "\n".join(urls)
    source = {"id": "urlhaus_recent", "name": f"URLhaus (recent {len(urls)})", "text": joined, "value": 60}
    return source, len(urls)


def _fetch_urlhaus_source(limit: int) -> tuple[dict[str, Any], int]:
    """Fetch the URLhaus 'recent' CSV feed live and build a pipeline source dict."""
    resp = httpx.get(URLHAUS_CSV_URL, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()
    return _parse_urlhaus_csv(resp.text, limit)


def _load_urlhaus_csv_file(path: str, limit: int) -> tuple[dict[str, Any], int]:
    """Parse a manually downloaded URLhaus CSV file (same format as the live feed)."""
    return _parse_urlhaus_csv(Path(path).read_text(), limit)


def _load_file_sources(paths: tuple[str, ...]) -> list[dict[str, Any]]:
    """Build pipeline source dicts from local text files (e.g. synthetic/sample IOC data)."""
    sources = []
    for path in paths:
        text = Path(path).read_text()
        sources.append(
            {"id": f"file_{Path(path).stem}", "name": f"File: {Path(path).name}", "text": text, "value": 50}
        )
    return sources


def _fetch_otx_sources(pulse_limit: int) -> tuple[list[dict[str, Any]], int]:
    """Fetch recent OTX pulses if OTX_API_KEY is set. Returns ([], 0) otherwise."""
    api_key = os.environ.get("OTX_API_KEY", "")
    if not api_key:
        return [], 0

    from intelgraph.core.source.otx import OtxClient

    client = OtxClient(api_key=api_key)
    pulses = client.get_pulses(page=1, limit=pulse_limit)
    total_iocs = sum(len(v) for v in client.extract_iocs(pulses).values())
    return [p.to_source_dict() for p in pulses], total_iocs


@pipeline_group.command(name="run", help="Fetch live threat feeds, run the pipeline, and feed a running server's dashboard")
@click.option(
    "--base-url",
    default="http://localhost:8000",
    show_default=True,
    help="Base URL of a running IntelGraph API server",
)
@click.option(
    "--urlhaus-limit",
    default=50,
    show_default=True,
    type=int,
    help="Number of recent URLhaus entries to pull (no API key required)",
)
@click.option(
    "--otx-pulses",
    default=5,
    show_default=True,
    type=int,
    help="Number of OTX pulses to pull (requires OTX_API_KEY env var; skipped if unset)",
)
@click.option(
    "--no-feed",
    is_flag=True,
    default=False,
    help="Run the pipeline and print a summary without POSTing to the dashboard",
)
@click.option(
    "--skip-urlhaus",
    is_flag=True,
    default=False,
    help="Don't use URLhaus at all (useful offline, or when only using --file)",
)
@click.option(
    "--urlhaus-csv",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a manually downloaded URLhaus CSV (same format as "
    "https://urlhaus.abuse.ch/downloads/csv_recent/) to use instead of fetching live. "
    "Conflicts with --skip-urlhaus.",
)
@click.option(
    "--file",
    "files",
    type=click.Path(exists=True, dir_okay=False),
    multiple=True,
    help="Local text file of sample/synthetic IOC data to include as a source "
    "(repeatable). See samples/synthetic_iocs.txt for the expected format.",
)
@click.pass_context
def pipeline_run(
    ctx: click.Context,
    base_url: str,
    urlhaus_limit: int,
    otx_pulses: int,
    no_feed: bool,
    skip_urlhaus: bool,
    urlhaus_csv: str | None,
    files: tuple[str, ...],
) -> None:
    if skip_urlhaus and urlhaus_csv:
        raise click.UsageError("--skip-urlhaus and --urlhaus-csv conflict; pass only one.")

    urlhaus_source = None
    urlhaus_count = 0
    if skip_urlhaus:
        click.echo("Skipping URLhaus (--skip-urlhaus)")
    elif urlhaus_csv:
        click.echo(f"Loading URLhaus CSV from {urlhaus_csv}...")
        urlhaus_source, urlhaus_count = _load_urlhaus_csv_file(urlhaus_csv, urlhaus_limit)
        click.echo(f"  {urlhaus_count} entries")
    else:
        click.echo("Fetching URLhaus (recent)...")
        urlhaus_source, urlhaus_count = _fetch_urlhaus_source(urlhaus_limit)
        click.echo(f"  {urlhaus_count} entries")

    click.echo("Fetching OTX pulses...")
    otx_sources, otx_ioc_count = _fetch_otx_sources(otx_pulses)
    if otx_sources:
        click.echo(f"  {len(otx_sources)} pulses, {otx_ioc_count} IOCs")
    else:
        click.echo("  skipped (OTX_API_KEY not set)")

    file_sources = _load_file_sources(files)
    if file_sources:
        click.echo(f"Loaded {len(file_sources)} local file source(s): {', '.join(files)}")

    sources = [s for s in (urlhaus_source,) if s] + otx_sources + file_sources
    if not sources:
        raise click.UsageError(
            "No sources to run. Pass --file, unset --skip-urlhaus, or set OTX_API_KEY."
        )

    click.echo("Running pipeline...")
    pipeline = Pipeline()
    try:
        result = pipeline.run(sources=sources)
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

    summary = {
        "sources": len(sources),
        "entities": len(result.extracted_entities),
        "graph_nodes": len(result.graph.nodes) if result.graph else 0,
        "alerts": len(result.alerts),
        "incidents": len(result.incidents),
        "errors": result.errors,
        "ner_counts": dict(ner_labels),
    }
    click.echo(json.dumps(summary, indent=2))

    if no_feed:
        return

    result_dict = result.to_dict()
    result_dict["source_texts"] = result.source_texts

    source_summary: dict[str, Any] = {
        "OTX": {"iocs": otx_ioc_count, "pulses": len(otx_sources)},
    }
    if urlhaus_source:
        source_summary["URLhaus"] = {"iocs": urlhaus_count, "entities": len(result.extracted_entities)}
    if file_sources:
        source_summary["Files"] = {"count": len(file_sources), "paths": list(files)}

    payload = {
        "result": result_dict,
        "sources": source_summary,
        "ner_counts": dict(ner_labels),
        "ner_samples": ner_samples,
    }
    click.echo(f"Feeding dashboard at {base_url}/dashboard/feed ...")
    try:
        resp = httpx.post(f"{base_url}/dashboard/feed", json=payload, timeout=30.0)
        resp.raise_for_status()
    except httpx.ConnectError as e:
        raise click.ClickException(
            f"Could not reach {base_url} ({e}).\n"
            "Is the IntelGraph server running? Start it in another terminal first:\n"
            "  uv run uvicorn intelgraph.api.main:app --reload\n"
            "Then re-run this command (or pass --no-feed to skip feeding the dashboard)."
        ) from e
    except httpx.HTTPStatusError as e:
        raise click.ClickException(
            f"Dashboard feed request failed: {e.response.status_code} {e.response.text}"
        ) from e
    click.echo(f"Done. Open {base_url}/ to view the dashboard.")
