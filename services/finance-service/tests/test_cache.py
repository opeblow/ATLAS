from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.cache import TtlCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        assert ttl >= 1
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def test_redis_cache_uses_short_lived_local_copy() -> None:
    cache = TtlCache(local_ttl_seconds=0.05)
    cache._redis = FakeRedis()
    cache._redis_ok = True

    cache.set("balance:user", {"balance": 12}, ttl=30)
    assert cache.get("balance:user") == {"balance": 12}

    cache._redis.values["balance:user"] = '{"balance": 20}'
    assert cache.get("balance:user") == {"balance": 12}

    time.sleep(0.06)
    assert cache.get("balance:user") == {"balance": 20}


def test_redis_failure_falls_back_to_local_cache() -> None:
    class UnavailableRedis:
        def get(self, key: str) -> None:
            raise ConnectionError("Redis unavailable")

        def setex(self, key: str, ttl: int, value: str) -> None:
            raise ConnectionError("Redis unavailable")

        def delete(self, key: str) -> None:
            raise ConnectionError("Redis unavailable")

    cache = TtlCache()
    cache._redis = UnavailableRedis()
    cache._redis_ok = True

    cache.set("risk:user", {"score": 0.25}, ttl=30)

    assert cache.get("risk:user") == {"score": 0.25}


def test_concurrent_cache_misses_share_one_producer() -> None:
    cache = TtlCache()
    workers_ready = threading.Barrier(7)
    producer_started = threading.Event()
    release_producer = threading.Event()
    calls = 0

    def producer() -> dict[str, bool]:
        nonlocal calls
        calls += 1
        producer_started.set()
        assert release_producer.wait(timeout=2)
        return {"ready": True}

    def load() -> dict[str, bool]:
        workers_ready.wait(timeout=2)
        return cache.get_or_set("shared", producer)

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = [executor.submit(load) for _ in range(6)]
        workers_ready.wait(timeout=2)
        assert producer_started.wait(timeout=2)
        time.sleep(0.05)
        release_producer.set()
        assert [result.result(timeout=2) for result in results] == [
            {"ready": True}
        ] * 6

    assert calls == 1
