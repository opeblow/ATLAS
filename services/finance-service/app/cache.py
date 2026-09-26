"""Small TTL cache with automatic Redis support.

- REDIS_URL set  -> redis cache (production hot path, Section 8.2)
- otherwise      -> process-local dict with TTL (single-instance dev)

Only used for hot reads: current balance, latest risk snapshot, today's schedule.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class TtlCache:
    def __init__(self, default_ttl_seconds: float = 30.0) -> None:
        self._default_ttl = default_ttl_seconds
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, Any]] = {}
        self._redis = None
        self._redis_ok = False
        try:  # optional dependency — only used when REDIS_URL is configured
            from atlas_common.config import settings

            if settings.redis_url:
                import redis  # type: ignore

                self._redis = redis.Redis.from_url(settings.redis_url)
                self._redis_ok = True
        except Exception:
            self._redis = None
            self._redis_ok = False

    def get_or_set(
        self, key: str, producer: Callable[[], T], ttl: float | None = None
    ) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = producer()
        self.set(key, value, ttl)
        return value

    def get(self, key: str) -> Any | None:
        if self._redis_ok:
            try:
                import json

                raw = self._redis.get(key)
                if raw is None:
                    return None
                return json.loads(raw)
            except Exception:
                return None
        with self._lock:
            hit = self._store.get(key)
            if hit is None:
                return None
            expires_at, value = hit
            if time.monotonic() > expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        if self._redis_ok:
            try:
                import json

                self._redis.setex(key, int(ttl), json.dumps(value))
            except Exception:
                pass
            return
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)

    def delete(self, key: str) -> None:
        if self._redis_ok:
            try:
                self._redis.delete(key)
            except Exception:
                pass
            return
        with self._lock:
            self._store.pop(key, None)


cache = TtlCache()