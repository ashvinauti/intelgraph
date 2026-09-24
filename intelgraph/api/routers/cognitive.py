from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from intelgraph.api.auth_middleware import require_permission
from intelgraph.core.cognitive import (
    ContinuousOptimizer,
    ContradictionDetector,
    HypothesisGenerator,
    ReasoningEngine,
    SelfLearningLoop,
    TraceSystem,
)
from intelgraph.core.enterprise import get_metrics as _get_metrics

router = APIRouter(prefix="/reasoning", tags=["cognitive"])


def get_reasoning_engine() -> ReasoningEngine:
    return ReasoningEngine()


def get_contradiction_detector() -> ContradictionDetector:
    return ContradictionDetector()


def get_hypothesis_generator() -> HypothesisGenerator:
    return HypothesisGenerator()


def get_learning_loop() -> SelfLearningLoop:
    return SelfLearningLoop()


def get_trace_system() -> TraceSystem:
    return TraceSystem()


def get_optimizer() -> ContinuousOptimizer:
    return ContinuousOptimizer()


@router.post("/query", summary="Multi-hop reasoning query over knowledge graph")
async def reasoning_query(
    body: dict[str, Any],
    engine: ReasoningEngine = Depends(get_reasoning_engine),
    trace: TraceSystem = Depends(get_trace_system),
    _=require_permission("cognitive:read"),
):
    start = body.get("start", "")
    end = body.get("end", "")
    query_type = body.get("type", "multi_hop")
    if not start or not end:
        raise HTTPException(status_code=422, detail="start and end are required")
    start_t = time.perf_counter()
    if query_type == "causal":
        paths = engine.causal_inference(start)
    else:
        paths = engine.multi_hop_reason(start, end)
    elapsed = (time.perf_counter() - start_t) * 1000
    path_dicts = [p.to_dict() for p in paths]
    alt_dicts = [p.to_dict() for p in paths[:3]]
    t = trace.record(
        f"{start} -> {end}",
        path_dicts,
        [alt_dicts] if alt_dicts else [],
        [p["evidence_chain"][0] if p["evidence_chain"] else "" for p in path_dicts],
        paths[0].score if paths else 0.0,
    )
    _get_metrics().set_gauge("reasoning_latency_ms", elapsed)
    _get_metrics().set_gauge("inference_depth", len(paths))
    return {"paths": path_dicts, "count": len(paths), "trace_id": t.trace_id}


@router.post("/explain", summary="Explain a reasoning path with step-by-step details")
async def reasoning_explain(
    body: dict[str, Any],
    engine: ReasoningEngine = Depends(get_reasoning_engine),
    trace: TraceSystem = Depends(get_trace_system),
    _=require_permission("cognitive:read"),
):
    trace_id = body.get("trace_id", "")
    if not trace_id:
        raise HTTPException(status_code=422, detail="trace_id is required")
    t = trace.get(trace_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return t.to_dict()


@router.post("/hypothesis/generate", summary="Generate hypotheses from graph patterns")
async def hypothesis_generate(
    body: dict[str, Any],
    generator: HypothesisGenerator = Depends(get_hypothesis_generator),
    _=require_permission("cognitive:read"),
):
    graph = body.get("graph")
    hypotheses = generator.generate(graph)
    _get_metrics().set_gauge("hypothesis_count", len(hypotheses))
    return {"hypotheses": [h.to_dict() for h in hypotheses], "count": len(hypotheses)}


@router.post("/learning/feedback", summary="Ingest analyst feedback for self-learning")
async def learning_feedback(
    body: dict[str, Any],
    loop: SelfLearningLoop = Depends(get_learning_loop),
    _=require_permission("cognitive:write"),
):
    query_id = body.get("query_id", "")
    analyst_id = body.get("analyst_id", "")
    feedback_type = body.get("feedback_type", "correction")
    score = float(body.get("score", 0.5))
    correction = body.get("correction", {})
    original = body.get("original_output", {})
    if not query_id or not analyst_id:
        raise HTTPException(status_code=422, detail="query_id and analyst_id are required")
    entry = loop.ingest_feedback(query_id, analyst_id, feedback_type, score, correction, original)
    _get_metrics().set_gauge("learning_improvement_rate", loop.improvement_rate())
    return entry.to_dict()


@router.get("/reasoning/trace/{trace_id}", summary="Get reasoning trace by ID")
async def get_trace(
    trace_id: str,
    trace: TraceSystem = Depends(get_trace_system),
    _=require_permission("cognitive:read"),
):
    t = trace.get(trace_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    return t.to_dict()


@router.post("/validate", summary="Validate a hypothesis with new confidence")
async def validate_hypothesis(
    body: dict[str, Any],
    generator: HypothesisGenerator = Depends(get_hypothesis_generator),
    _=require_permission("cognitive:write"),
):
    hypothesis_id = body.get("hypothesis_id", "")
    confidence = float(body.get("confidence", 0.5))
    if not hypothesis_id:
        raise HTTPException(status_code=422, detail="hypothesis_id is required")
    success = generator.validate(hypothesis_id, confidence)
    if not success:
        raise HTTPException(status_code=404, detail=f"Hypothesis {hypothesis_id} not found")
    _get_metrics().set_gauge("hypothesis_confidence", confidence)
    return {"hypothesis_id": hypothesis_id, "new_confidence": confidence, "status": "validated"}


@router.post("/contradictions/detect", summary="Detect contradictions between facts")
async def detect_contradictions(
    body: dict[str, Any],
    detector: ContradictionDetector = Depends(get_contradiction_detector),
    _=require_permission("cognitive:read"),
):
    facts = body.get("facts", [])
    contradictions = detector.detect(facts)
    _get_metrics().set_gauge(
        "contradiction_detection_rate", len(contradictions) / max(len(facts), 1)
    )
    return {"contradictions": [c.to_dict() for c in contradictions], "count": len(contradictions)}
