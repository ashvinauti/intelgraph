from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceEntry:
    trace_id: str
    query: str
    reasoning_path: list[dict[str, Any]]
    confidence_per_step: list[float]
    uncertainty_markers: list[str]
    alternative_paths: list[list[dict[str, Any]]]
    evidence_chain: list[str]
    score: float
    created_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "reasoning_path": self.reasoning_path,
            "confidence_per_step": [round(c, 4) for c in self.confidence_per_step],
            "uncertainty_markers": self.uncertainty_markers,
            "alternative_count": len(self.alternative_paths),
            "evidence_chain": self.evidence_chain,
            "score": round(self.score, 4),
            "created_at": self.created_at,
        }


class TraceSystem:
    def __init__(self) -> None:
        self._traces: list[TraceEntry] = []
        self._max_traces = 10000

    def record(
        self,
        query: str,
        path: list[dict[str, Any]],
        alt_paths: list[list[dict[str, Any]]],
        evidence: list[str],
        score: float,
    ) -> TraceEntry:
        entry = TraceEntry(
            trace_id=f"tr_{uuid.uuid4().hex[:12]}",
            query=query,
            reasoning_path=path,
            confidence_per_step=[s.get("confidence", 0.5) for s in path],
            uncertainty_markers=[
                f"uncertainty_{s.get('step_type', 'unknown')}"
                for s in path
                if s.get("uncertainty", 0) > 0.3
            ],
            alternative_paths=alt_paths,
            evidence_chain=evidence,
            score=score,
            created_at=time.time(),
        )
        self._traces.append(entry)
        if len(self._traces) > self._max_traces:
            self._traces = self._traces[-self._max_traces :]
        return entry

    def get(self, trace_id: str) -> TraceEntry | None:
        for t in self._traces:
            if t.trace_id == trace_id:
                return t
        return None

    def list(self, limit: int = 50) -> list[TraceEntry]:
        return self._traces[-limit:]

    def query_traces(self, query_filter: str = "", limit: int = 50) -> list[TraceEntry]:
        if not query_filter:
            return self.list(limit)
        return [t for t in self._traces if query_filter.lower() in t.query.lower()][-limit:]
