import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any


class IncrementalTracker:
    def __init__(self, storage_backend: Any, default_ttl_days: int = 7) -> None:
        self._storage = storage_backend
        self._default_ttl = timedelta(days=default_ttl_days)

    def should_collect(
        self,
        source_key: str,
        target: str,
        ttl_days: int | None = None,
    ) -> bool:
        cache_key = self._cache_key(source_key, target)
        cached = self._get_tracker(cache_key)
        if cached is None:
            return True

        ttl = timedelta(days=ttl_days) if ttl_days else self._default_ttl
        last = datetime.fromisoformat(cached.get("collected_at", ""))
        staleness = datetime.now(UTC) - last
        return staleness > ttl

    def mark_collected(
        self,
        source_key: str,
        target: str,
        content_hash: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        cache_key = self._cache_key(source_key, target)
        entry = {
            "source_key": source_key,
            "target": target,
            "collected_at": datetime.now(UTC).isoformat(),
            "content_hash": content_hash,
            "metadata": metadata or {},
        }
        self._storage.cache_set(cache_key, _serialize(entry), None)

    def has_changed(self, source_key: str, target: str, content: str) -> bool:
        cache_key = self._cache_key(source_key, target)
        cached = self._get_tracker(cache_key)
        if cached is None:
            return True
        old_hash = cached.get("content_hash", "")
        new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return old_hash != new_hash

    def _cache_key(self, source_key: str, target: str) -> str:
        key = f"incr:{source_key}:{target}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]

    def _get_tracker(self, cache_key: str) -> dict[str, Any] | None:
        cached = self._storage.cache_get(cache_key)
        if cached is None:
            return None
        return _deserialize(cached.get("value", "{}"))


def _serialize(obj: dict[str, Any]) -> str:
    import json

    return json.dumps(obj, default=str)


def _deserialize(s: str) -> dict[str, Any]:
    import json

    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return {}
