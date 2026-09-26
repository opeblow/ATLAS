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