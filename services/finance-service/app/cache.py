"""Small TTL cache with automatic Redis support.

- REDIS_URL set  -> redis cache (production hot path, Section 8.2)
- otherwise      -> process-local dict with TTL (single-instance dev)

Only used for hot reads: current balance, latest risk snapshot, today's schedule.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


class TtlCache:
    def __init__(
        self, default_ttl_seconds: float = 30.0, local_ttl_seconds: float = 1.5
    ) -> None:
        self._default_ttl = default_ttl_seconds
        self._local_ttl = local_ttl_seconds
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, Any]] = {}
        self._inflight_lock = threading.Lock()
        self._inflight: dict[str, Future[Any]] = {}
        self._redis = None
        self._redis_ok = False
        try:  # optional dependency — only used when REDIS_URL is configured
            from atlas_common.config import settings

            if settings.redis_url:
                import redis  # type: ignore

                self._redis = redis.Redis.from_url(settings.redis_url)
                self._redis_ok = True
        except ImportError:
            logger.warning("Redis is configured but the redis package is unavailable")
        except Exception:
            logger.exception("Unable to initialize Redis cache; using local cache")
            self._redis = None
            self._redis_ok = False

    def get_or_set(
        self, key: str, producer: Callable[[], T], ttl: float | None = None
    ) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached

        with self._inflight_lock:
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[key] = future

        if not owner:
            return future.result()

        try:
            cached = self.get(key)
            if cached is not None:
                future.set_result(cached)
                return cached
            value = producer()
            self.set(key, value, ttl)
            future.set_result(value)
            return value
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self._inflight_lock:
                self._inflight.pop(key, None)

    def get(self, key: str) -> Any | None:
        local_value = self._get_local(key)
        if local_value is not None:
            return local_value
        if self._redis_ok:
            try:
                raw = self._redis.get(key)
                if raw is not None:
                    value = json.loads(raw)
                    self._set_local(key, value, self._local_ttl)
                    return value
            except Exception:
                logger.warning(
                    "Redis cache read failed for key %s; checking local cache",
                    key,
                    exc_info=True,
                )
        return self._get_local(key)

    def _get_local(self, key: str) -> Any | None:
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
        local_ttl = min(ttl, self._local_ttl) if self._redis_ok else ttl
        self._set_local(key, value, local_ttl)
        if self._redis_ok:
            try:
                self._redis.setex(key, max(1, int(ttl)), json.dumps(value))
            except Exception:
                logger.warning(
                    "Redis cache write failed for key %s; retaining local value",
                    key,
                    exc_info=True,
                )

    def _set_local(self, key: str, value: Any, ttl: float) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + ttl, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)
        if self._redis_ok:
            try:
                self._redis.delete(key)
            except Exception:
                logger.warning("Redis cache delete failed for key %s", key, exc_info=True)


cache = TtlCache()