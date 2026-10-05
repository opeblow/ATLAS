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

        INCR-then-EXPIRE is atomic enough here: the window is a coarse traffic
        ceiling, so losing the race to set a TTL (both callers setting the same
        value) is harmless. The counter is expired on every reset of the window.
        """
        if not _REDIS_ENABLED:
            return self.allow(client)

        try:
            key = f"atlas:rl:{self.name}:{_hash_client(client)}"
            pipe = _redis_client().pipeline()
            pipe.incr(key)
            pipe.expire(key, self.window)
            count = int(pipe.execute()[0])
        except Exception:
            # Fail open: an unreachable Redis must not take the API down.
            return self.allow(client)

        if count > self.limit:
            return False, self.window
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
    """
    if authenticated_user_id:
        return f"u:{authenticated_user_id}"
    peer = getattr(request, "client", None)
    host = getattr(peer, "host", None)
    if not host:
        host = "unknown"
    if _flag("ATLAS_TRUST_PROXY_HEADERS", "0"):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{host}"