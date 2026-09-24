from datetime import UTC, datetime
from typing import Any

import ulid


class SourceRegistry:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def register(
        self,
        source_name: str,
        source_url: str,
        source_tier: int,
        trust_score: int,
        reliability_score: int,
        classification: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        source_id = str(ulid.new())
        entry = {
            "id": source_id,
            "source_name": source_name,
            "source_url": source_url,
            "source_tier": source_tier,
            "trust_score": trust_score,
            "reliability_score": reliability_score,
            "last_validated": datetime.now(UTC).isoformat(),
            "classification": classification or "",
            "metadata": _serialize(metadata or {}),
        }
        self._backend.register_source(entry)
        return source_id

    def get(self, source_id: str) -> dict[str, Any] | None:
        return self._backend.get_source(source_id)

    def list(self) -> list[dict[str, Any]]:
        return self._backend.list_sources()


def _serialize(obj: object) -> str:
    import json

    return json.dumps(obj, default=str)
