# ATLAS on AWS — integration guide

This repo ships a fully local, self-hosted system (no account required). This
document maps each component onto the AWS services from the mini-challenge and
gives the exact steps to stand it up server-side.

## The mapping

| Local component                 | AWS counterpart                                     |
|---------------------------------|-----------------------------------------------------|
| risk-model :8000 (PyTorch/FastAPI) | ECS Fargate task (CPU-only, one container)       |
| finance-service :8001           | ECS Fargate service (FastAPI on uvicorn)            |
| scheduling-service :8002        | ECS Fargate service                                 |
| mcp-server :8003 (Streamable HTTP) | ECS Fargate service, behind ALB path `/mcp`      |
| shared `atlas.db` / SQLAlchemy  | RDS PostgreSQL 15 (schema in `atlas_common/schema.sql`) |
| bearer tokens (dev)             | Session table in Postgres, or JWT issued by the orchestrator |
| reasoning (Bedrock w/ fallback) | Amazon Bedrock `converse` (tool use) + an AgentCore runtime hook |
| dashboard :3000 (Next.js)       | S3 + CloudFront static export, or Amplify            |
| model artifacts `.pt` + scaler  | S3 (mounted/downloaded at task start)               |
| env config                      | SSM Parameter Store / task env vars                 |
| audit trail `mcp_tool_calls`    | Postgres tables (already partition-ready) + optional CloudWatch |

## 1. Database (RDS Postgres)

1. Create an RDS PostgreSQL instance (default `atlas` DB / `atlas_user`).
2. Apply the DDL once: `psql "postgres://..." -f services/common/atlas_common/schema.sql`
3. Every service boots with:
   ```
   ATLAS_DATABASE_URL=postgresql+psycopg2://atlas_user:...@<rds-endpoint>:5432/atlas
   ```
   The same SQLAlchemy models run identically on SQLite (local) and Postgres (AWS).

## 2. Explainer services (risk-model, finance, scheduling)

Each is a plain FastAPI app. Build its image, push to ECR, and run on Fargate:

```
docker build -t atlas/{name} services/{name}
```

Minimal task-relevant details:
- **risk-model**: needs the trained artifacts (`app/artifacts/risk_mlp.pt`,
  `scaler.json`). Restart the task from the latest image to pick up a retrain;
  no DB needed. Expose only to the finance service's security group.
- **finance-service**: needs `ATLAS_DATABASE_URL` and the risk-model internal
  URL (`RISK_MODEL_URL=http://atlas-risk-model:8000`).
- **scheduling-service**: only `ATLAS_DATABASE_URL`.

`ATLAS_REQUIRE_AUTH`, TTL cache and breaker settings are read from env so the
Fargate tasks can tune them per environment (see `atlas_common/config.py`).

## 3. MCP server

- `fastmcp` Streamable HTTP app, mounted at `/mcp` behind the ALB.
- Bearer auth stays as it is locally (header-only gate + in-tool identity
  checks) — the middleware class is transport-agnostic.
- The Alexa+ skill / MCP client points at `https://atlas.example.com/mcp` and
  sends `Authorization: Bearer <session-token>`.
- For ALB path routing, set `ATLAS_MCP_PATH=/mcp` (the app is mounted
  accordingly in `transport/streamable_http.py`).

## 4. Reasoning layer

Two modes, one interface (`orchestrator/executor.py`):

- **Bedrock (primary).** `bedrock.converse` with the six `toolSpec`s, then a
  second turn to draft the reply. Model default `amazon.nova-micro-v1:0`
  (cheap, structural output). Set the region/model via env.
- **Fallback (offline/default).** Keyword intent router so the whole demo runs
  with zero AWS credentials and never hard-depends on the cloud.

Where AgentCore fits: the AgentCore runtime replaces the hand-rolled
two-turn loop by acting as the host for the Alexa+ skill, invoking this MCP
server's tools as its tool layer, and storing the session state. The
`toolSpec` schemas in `tools_spec.py` are the single source of truth for both
the fallback router and the Bedrock call.

**Permissions (terraform wires this):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0" }
  ]
}
```

## 5. Dashboard

Static export is the cheapest path:

```
cd dashboard
npm run build            # next build already works locally (100% offline-safe fonts/CSS)
```

Serve `.next` (or the export output) from S3 + CloudFront. Data URLs are
configurable via `app/lib/api.ts`, so point them at the ALB endpoints.

## 6. Go-live checklist

- [ ] RDS running; `schema.sql` applied; security group allows the Fargate tasks.
- [ ] ECR images pushed for the four Python services.
- [ ] ECS cluster + task definitions with `ATLAS_DATABASE_URL` and internal URLs.
- [ ] ALB listener: `/mcp*` → mcp-server target group; `/` path rules for
      finance/scheduling dashboards.
- [ ] Bedrock model access enabled for `amazon.nova-micro-v1:0` in us-east-1.
- [ ] `.pt` + `scaler.json` copied into the risk-model image (or S3 bootstrap).
- [ ] Smoke test: `get_risk_snapshot`, `log_transaction` (dup), `commit_schedule` (dup).