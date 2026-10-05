# Security Policy

ATLAS is a self-hosted reference implementation for the *Agentic Chief of
Staff* mini-challenge. We treat the security posture seriously even though the
default dev mode runs on one SQLite file with no network exposure. Report
issues, don't spam bullets.

## Reporting a vulnerability

**Do not** open a public issue for a security bug.

Email the maintainer directly (see `LICENSE` / git history for the address), or
open a **private** report via GitHub's advisory flow:
`Security → Report a vulnerability` on this repository.

Include:

- the affected component (`services/*`, `mcp-server`, `reasoning/*`,
  `dashboard`) and version/commit,
- a minimal reproduction (endpoints, payload),
- impact assessment and any suggested fix.

We aim to acknowledge within 72 hours and ship a fix in the next release once
confirmed. If you prefer, you can wait for public disclosure before we make a
release.

## Supported scope

| Component        | Supported | Notes |
|------------------|-----------|-------|
| `mcp-server`     | yes       | primary attack surface (network-facing) |
| `services/*`     | yes       | FastAPI uvicorn defaults + CORS locked to the dashboard |
| `reasoning/*`    | yes       | boto3 Bedrock calls, no secrets stored |
| `dashboard`      | yes       | read-only + forms; server components fetch via REST |
| `infra/terraform`| yes       | proof-of-concept provisioning, review before prod |

## Key security properties we enforce (please keep them when contributing)

- **Never trust a session id from a tool argument.** Identity comes from the
  bearer token at the transport; every tool re-checks the caller-supplied
  `user_id` against the token's user (`mcp-server/src/atlas_mcp_server/tools/identity.py`).
- **No secrets in the repo.** Never commit `.env`, `terraform.tfvars`, tokens,
  or AWS keys. Config reads env / SSM.
- **Boundaries**: the MCP server and dashboard never import the DB layer;
  database access lives only in `atlas_common` + the two services.
- **Idempotent writes**: `log_transaction` and `commit_schedule` are
  keyed so replayed (possibly malicious) retries can't double-write.
- **Least privilege in AWS**: the task role in `infra/terraform` can invoke
  exactly one Bedrock model and nothing else.

## Dev-mode caveats (honest defaults)

- Default `ATLAS_REQUIRE_AUTH=0` for local convenience. Enable it in
  anything exposed beyond localhost (`dev.ps1 -Auth` or the env var).
- `/auth/token` is a dev token-issuer — replace with your session/JWT layer
  before exposing ATLAS publicly.
- The risk model endpoint is unauthenticated within the VPC by design
  (internal-only); keep its security group private.
- CORS is locked to `http://localhost:3000` / `http://127.0.0.1:3000`.

## Reporting reward

This is a non-commercial project; contributions and public acknowledgement,
not bounties.

## Transport and edge controls

Enforced in `services/edge/atlas_edge/asgi.py` via `SecurityMiddleware`, which
wraps the whole app so the four mounted services inherit it:

- **Request-size ceiling.** `ATLAS_MAX_BODY_BYTES` (default 64 KiB), enforced
  both on the declared `Content-Length` *and* while reading the body stream, so
  a chunked or understated length cannot allocate unbounded memory.
- **Rate limiting.** Per-client fixed-window limits on every route, with tighter
  budgets for mutating methods than reads. `/api/ask` and `/auth/token`
  additionally apply stricter in-handler limiters because they are the expensive
  and guessable surfaces. Set `ATLAS_RATE_LIMIT=0` to disable.
- **Rate-limit identity.** The authenticated subject is preferred over the peer
  IP. `X-Forwarded-For` is attacker-controlled, so it is **ignored unless
  `ATLAS_TRUST_PROXY_HEADERS=1`** — trusting it by default would hand out a fresh
  bucket per request, and would collapse every client that sends no such header
  onto a single shared bucket. Enable it only behind a proxy that overwrites the
  header (Render, Cloudflare). The in-process limiter's client table is bounded so
  a spoofed-IP flood cannot turn the limiter itself into the leak.
- **CORS.** Explicit methods and headers, `allow_credentials=False`, and a
  preflight cache — rather than `*` on both.

### Shared counting (required for more than one worker)

The in-process limiter is per worker. The service images run `--workers 4`, which
would silently multiply every configured limit by four. Setting `REDIS_URL`
switches the counters to a shared fixed window; without it ATLAS still limits,
but per worker. `docker-compose.yml` and `services/edge/Dockerfile` both set it,
and the limiter **fails open** to the local table if Redis is unreachable — an
availability bug is worse here than a temporarily looser ceiling.

### The edge must be the only public entrypoint

`docker-compose.yml` publishes just `edge` (plus Postgres for local tooling) and
gives the four application services `expose:` instead of `ports:`. CORS is not
access control: a non-browser client ignores it entirely, so a host-published
8000–8003 lets any caller skip the body ceiling, the rate limiter, and request
normalisation.

## Token handling

- Dev-mode tokens are stored as a **SHA-256 digest**, not the bearer value, so a
  database dump does not hand out working credentials. Lookup is by digest and
  the equality check is constant-time (`hmac.compare_digest`), with a dummy
  comparison on a miss so "unknown token" and "wrong token" cost the same.
- Rows minted **before** digests were introduced stored the bearer value itself.
  Rather than silently logging every existing session out, a digest miss falls
  back to the raw value once and rewrites the row to its digest, so plaintext at
  rest drains away as users return instead of needing a migration script.
- Cognito access tokens are verified with the issuer pinned and `RS256` only,
  then checked for `token_use=access`, an app-client match, and a non-empty
  `sub`. Audience verification stays off deliberately because Cognito puts the
  app client in `client_id` rather than `aud`; the explicit `client_id` check is
  what enforces it.

## Dashboard transport

The dashboard is a Next.js **static export**, so `headers()` in `next.config.ts`
is inert for it. Security headers are **generated** into
`dashboard/public/_headers` by `scripts/build-headers.mjs` during `prebuild`, and
Cloudflare Pages and Netlify both honour the result: CSP, HSTS, `X-Frame-Options:
DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP, plus an immutable
cache for hashed `_next/static` assets and `no-store` for the HTML shell.

Two reasons it is generated rather than committed literally:

- `connect-src` is derived from `NEXT_PUBLIC_ATLAS_URL`. The dashboard is a static
  bundle on a different host from the API, so `connect-src 'self'` alone would
  block every fetch and the app would fail closed with no obvious cause.
- The `_headers` grammar is only a path followed by indented `Name: value` lines.
  Prose inside a block is not reliably supported by Cloudflare Pages and can
  invalidate the entire file, so the emitted file contains directives only and
  the generator carries the commentary.

The containerised build bakes the same origin into `nginx.conf`, since nginx does
not read `_headers`.

The API client (`app/lib/api.ts`) bounds every call with a timeout and maps
error statuses to generic messages — backend bodies can carry driver messages or
stack traces, so the detail goes to the console rather than the DOM.

## Input validation

Request bodies are length-bounded at the schema (`Field(max_length=...)`), and
pagination takes `ge=0, le=1_000_000` — an unbounded or negative `offset` is a
500 at best and a cheap way to pin the database at worst.

## Container and supply-chain posture

- **No root in any image.** All five service images create an unprivileged
  `atlas` user (uid 10001), `chown` the tree, and drop to it via `USER`. The
  dashboard image is `nginxinc/nginx-unprivileged` (uid 101) rather than stock
  nginx. A container escape should not start from uid 0.
- **Redis is not published.** `docker-compose.yml` gives it `expose:` only; an
  unauthenticated Redis on a routable port is a well-trodden RCE path.
- **CI actions are pinned to commit SHAs**, not mutable tags — a tag can be
  repointed at new code that then executes with the workflow's token.
- **CI runs dependency review** (PR-only, fails on high severity) and a
  **full-history secret scan**, which catches a credential that was committed and
  later deleted.
- The dashboard image requires `NEXT_PUBLIC_ATLAS_URL` as a build arg and fails
  the build without it, rather than shipping a bundle wired to `127.0.0.1`.