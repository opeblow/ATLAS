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

    assert client_key(request, None) == "ip:1.2.3.4"


def test_body_ceiling_default_is_64_kib():
    assert max_body_bytes() == 65536