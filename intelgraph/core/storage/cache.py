import json
import threading
from datetime import UTC, datetime
from typing import Any


class CacheManager:
    def __init__(self, backend: Any, default_ttl: int = 300) -> None:
        self._backend = backend
        self._default_ttl = default_ttl
        self._memory: dict[str, tuple[object, float | None]] = {}
        self._lock = threading.Lock()
        self._hit_count = 0
        self._miss_count = 0

    def get(self, key: str) -> object | None:
        cached = self._memory_get(key)
        if cached is not None:
            self._hit_count += 1
            return cached

        row = self._backend.cache_get(key)
        if row is not None:
            value = json.loads(row["value"])
            expires = row.get("expires_at")
            if expires:
                exp_dt = datetime.fromisoformat(expires)
                if exp_dt < datetime.now(UTC):
                    self._miss_count += 1
                    return None
            self._memory_put(key, value, expires, persist=False)
            self._hit_count += 1
            return value

        self._miss_count += 1
        return None

    def set(self, key: str, value: object, ttl: int | None = None, persist: bool = True) -> None:
        expires: str | None = None
        if ttl is None:
            ttl = self._default_ttl
        if ttl > 0:
            exp_dt = datetime.now(UTC).timestamp() + ttl
            expires = datetime.fromtimestamp(exp_dt, tz=UTC).isoformat()

        self._memory_put(key, value, expires)
        if persist:
            self._backend.cache_set(key, json.dumps(value, default=str), expires)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._memory.pop(key, None)
        self._backend.cache_delete(key)

    def invalidate_pattern(self, pattern: str) -> None:
        with self._lock:
            keys = [k for k in self._memory if pattern in k]
            for k in keys:
                self._memory.pop(k, None)
        self._backend.cache_delete_pattern(pattern)

    def clear(self) -> None:
        with self._lock:
            self._memory.clear()
        self._backend.cache_clear()

    @property
    def stats(self) -> dict[str, int]:
        return {
            "hits": self._hit_count,
            "misses": self._miss_count,
            "memory_size": len(self._memory),
        }

    def _memory_get(self, key: str) -> object | None:
        with self._lock:
            entry = self._memory.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at:
                exp_dt = datetime.fromisoformat(expires_at)
                if exp_dt < datetime.now(UTC):
                    self._memory.pop(key, None)
                    return None
            return value

    def _memory_put(
        self, key: str, value: object, expires_at: str | None, persist: bool = True
    ) -> None:
        with self._lock:
            self._memory[key] = (value, expires_at)
