import time
from threading import Lock
from typing import Any, Optional

from app.cache.base import Cache


class MemoryCache(Cache):
    """Simple in-process TTL dict cache. Not shared across workers/processes —
    fine for single-user MVP. Swap for RedisCache (same interface) once you
    run multiple backend processes or need cross-instance sharing."""

    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if time.time() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            self._store[key] = (time.time() + ttl, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


cache = MemoryCache()
