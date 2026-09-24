from __future__ import annotations

import json
import sys
from typing import Any

import click

from intelgraph.core.nlp import (
    DocumentSummarizer,
    EntityLinker,
    EventExtractor,
    NEREngine,
    NLPModelRegistry,
    RelationshipExtractor,
    TextClassifier,
)
from intelgraph.core.nlp.models import ModelTask


@click.group(name="nlp")
def nlp_group() -> None:
    """Natural Language Processing for intelligence extraction."""


@nlp_group.command("extract-entities")
@click.argument("text", required=False, default="")
@click.option("--file", "-f", type=str, help="Read text from file")
def extract_entities(text: str, file: str | None) -> None:
    """Extract named entities from text."""
    content = _read_input(text, file)
    ner = NEREngine()
    entities = ner.extract(content)
    _print_json([e.to_dict() for e in entities])


@nlp_group.command("extract-relationships")
@click.argument("text", required=False, default="")
@click.option("--file", "-f", type=str, help="Read text from file")
def extract_relationships(text: str, file: str | None) -> None:
    """Extract relationships from text."""
    content = _read_input(text, file)
    ner = NEREngine()
    rel_extractor = RelationshipExtractor()
    entities = ner.extract(content)
    relationships = rel_extractor.extract(content, entities)
    _print_json([r.to_dict() for r in relationships])


@nlp_group.command("extract-events")
@click.argument("text", required=False, default="")
@click.option("--file", "-f", type=str, help="Read text from file")
def extract_events(text: str, file: str | None) -> None:
    """Extract events from text."""
    content = _read_input(text, file)
    ner = NEREngine()
    event_extractor = EventExtractor()
    entities = ner.extract(content)
    events = event_extractor.extract(content, entities)
    _print_json([e.to_dict() for e in events])


@nlp_group.command("classify-text")
@click.argument("text", required=False, default="")
@click.option("--file", "-f", type=str, help="Read text from file")
def classify_text(text: str, file: str | None) -> None:
    """Classify text threat type and severity."""
    content = _read_input(text, file)
    classifier = TextClassifier()
    result = classifier.classify(content)
    _print_json(result.to_dict())


@nlp_group.command("summarize")
@click.argument("file_path", type=str)
def summarize(file_path: str) -> None:
    """Summarize a document file."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except FileNotFoundError:
        click.echo(f"File not found: {file_path}", err=True)
        sys.exit(1)
    summarizer = DocumentSummarizer()
    result = summarizer.summarize(content)
    _print_json(result)


@nlp_group.command("link-to-graph")
@click.argument("text", required=False, default="")
@click.option("--file", "-f", type=str, help="Read text from file")
def link_to_graph(text: str, file: str | None) -> None:
    """Link extracted entities to graph nodes."""
    content = _read_input(text, file)
    ner = NEREngine()
    linker = EntityLinker()
    entities = ner.extract(content)
    entity_dicts = [e.to_dict() for e in entities]
    result = linker.link(content, entity_dicts)
    _print_json(result)


@nlp_group.command("ingest-file")
@click.argument("path", type=str)
def ingest_file(path: str) -> None:
    """Ingest a file with full auto-extraction (entities, relationships, events, classification)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except FileNotFoundError:
        click.echo(f"File not found: {path}", err=True)
        sys.exit(1)
    ner = NEREngine()
    rel_extractor = RelationshipExtractor()
    event_extractor = EventExtractor()
    classifier = TextClassifier()
    summarizer = DocumentSummarizer()
    linker = EntityLinker()
    entities = ner.extract(content)
    entity_dicts = [e.to_dict() for e in entities]
    relationships = rel_extractor.extract(content, entities)
    events = event_extractor.extract(content, entities)
    classification = classifier.classify(content)
    summary = summarizer.summarize(content)
    link_result = linker.link(content, entity_dicts)
    result = {
        "entities": entity_dicts,
        "entity_count": len(entity_dicts),
        "relationships": [r.to_dict() for r in relationships],
        "relationship_count": len(relationships),
        "events": [e.to_dict() for e in events],
        "event_count": len(events),
        "classification": classification.to_dict(),
        "summary": summary,
        "graph_links": link_result,
    }
    _print_json(result)


@nlp_group.group("models")
def models_group() -> None:
    """Manage NLP models."""


@models_group.command("list")
def list_models() -> None:
    """List registered NLP models."""
    registry = NLPModelRegistry()
    models = registry.list()
    _print_json([m.to_dict() for m in models])


@models_group.command("register")
@click.option("--name", required=True, help="Model name")
@click.option("--version", required=True, help="Model version")
@click.option(
    "--task",
    required=True,
    type=click.Choice(["ner", "relationship", "event", "classification", "summarization"]),
    help="Model task",
)
def register_model(name: str, version: str, task: str) -> None:
    """Register a new NLP model."""
    task_map = {
        "ner": ModelTask.NER,
        "relationship": ModelTask.RELATIONSHIP,
        "event": ModelTask.EVENT,
        "classification": ModelTask.CLASSIFICATION,
        "summarization": ModelTask.SUMMARIZATION,
    }
    registry = NLPModelRegistry()
    record = registry.register(name, version, task_map[task])
    _print_json(record.to_dict())


@models_group.command("deploy")
@click.argument("model-id", type=str)
def deploy_model(model_id: str) -> None:
    """Deploy (hot-swap) a model."""
    registry = NLPModelRegistry()
    success = registry.deploy(model_id)
    if success:
        click.echo(f"Model {model_id} deployed successfully")
    else:
        click.echo(f"Model {model_id} not found", err=True)
        sys.exit(1)


def _read_input(text: str, file: str | None) -> str:
    if file:
        try:
            with open(file, encoding="utf-8", errors="replace") as f:
                return f.read()
        except FileNotFoundError:
            click.echo(f"File not found: {file}", err=True)
            sys.exit(1)
    if text:
        return text
    return sys.stdin.read()


def _print_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, default=str))
