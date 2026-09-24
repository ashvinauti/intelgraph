from __future__ import annotations

import json
import sys
from typing import Any

import click

from intelgraph.core.cognitive import (
    HypothesisGenerator,
    ReasoningEngine,
    SelfLearningLoop,
    TraceSystem,
)


@click.group(name="cognitive")
def cognitive_group() -> None:
    """Cognitive reasoning and self-learning intelligence."""


@cognitive_group.command("query")
@click.argument("start", type=str)
@click.argument("end", type=str)
@click.option(
    "--type", "-t", "query_type", default="multi_hop", help="Query type: multi_hop or causal"
)
def query(start: str, end: str, query_type: str) -> None:
    """Multi-hop reasoning query between two entities."""
    engine = ReasoningEngine()
    if query_type == "causal":
        paths = engine.causal_inference(start)
    else:
        paths = engine.multi_hop_reason(start, end)
    _print_json([p.to_dict() for p in paths])


@cognitive_group.command("explain")
@click.argument("trace_id", type=str)
def explain(trace_id: str) -> None:
    """Explain a reasoning trace."""
    trace = TraceSystem()
    t = trace.get(trace_id)
    if not t:
        click.echo(f"Trace {trace_id} not found", err=True)
        sys.exit(1)
    _print_json(t.to_dict())


@cognitive_group.command("hypothesis")
@click.option("--generate", "do_generate", is_flag=True, help="Generate hypotheses")
def hypothesis(do_generate: bool) -> None:
    """Generate or list hypotheses."""
    generator = HypothesisGenerator()
    if do_generate:
        hypotheses = generator.generate()
        _print_json([h.to_dict() for h in hypotheses])
    else:
        active = generator.get_active()
        _print_json([h.to_dict() for h in active])


@cognitive_group.command("feedback")
@click.option("--query-id", required=True, help="Query ID")
@click.option("--analyst-id", required=True, help="Analyst ID")
@click.option("--score", type=float, default=0.5, help="Feedback score")
@click.option("--type", "fb_type", default="correction", help="Feedback type")
def feedback(query_id: str, analyst_id: str, score: float, fb_type: str) -> None:
    """Submit feedback for self-learning."""
    loop = SelfLearningLoop()
    entry = loop.ingest_feedback(query_id, analyst_id, fb_type, score, {}, {})
    _print_json(entry.to_dict())


@cognitive_group.command("trace")
@click.argument("trace_id", type=str, required=False)
def trace(trace_id: str | None) -> None:
    """Get reasoning trace."""
    trace_sys = TraceSystem()
    if trace_id:
        t = trace_sys.get(trace_id)
        if not t:
            click.echo(f"Trace {trace_id} not found", err=True)
            sys.exit(1)
        _print_json(t.to_dict())
    else:
        traces = trace_sys.list()
        _print_json([t.to_dict() for t in traces])


@cognitive_group.command("validate")
@click.option("--hypothesis-id", required=True, help="Hypothesis ID")
@click.option("--confidence", type=float, default=0.5, help="New confidence score")
def validate(hypothesis_id: str, confidence: float) -> None:
    """Validate a hypothesis."""
    generator = HypothesisGenerator()
    success = generator.validate(hypothesis_id, confidence)
    if success:
        click.echo(f"Hypothesis {hypothesis_id} validated with confidence {confidence}")
    else:
        click.echo(f"Hypothesis {hypothesis_id} not found", err=True)
        sys.exit(1)


def _print_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, default=str))
