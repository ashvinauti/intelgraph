from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import ulid


@dataclass
class AuditEntry:
    entity_id: str | None
    entity_type: str | None
    operation: str
    old_data: dict[str, Any] | None = None
    new_data: dict[str, Any] | None = None
    actor: str | None = None
    correlation_id: str | None = None


class AuditLogger:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def log(
        self,
        entry: AuditEntry,
    ) -> dict[str, Any]:
        record = {
            "id": str(ulid.new()),
            "entity_id": entry.entity_id,
            "entity_type": entry.entity_type,
            "operation": entry.operation,
            "old_data": _serialize_json(entry.old_data),
            "new_data": _serialize_json(entry.new_data),
            "actor": entry.actor,
            "correlation_id": entry.correlation_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._backend.write_audit(record)
        return record

    def query(self, entity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self._backend.query_audit(entity_id=entity_id, limit=limit)


def _serialize_json(obj: object) -> str | None:
    if obj is None:
        return None
    import json

    return json.dumps(obj, default=str)
