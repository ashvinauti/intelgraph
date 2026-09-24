from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from intelgraph.api.auth_middleware import require_permission
from intelgraph.core.enterprise import get_metrics as _get_metrics
from intelgraph.core.nlp import (
    DocumentSummarizer,
    EconomicGovernor,
    EntityLinker,
    EventExtractor,
    InputSanitizer,
    NEREngine,
    NLPModelRegistry,
    OutputSanitizer,
    RelationshipExtractor,
    TextClassifier,
)

router = APIRouter(prefix="/nlp", tags=["NLP"])


def get_ner() -> NEREngine:
    return NEREngine()


def get_rel_extractor() -> RelationshipExtractor:
    return RelationshipExtractor()


def get_event_extractor() -> EventExtractor:
    return EventExtractor()


def get_classifier() -> TextClassifier:
    return TextClassifier()


def get_summarizer() -> DocumentSummarizer:
    return DocumentSummarizer()


def get_linker() -> EntityLinker:
    return EntityLinker()


def get_model_registry() -> NLPModelRegistry:
    return NLPModelRegistry()


def get_economic_governor() -> EconomicGovernor:
    return EconomicGovernor()


@router.post("/extract-entities", summary="Extract named entities from text")
async def extract_entities(
    request: Request,
    body: dict[str, Any],
    ner: NEREngine = Depends(get_ner),
    _=require_permission("nlp:read"),
):
    text = InputSanitizer.sanitize_text(body.get("text", ""))
    if not InputSanitizer.validate_text(text):
        raise HTTPException(status_code=422, detail="Invalid or empty text")
    entities = ner.extract(text)
    safe = OutputSanitizer.sanitize_entity_output([e.to_dict() for e in entities])
    _get_metrics().set_gauge("entities_extracted_count", len(safe))
    return {"entities": safe, "count": len(safe)}


@router.post("/extract-relationships", summary="Extract relationships from text")
async def extract_relationships(
    request: Request,
    body: dict[str, Any],
    ner: NEREngine = Depends(get_ner),
    rel_extractor: RelationshipExtractor = Depends(get_rel_extractor),
    _=require_permission("nlp:read"),
):
    text = InputSanitizer.sanitize_text(body.get("text", ""))
    if not InputSanitizer.validate_text(text):
        raise HTTPException(status_code=422, detail="Invalid or empty text")
    entities = ner.extract(text)
    relationships = rel_extractor.extract(text, entities)
    results = [r.to_dict() for r in relationships]
    _get_metrics().set_gauge("relationships_extracted_count", len(results))
    return {"relationships": results, "count": len(results)}


@router.post("/extract-events", summary="Extract events from text")
async def extract_events(
    request: Request,
    body: dict[str, Any],
    ner: NEREngine = Depends(get_ner),
    event_extractor: EventExtractor = Depends(get_event_extractor),
    _=require_permission("nlp:read"),
):
    text = InputSanitizer.sanitize_text(body.get("text", ""))
    if not InputSanitizer.validate_text(text):
        raise HTTPException(status_code=422, detail="Invalid or empty text")
    entities = ner.extract(text)
    events = event_extractor.extract(text, entities)
    results = [e.to_dict() for e in events]
    _get_metrics().set_gauge("events_extracted_count", len(results))
    return {"events": results, "count": len(results)}


@router.post("/classify-text", summary="Classify text threat type and severity")
async def classify_text(
    request: Request,
    body: dict[str, Any],
    classifier: TextClassifier = Depends(get_classifier),
    _=require_permission("nlp:read"),
):
    text = InputSanitizer.sanitize_text(body.get("text", ""))
    if not InputSanitizer.validate_text(text):
        raise HTTPException(status_code=422, detail="Invalid or empty text")
    result = classifier.classify(text)
    return result.to_dict()


@router.post("/summarize-document", summary="Summarize a document for threat intelligence")
async def summarize_document(
    request: Request,
    body: dict[str, Any],
    summarizer: DocumentSummarizer = Depends(get_summarizer),
    _=require_permission("nlp:read"),
):
    text = InputSanitizer.sanitize_text(body.get("text", ""))
    if not InputSanitizer.validate_text(text):
        raise HTTPException(status_code=422, detail="Invalid or empty text")
    max_sentences = body.get("max_sentences", 5)
    result = summarizer.summarize(text, max_sentences)
    return result


@router.post("/link-to-graph", summary="Link extracted entities to graph nodes")
async def link_to_graph(
    request: Request,
    body: dict[str, Any],
    ner: NEREngine = Depends(get_ner),
    linker: EntityLinker = Depends(get_linker),
    _=require_permission("nlp:write"),
):
    text = InputSanitizer.sanitize_text(body.get("text", ""))
    if not InputSanitizer.validate_text(text):
        raise HTTPException(status_code=422, detail="Invalid or empty text")
    entities = ner.extract(text)
    entity_dicts = [e.to_dict() for e in entities]
    result = linker.link(text, entity_dicts)
    _get_metrics().set_gauge("link_accuracy", result["link_accuracy"])
    return result


@router.post("/ingest-text", summary="Batch ingest text with full auto-extraction")
async def ingest_text(
    request: Request,
    body: dict[str, Any],
    ner: NEREngine = Depends(get_ner),
    rel_extractor: RelationshipExtractor = Depends(get_rel_extractor),
    event_extractor: EventExtractor = Depends(get_event_extractor),
    classifier: TextClassifier = Depends(get_classifier),
    summarizer: DocumentSummarizer = Depends(get_summarizer),
    linker: EntityLinker = Depends(get_linker),
    _=require_permission("nlp:write"),
):
    text = InputSanitizer.sanitize_text(body.get("text", ""))
    if not InputSanitizer.validate_text(text):
        raise HTTPException(status_code=422, detail="Invalid or empty text")
    entities = ner.extract(text)
    entity_dicts = [e.to_dict() for e in entities]
    relationships = rel_extractor.extract(text, entities)
    events = event_extractor.extract(text, entities)
    classification = classifier.classify(text)
    summary = summarizer.summarize(text)
    link_result = linker.link(text, entity_dicts)
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
    metrics = _get_metrics()
    metrics.set_gauge("entities_extracted_count", len(entity_dicts))
    metrics.set_gauge("relationships_extracted_count", len(relationships))
    metrics.set_gauge("events_extracted_count", len(events))
    return result


@router.get("/models", summary="List available NLP models")
async def list_models(
    registry: NLPModelRegistry = Depends(get_model_registry),
    _=require_permission("nlp:read"),
):
    models = registry.list()
    return {"models": [m.to_dict() for m in models], "count": len(models)}


@router.post(
    "/models/{model_id}/deploy",
    status_code=status.HTTP_200_OK,
    summary="Deploy or hot-swap an NLP model",
)
async def deploy_model(
    model_id: str,
    registry: NLPModelRegistry = Depends(get_model_registry),
    _=require_permission("nlp:admin"),
):
    success = registry.deploy(model_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return {"model_id": model_id, "status": "deployed"}


@router.post("/analyze-roi", summary="Compute ROI for an NLP analysis query")
async def analyze_roi(
    body: dict[str, Any],
    governor: EconomicGovernor = Depends(get_economic_governor),
    _=require_permission("nlp:read"),
):
    query_id = body.get("query_id", "unknown")
    value = float(body.get("estimated_value", 0))
    cost = float(body.get("estimated_cost", 0))
    roi = governor.compute_roi(query_id, value, cost)
    return roi.to_dict()


@router.get("/budget-status", summary="Get NLP budget consumption status")
async def budget_status(
    governor: EconomicGovernor = Depends(get_economic_governor),
    _=require_permission("nlp:read"),
):
    return governor.get_budget_status()
