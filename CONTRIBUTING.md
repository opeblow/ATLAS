# Contributing to ATLAS

Thanks for wanting to help build a chief of staff that actually understands
money and time. This is a small, deliberately tidy repo — keep it that way.

## Development setup

Requires Python 3.10+ and Node 20+.

```powershell
# 1. install the Python packages (editable, in dependency order)
cd services/common            && python -m pip install -e .
cd services/risk-model        && python -m pip install -e .
cd services/finance-service   && python -m pip install -e .
cd services/scheduling-service && python -m pip install -e .
cd mcp-server                 && python -m pip install -e .
cd reasoning/bedrock-orchestrator && python -m pip install -e .

# 2. boot the stack
cd ..\.. && powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

# 3. dashboard
cd dashboard && npm install && npm run dev
```

`scripts/dev.ps1` starts, in order: risk-model (:8000) → finance (:8001) →
scheduling (:8002) → MCP server (:8003). Restart order matters — finance
needs the model; the MCP server needs finance and scheduling.

## Testing

```powershell
# end-to-end (stack must be up)
cd mcp-server && python -m pytest tests -q

# unit tests that need nothing running
cd services/scheduling-service   && python -m pytest tests -q
cd reasoning/bedrock-orchestrator && python -m pytest tests -q

# dashboard build check
cd dashboard && npm run build
```

Every pull request must pass the CI workflow `.github/workflows/ci.yml`,
which runs the same commands on Linux.

## Code style & conventions

- **Python**: 3.10+ syntax, `from __future__ import annotations` in service
  code, type hints on public functions. No formatter is enforced, but match
  the surrounding style (double quotes, 100 columns, plain docstrings).
- **No comments beyond what the code says.** If something is subtle, a short
  module or function docstring beats a wall of inline comments.
- **Shared DB access lives only in `atlas_common`** (models, schema, audit).
  Services must not define their own tables. The MCP server and dashboard are
  *HTTP clients only* — never import the DB layer there.
- **Don't load torch in the MCP process.** The risk model stays out-of-process;
  everything else talks to it over HTTP.
- **Idempotency is sacred.** Any new write capability takes an
  `idempotency_key` and returns a "duplicate" marker instead of writing twice.
- **Every tool call is audited** via `atlas_common.audit.timed_tool_call` —
  new tools get a row automatically.

## Making a change

1. Fork / branch: `feat/`, `fix/`, `docs/` prefixes.
2. Add or update tests for the change — unit tests where possible, entries in
   the integration walkthrough (`scripts/demo_client.py`) for user-visible
   flows.
3. Run the local test suite (above) and `npm run build` if the dashboard is
   touched.
4. Open a PR. Keep it focused; explain the *why* in the description and update
   `docs/architecture.md` + `README.md` when behaviour or layout changes.

## Project layout (short version)

```
mcp-server/               standalone MIT-licensed MCP server (6 tools)
services/common/          atlas_common — models, config, audit, schema.sql
services/risk-model/      PyTorch MLP risk scorer, FastAPI :8000
services/finance-service/ ledger, affordability, risk snapshots :8001
services/scheduling-service/ deadlines, plan, commit :8002
reasoning/bedrock-orchestrator/ Bedrock tool-use + offline fallback
dashboard/                Next.js command center :3000
infra/terraform/          AWS provisioning (RDS, ECS/Fargate, ALB, Bedrock IAM)
scripts/                  dev.ps1, demo_client.py
docs/                     architecture, aws-integration, demo-script
```