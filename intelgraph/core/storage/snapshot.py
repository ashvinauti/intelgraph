from typing import Any

import ulid


class SnapshotManager:
    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def create(
        self,
        label: str,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        snapshot_id = str(ulid.new())
        data = {
            "entities": entities,
            "relationships": relationships,
        }
        self._backend.create_snapshot(
            snapshot_id=snapshot_id,
            label=label,
            data=data,
            entity_count=len(entities),
            relationship_count=len(relationships),
            metadata=metadata,
        )
        return snapshot_id

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        return self._backend.get_snapshot(snapshot_id)

    def list(self) -> list[dict[str, Any]]:
        return self._backend.list_snapshots()

    def restore(self, snapshot_id: str) -> dict[str, Any] | None:
        snapshot = self._backend.get_snapshot(snapshot_id)
        if snapshot is None:
            return None
        import json

        data = json.loads(snapshot["data"])
        return data
