"""Rate limiting and request-size guards.

ATLAS exposes a small public HTTP surface: four REST services plus the MCP
endpoint, fronted by atlas-edge. None of those routes had any request ceiling, so
an unauthenticated caller could brute-force /auth/token, drive unbounded
pagination, or exhaust the event loop on /api/ask (which fans out to an LLM or the
rule-based router). These helpers are the cheapest effective mitigation and are
intentionally dependency-free at the core.

Two backends:
  * Redis (REDIS_URL set) — a shared fixed-window counter. Required whenever more
    than one worker or replica is running: an in-process table is private to each
    worker, so N workers silently multiply the configured limit by N. The
    container images run `--workers 4`, which is exactly that case.
  * In-process — single-worker local dev and tests.

Fail-open by design: if Redis is unreachable the limiter falls back to the local
table rather than rejecting traffic. An availability bug is worse here than a
temporarily looser limit, and the table still bounds each worker.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field

_MAX_TRACKED_CLIENTS = 4096


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def rate_limit_enabled() -> bool:
    return _flag("ATLAS_RATE_LIMIT", "1")


def redis_url() -> str | None:
    return os.getenv("REDIS_URL") or None


def max_body_bytes() -> int:
    """Ceiling for JSON request bodies.

    64 KiB is far above any legitimate ATLAS payload (the largest is a voice
    utterance) while keeping a single request from allocating unbounded memory.
    """
    try:
        return max(1024, int(os.getenv("ATLAS_MAX_BODY_BYTES", "65536")))
    except ValueError:
        return 65536


def max_text_length() -> int:
    """Ceiling for free-text fields (utterances, titles, categories)."""
    try:
        return max(64, int(os.getenv("ATLAS_MAX_TEXT_LENGTH", "2000")))
    except ValueError:
        return 2000


@dataclass
class _Bucket:
    hits: "OrderedDict[float, int]" = field(default_factory=OrderedDict)


class RateLimiter:
    """Fixed-window-per-client limiter keyed by an opaque client identifier.

    Fixed window rather than sliding: the burst it lets through at a boundary is
    the documented trade-off, and it needs no per-request lock in the common
    single-threaded path. Memory is bounded by evicting the least-recently-seen
    client once _MAX_TRACKED_CLIENTS is exceeded, so a spoofed-IP flood cannot
    turn the limiter itself into the leak.
    """

    def __init__(self, limit: int, window_seconds: int, name: str = "default") -> None:
        self.limit = max(1, limit)
        self.window = max(1, window_seconds)
        self.name = name
        self._clients: "OrderedDict[str, _Bucket]" = OrderedDict()

    def allow(self, client: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds). In-process only."""
        now = time.monotonic()
        cutoff = now - self.window
        bucket = self._clients.get(client)
        if bucket is None:
            bucket = self._clients[client] = _Bucket()
        else:
            self._clients.move_to_end(client)

        hits = bucket.hits
        while hits:
            oldest = next(iter(hits))
            if oldest > cutoff:
                break
            hits.pop(oldest, None)

        if sum(hits.values()) >= self.limit:
            retry_after = max(1, int(self.window - (now - min(hits))))
            return False, retry_after

        hits[now] = hits.get(now, 0) + 1

        if len(self._clients) > _MAX_TRACKED_CLIENTS:
            self._clients.popitem(last=False)
        return True, 0

    async def acquire(self, client: str) -> tuple[bool, int]:
        """Shared-counter rate limit when Redis is configured, else `allow`.

        The window is bucketed by wall clock and the bucket is part of the key, so
        every window gets its own counter and no request can extend the window it
        lands in. The previous version re-issued EXPIRE on every hit, which
        quietly turned the ceiling into an inactivity window: a client sending one
        request every 59s kept resetting the TTL and was never limited at all.

        INCR and EXPIRE go out in one pipeline, which redis-py wraps in
        MULTI/EXEC, so the TTL always lands on a counter that exists.
        """
        if not _REDIS_ENABLED:
            return self.allow(client)

        try:
            client_redis = _redis_client()
            if client_redis is None:
                # REDIS_URL is set but the client could not be built, e.g. the
                # optional `redis` extra is not installed. Fails open to the
                # in-process table rather than raising on every request.
                return self.allow(client)

            now = int(time.time())
            bucket = now // self.window
            key = f"atlas:rl:{self.name}:{_hash_client(client)}:{bucket}"
            pipe = client_redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, self.window + 1)
            count = int(pipe.execute()[0])
        except Exception:
            # Fail open: an unreachable Redis must not take the API down.
            return self.allow(client)

        if count > self.limit:
            return False, max(1, self.window - (now % self.window))
        return True, 0

    def reset(self) -> None:
        self._clients.clear()


# Named limiters, tuned per endpoint class. Auth and ask are the two expensive
# or guessable surfaces, so they get the tightest budgets.
auth_limiter = RateLimiter(limit=10, window_seconds=60, name="auth")
ask_limiter = RateLimiter(limit=20, window_seconds=60, name="ask")
write_limiter = RateLimiter(limit=120, window_seconds=60, name="write")
read_limiter = RateLimiter(limit=600, window_seconds=60, name="read")


# --------------------------------------------------------------- shared backend

_REDIS_CLIENT = None
_REDIS_CHECKED = False


def _hash_client(client: str) -> str:
    """Key-safe digest of a client identifier.

    Identifiers can come from a header, so they must not be able to inject
    colons and collide with another client's namespace or blow up key length.
    """
    import hashlib

    return hashlib.sha256(client.encode("utf-8", "replace")).hexdigest()[:32]


def _redis_client():
    """Lazily build a Redis client, or None if unavailable.

    Import is deferred so the dependency is only required when REDIS_URL is
    actually set; local dev and tests never need it.
    """
    global _REDIS_CLIENT, _REDIS_CHECKED
    if _REDIS_CHECKED:
        return _REDIS_CLIENT
    _REDIS_CHECKED = True

    url = redis_url()
    if not url:
        return None
    try:
        import redis  # type: ignore

        _REDIS_CLIENT = redis.Redis.from_url(
            url,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            health_check_interval=30,
        )
    except Exception:
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


def _redis_configured() -> bool:
    return bool(redis_url())


_REDIS_ENABLED = _redis_configured()


def client_key(request, authenticated_user_id: str | None = None) -> str:
    """Identify the caller for rate limiting.

    Prefer the authenticated subject: it is not attacker-controlled, so it cannot
    be defeated by rotating X-Forwarded-For.

    Only fall back to X-Forwarded-For when ATLAS_TRUST_PROXY_HEADERS is on. That
    header is set by the caller and is trivially spoofed, so trusting it by
    default just hands an attacker a fresh bucket per request (and, with every
    request landing on `ip:unknown`, lets one client exhaust the budget for
    everyone). Turn it on only when a proxy you control is known to overwrite the
    header -- Render and Cloudflare both do.

    When it is on, trust the *last* hop, not the first. A proxy appends the peer it
    received from, so the rightmost entry is the one the proxy observed and the
    leftmost is whatever the caller sent. Reading the leftmost entry -- which is
    what this used to do -- meant a client could send `X-Forwarded-For: <random>`
    and get a fresh rate-limit bucket on every request, defeating the limiter
    entirely while the flag was on.

    This assumes exactly one trusted hop in front of ATLAS, which is the deployed
    topology: Render terminates TLS and calls the edge directly. Chain a second
    proxy (say Cloudflare in front of Render) and the last entry becomes that
    proxy's address, collapsing anonymous callers onto one bucket; in that case
    front ATLAS directly instead.
    """
    if authenticated_user_id:
        return f"u:{authenticated_user_id}"
    peer = getattr(request, "client", None)
    host = getattr(peer, "host", None)
    if not host:
        host = "unknown"
    if _flag("ATLAS_TRUST_PROXY_HEADERS", "0"):
        hops = [hop.strip() for hop in request.headers.get("x-forwarded-for", "").split(",")]
        hops = [hop for hop in hops if hop]
        if hops:
            return f"ip:{hops[-1]}"
    return f"ip:{host}"