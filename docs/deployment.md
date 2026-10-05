# Deploying ATLAS

Two pieces:

| Piece | Host | What it is |
|---|---|---|
| `atlas` | Render (Python web service) | One process serving finance, scheduling, risk and MCP under a single origin |
| `atlas-dashboard` | Cloudflare Pages | Static Next.js export, no server runtime |

The local demo uses a rule-based router and reports it as simulated. The
repository's Render template now fails closed on Cognito configuration and
requires an externally managed database URL. Do not deploy it expecting a
working demo until those settings are configured.

## Why the backend is one service

Finance, scheduling, MCP and the audit log all read and write the same managed
PostgreSQL database. Four Render services would each get their own filesystem and could not
see each other's writes, so `services/edge/atlas_edge/asgi.py` mounts all four
ASGI apps behind one port:

```
/finance/*   -> finance-service
/schedule/*  -> scheduling-service
/risk/*      -> risk-model
/mcp/*       -> MCP server (Streamable HTTP)
/api/ask     -> orchestrator (local router)
/api/capabilities  -> what is live vs simulated
```

The multi-service architecture is unchanged; `docker-compose.yml` still runs four
containers, and sub-services still talk to each other over real HTTP.

## 1. Backend on Render

`render.yaml` is a Blueprint, so Render can create the service from it:

1. Push the branch to GitHub.
2. In Render: **New → Blueprint**, select the repo, apply.
3. Set `ATLAS_CORS_ORIGINS` to your Cloudflare Pages URL once step 2 is done
   (e.g. `https://atlas-dashboard.pages.dev`).

Or configure a Python service by hand:

| Field | Value |
|---|---|
| Root directory | `.` |
| Build command | see below |
| Start command | `python -m atlas_edge.asgi` |
| Health check path | `/edge/health` |

Build command:

```bash
pip install --upgrade pip
pip install "numpy>=1.26" "torch>=2.2" --index-url https://download.pytorch.org/whl/cpu
pip install -e ./services/common -e ./services/edge -e ./services/finance-service \
            -e ./services/scheduling-service -e ./services/risk-model \
            -e ./mcp-server -e ./reasoning/bedrock-orchestrator
```

The CPU-only torch index matters: the default wheel is roughly 2.5GB and the
build times out.

### Environment variables

| Variable | Value | Why |
|---|---|---|
| `PORT` | set by Render | uvicorn bind port |
| `ATLAS_SELF_URL` | `http://127.0.0.1:8000` | base URL sub-services call each other on |
| `ATLAS_DATABASE_URL` | External managed PostgreSQL DSN | Required; Render filesystem is not durable |
| `ATLAS_SEED_ON_START` | `0` | Do not seed shared production data |
| `ATLAS_MOCK_BEDROCK` | `1` | route `/api/ask` through the local router |
| `ATLAS_AUTH_MODE` | `cognito` | Production authentication mode |
| `ATLAS_REQUIRE_AUTH` | `1` | Fail closed; cannot disable in Cognito mode |
| `ATLAS_COGNITO_ISSUER` | Cognito user-pool issuer URL | Validate token issuer/signing keys |
| `ATLAS_COGNITO_APP_CLIENT_ID` | Cognito public app-client ID | Bind access tokens to the dashboard client |
| `AWS_REGION` | Cognito pool / Bedrock region | Resolve user-pool JWKS and optional Bedrock |
| `ATLAS_CORS_ORIGINS` | your Pages URL | the dashboard is cross-origin |
| Dashboard `NEXT_PUBLIC_COGNITO_DOMAIN` | Cognito hosted UI base URL | OAuth authorization-code + PKCE |
| Dashboard `NEXT_PUBLIC_COGNITO_APP_CLIENT_ID` | Cognito public client ID | Must match backend verifier |
| Dashboard `NEXT_PUBLIC_COGNITO_REDIRECT_URI` | Exact registered `/auth/callback` URL | OAuth callback |

### Two things to know before demoing

**The free plan is not a production database or scale tier.** Use managed
PostgreSQL with backups and tested restore procedures; never persist user data
to the service's local filesystem.

**The free plan sleeps.** A cold start takes a few seconds while the container
boots and the model loads. Send a request before you present.

### Verify the deploy

```powershell
$ATLAS = "https://atlas-<hash>.onrender.com"

curl "$ATLAS/edge/health"
curl "$ATLAS/api/capabilities"

# user endpoints require a valid Cognito access token; see OAuth setup below
```

`/api/capabilities` should report `bedrock.mode = "simulated"` and
`database.mode = "sqlite"`.

## 2. Dashboard on Cloudflare Pages

The dashboard is a static export, so Pages needs no build adapter.

| Field | Value |
|---|---|
| Framework preset | None |
| Build command | `npm run build` |
| Build output directory | `out` |
| Root directory | `dashboard` |
| Node version | 20 or newer |

Set one build variable:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_ATLAS_URL` | your API URL, no trailing slash |
| `NEXT_PUBLIC_COGNITO_DOMAIN` | Cognito hosted UI domain, without a trailing slash |
| `NEXT_PUBLIC_COGNITO_APP_CLIENT_ID` | Cognito public client ID |
| `NEXT_PUBLIC_COGNITO_REDIRECT_URI` | Exact public `/auth/callback` URL |

`NEXT_PUBLIC_ATLAS_URL` is inlined at build time, so redeploy the Pages project
whenever the Render URL changes. Building without it prints a warning and falls
back to `127.0.0.1`, which will not reach a deployed backend.

Local equivalent:

```powershell
cd dashboard
$env:NEXT_PUBLIC_ATLAS_URL = "http://127.0.0.1:8000"
npm run build          # writes dashboard/out
npx serve out
```

`NEXT_PUBLIC_ATLAS_URL` is optional for local builds: with it unset, `lib/api.ts`
falls back to the four separate dev ports.

## Running the same thing locally

One process, same shape as production:

```powershell
$env:ATLAS_SEED_ON_START = "1"
$env:ATLAS_AUTH_MODE = "dev"
$env:ATLAS_REQUIRE_AUTH = "0"
python -m atlas_edge.asgi            # http://127.0.0.1:8000
```

Verify it the way the deploy is verified:

```powershell
$env:ATLAS_BASE_URL = "http://127.0.0.1:8000"
cd mcp-server; python -m pytest tests -q

cd ..\reasoning\bedrock-orchestrator; python -m pytest tests -q
```

`ATLAS_AUTH_MODE=dev` is for local testing only; it enables the development
token issuer. Never set this mode on an internet-facing deployment. The
integration suite verifies bearer auth and rejects a user ID that does not
match the authenticated token.

## Turning on real Bedrock

Authenticate locally (for example, `aws sso login --profile <profile>`), set
`AWS_PROFILE`, `AWS_REGION`, and `ATLAS_MOCK_BEDROCK=0`, then run
`python scripts/test_bedrock.py --profile <profile>` to make a live, small
Converse request. The caller needs `bedrock:InvokeModel` and access to the
configured model. `orchestrator/bedrock.py` then routes to
`amazon.bedrock-runtime` and `/api/capabilities` reports `bedrock.mode =
"live"`. The local router stays in place as the fallback if Bedrock is
unreachable at call time; a fallback response must be identified as simulated.