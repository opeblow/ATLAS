from __future__ import annotations

import asyncio
import time

from atlas_common.ratelimit import RateLimiter, client_key, max_body_bytes


def test_allows_up_to_limit_then_rejects_with_retry_hint():
    limiter = RateLimiter(limit=3, window_seconds=60, name="t")

    assert [limiter.allow("a")[0] for _ in range(3)] == [True, True, True]

    allowed, retry_after = limiter.allow("a")
    assert allowed is False
    assert 0 < retry_after <= 60


def test_clients_are_isolated():
    limiter = RateLimiter(limit=1, window_seconds=60, name="t")

    assert limiter.allow("a")[0] is True
    assert limiter.allow("a")[0] is False
    assert limiter.allow("b")[0] is True


def test_window_recovers_after_it_expires():
    limiter = RateLimiter(limit=1, window_seconds=1, name="t")

    assert limiter.allow("a")[0] is True
    assert limiter.allow("a")[0] is False

    time.sleep(1.05)
    assert limiter.allow("a")[0] is True


def test_tracked_clients_stay_bounded_under_spoofing():
    """A spoofed-IP flood must not turn the limiter itself into unbounded memory."""
    limiter = RateLimiter(limit=5, window_seconds=60, name="t")

    for i in range(5000):
        limiter.allow(f"spoofed-{i}")

    assert len(limiter._clients) <= 4096 + 1


def test_acquire_without_redis_enforces_the_limit():
    """Async path used by middleware: falls back to the local table when unset."""
    limiter = RateLimiter(limit=2, window_seconds=60, name="async")

    async def scenario():
        assert (await limiter.acquire("u"))[0] is True
        assert (await limiter.acquire("u"))[0] is True
        allowed, retry_after = await limiter.acquire("u")
        assert allowed is False
        assert retry_after > 0
        assert (await limiter.acquire("other"))[0] is True

    asyncio.run(scenario())


class _FakePipeline:
    """Minimal stand-in for redis-py's pipeline (MULTI/EXEC), enough for INCR+EXPIRE."""

    def __init__(self, store: "_FakeRedis") -> None:
        self._store = store
        self._queued: list[tuple] = []

    def incr(self, key: str):
        self._queued.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int):
        self._queued.append(("expire", key, ttl))
        return self

    def execute(self) -> list:
        results = []
        for op in self._queued:
            if op[0] == "incr":
                key = op[1]
                self._store.counters[key] = self._store.counters.get(key, 0) + 1
                results.append(self._store.counters[key])
            else:
                self._store.ttls[op[1]] = op[2]
                results.append(True)
        self._queued.clear()
        return results


class _FakeRedis:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)


def _use_fake_redis(monkeypatch, fake: _FakeRedis) -> dict[str, float]:
    """Point the limiter at `fake` and hand back a mutable wall clock."""
    from atlas_common import ratelimit

    monkeypatch.setattr(ratelimit, "_REDIS_ENABLED", True)
    monkeypatch.setattr(ratelimit, "_REDIS_CHECKED", True)
    monkeypatch.setattr(ratelimit, "_REDIS_CLIENT", fake)

    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(ratelimit.time, "time", lambda: clock["t"])
    return clock


def test_shared_counter_rolls_over_into_a_fresh_window(monkeypatch):
    """The ceiling is per window, not per key lifetime.

    A single non-expiring key makes the limit permanent for any client that keeps
    talking, and an EXPIRE re-issued on every hit makes it an inactivity window
    instead. Bucketing the window into the key is what makes this recover.
    """
    fake = _FakeRedis()
    clock = _use_fake_redis(monkeypatch, fake)
    limiter = RateLimiter(limit=5, window_seconds=60, name="rollover")

    async def scenario():
        for _ in range(2):
            assert (await limiter.acquire("u"))[0] is True

        clock["t"] += 61  # next window

        for _ in range(3):
            assert (await limiter.acquire("u"))[0] is True

    asyncio.run(scenario())

    # Two buckets were used, so the counter reset instead of accumulating.
    assert len(fake.counters) == 2
    assert sorted(fake.counters.values()) == [2, 3]


def test_shared_counter_limits_a_client_sustained_above_the_ceiling(monkeypatch):
    """Steady traffic above the ceiling must be throttled, yet not banned outright."""
    fake = _FakeRedis()
    clock = _use_fake_redis(monkeypatch, fake)
    limiter = RateLimiter(limit=2, window_seconds=60, name="steady")

    allowed = denied = 0

    async def scenario():
        nonlocal allowed, denied
        for _ in range(30):  # one request every 20s == 3/min, above a 2/min ceiling
            clock["t"] += 20
            ok, _ = await limiter.acquire("u:steady")
            allowed += ok
            denied += not ok

    asyncio.run(scenario())

    assert denied > 0, "sustained over-limit traffic was never limited"
    # A window that never resets would clamp this to 2 and lock the client out.
    assert allowed > 2, "client was throttled below its configured ceiling"


def test_shared_counter_retry_after_never_exceeds_the_window(monkeypatch):
    fake = _FakeRedis()
    clock = _use_fake_redis(monkeypatch, fake)
    limiter = RateLimiter(limit=1, window_seconds=60, name="retry")

    async def scenario():
        # Land just after a window boundary, where the remaining time is shortest.
        clock["t"] = 1_000_001.0
        assert (await limiter.acquire("u"))[0] is True
        allowed, retry_after = await limiter.acquire("u")
        assert allowed is False
        assert 0 < retry_after <= 60

    asyncio.run(scenario())


def test_shared_backend_falls_back_when_the_client_is_unavailable(monkeypatch):
    """REDIS_URL set but no usable client must fail open, not raise per request."""
    from atlas_common import ratelimit

    monkeypatch.setattr(ratelimit, "_REDIS_ENABLED", True)
    monkeypatch.setattr(ratelimit, "_REDIS_CHECKED", True)
    monkeypatch.setattr(ratelimit, "_REDIS_CLIENT", None)
    limiter = RateLimiter(limit=1, window_seconds=60, name="noclient")

    async def scenario():
        assert (await limiter.acquire("u"))[0] is True
        assert (await limiter.acquire("u"))[0] is False

    asyncio.run(scenario())


def test_shared_backend_fails_open_when_redis_raises(monkeypatch):
    class _Broken:
        def pipeline(self):
            raise ConnectionError("redis is down")

    monkeypatch_target = _use_fake_redis(monkeypatch, _Broken())
    assert monkeypatch_target is not None
    limiter = RateLimiter(limit=1, window_seconds=60, name="broken")

    async def scenario():
        assert (await limiter.acquire("u"))[0] is True
        assert (await limiter.acquire("u"))[0] is False

    asyncio.run(scenario())


class _Headers:
    def __init__(self, mapping):
        self._mapping = {k.lower(): v for k, v in mapping.items()}

    def get(self, key, default=None):
        return self._mapping.get(key.lower(), default)


class _Request:
    def __init__(self, headers):
        self.headers = _Headers(headers)
        self.client = None


def test_authenticated_identity_wins_over_forwarded_for():
    """X-Forwarded-For is caller-controlled, so it must not key the limiter once
    the caller is identified -- otherwise spoofing the header sidesteps the cap."""
    request = _Request({"x-forwarded-for": "1.2.3.4"})

    assert client_key(request, "u_alice") == "u:u_alice"


def test_forwarded_for_is_ignored_unless_a_trusted_proxy_is_declared(monkeypatch):
    """By default the header is attacker-supplied, so honouring it would hand out
    a fresh bucket per request and let one caller exhaust the global budget."""
    monkeypatch.delenv("ATLAS_TRUST_PROXY_HEADERS", raising=False)
    request = _Request({"x-forwarded-for": "1.2.3.4"})

    assert client_key(request, None) == "ip:unknown"


def test_forwarded_for_is_honoured_when_the_proxy_is_trusted(monkeypatch):
    monkeypatch.setenv("ATLAS_TRUST_PROXY_HEADERS", "1")
    request = _Request({"x-forwarded-for": "1.2.3.4, 10.0.0.1"})

    # The last hop is the one the trusted proxy appended, not the caller-supplied one.
    assert client_key(request, None) == "ip:10.0.0.1"


def test_forwarded_for_cannot_be_spoofed_to_rotate_buckets(monkeypatch):
    """A caller pre-seeding XFF must not get a fresh rate-limit bucket per request.

    The proxy appends the peer it saw, so the real address always ends up last and
    is what the limiter keys on.
    """
    monkeypatch.setenv("ATLAS_TRUST_PROXY_HEADERS", "1")

    def key_for(spoof: str) -> str:
        # `spoof, real-client` is what the proxy produces from a spoofed request.
        return client_key(_Request({"x-forwarded-for": f"{spoof}, 203.0.113.7"}), None)

    assert key_for("9.9.9.9") == key_for("8.8.8.8") == "ip:203.0.113.7"


def test_forwarded_for_single_hop_is_used_verbatim(monkeypatch):
    monkeypatch.setenv("ATLAS_TRUST_PROXY_HEADERS", "1")
    assert client_key(_Request({"x-forwarded-for": "203.0.113.7"}), None) == "ip:203.0.113.7"


def test_blank_forwarded_for_falls_back_to_the_peer(monkeypatch):
    monkeypatch.setenv("ATLAS_TRUST_PROXY_HEADERS", "1")
    request = _Request({"x-forwarded-for": " , "})
    request.client = None
    assert client_key(request, None) == "ip:unknown"


def test_body_ceiling_default_is_64_kib():
    assert max_body_bytes() == 65536