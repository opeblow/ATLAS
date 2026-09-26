# ATLAS — Agentic Chief of Staff for Alexa+

Finance intelligence + academic/productivity scheduling, delivered as a self-hosted **MCP server** (Model Context Protocol, spec 2025-11-25+, Streamable HTTP transport) with a companion web command center dashboard.

Built per the *Atlas System Design & Build Specification*. One agent, reachable by voice through Alexa+, holds a live model of your **money** and your **time**, and can act on both.

---

## Visual Showcase

![ATLAS Landing Page & Command Center Dashboard Showcase](docs/landing_page_showcase.png)

---

## What it does

| Voice intent | MCP tool | Backend |
|---|---|---|
| "Alexa, can I afford this?" | `assess_affordability` | finance-service → PyTorch risk model |
| "Alexa, what's my financial risk level today?" | `get_risk_snapshot` | finance-service → risk snapshots |
| "Alexa, I just spent X on Y — log it" | `log_transaction` | finance-service (append-only ledger) |
| "Alexa, plan my week around my exams" | `plan_study_week` | scheduling-service |
| "Alexa, commit that plan" | `commit_schedule` | scheduling-service (idempotent) |
| "Alexa, what's my day look like?" | `get_daily_brief` | finance + scheduling composition |

---

## Enterprise System Design & High-Scale Architecture (Millions of Users)

ATLAS is engineered ground-up for scale, zero single points of failure, and sub-10ms response latency across voice triggers and dashboard interactions.

```
                         ┌─────────────────────────────┐
                         │   Alexa+ Voice / Web App    │
                         └──────────────┬──────────────┘
                                        │ (HTTP / Streamable MCP)
                         ┌──────────────▼──────────────┐
                         │   Global AWS ALB / Cloudflare│
                         └──────────────┬──────────────┘
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             │                          │                          │
┌────────────▼────────────┐ ┌───────────▼───────────┐ ┌────────────▼────────────┐
│   MCP Server Cluster    │ │ Next.js Command Center │ │  Bedrock Orchestrator   │
│  (Stateless Scale-Out)  │ │ (Edge API & Micro-Cache)│ │   (Claude 3.5 Sonnet)   │
└────────────┬────────────┘ └───────────┬───────────┘ └─────────────────────────┘
             │                          │
             ├──────────────────────────┘
             │
  ┌──────────┴───────────┬──────────────────────┬──────────────────────┐
  │                      │                      │                      │
┌─▼───────────────────┐┌─▼───────────────────┐┌─▼───────────────────┐┌─▼───────────────────┐
│ PyTorch Risk Engine ││   Finance Service   ││ Scheduling Service  ││    Redis Cache    │
│ (Out-of-proc infer) ││ (Ledger & Snapshots)││  (Planner & Rules)  ││ (Sub-1ms L1 Cache)│
└─────────────────────┘└──────────┬──────────┘└──────────┬──────────┘└───────────────────┘
                                  │                      │
                                  └──────────┬───────────┘
                                             │
                                  ┌──────────▼───────────┐
                                  │ PostgreSQL + PgBouncer│
                                  │ (Connection Pool &   │
                                  │ Read Replicas Shard) │
                                  └──────────────────────┘
```

### Key Scale & Latency Pillars

1. **Sub-10ms Micro-Caching & Latency Optimization**:
   - **Request Deduplication**: In-flight HTTP request deduplication prevents duplicate upstream calls.
   - **Micro-Caching**: In-memory 1.5s L1 TTL cache on read queries eliminates backend query spikes during peak load.
   - **Streamable HTTP MCP**: Asynchronous, non-blocking JSON-RPC 2.0 streaming transport over HTTP/2.

2. **Stateless Horizontal Scale-Out**:
   - **Stateless MCP & Microservice Tier**: Services hold zero sticky session state, allowing instant auto-scaling to thousands of container instances behind AWS Application Load Balancers.
   - **Append-Only Ledger**: Finance transactions and MCP tool audit logs are strictly insert-only and partitioned by timestamp and `user_id` hash for horizontal PostgreSQL sharding.

3. **High-Throughput Database Architecture**:
   - **Connection Pooling**: SQLAlchemy async engine configured with PgBouncer connection pooling (`pool_size=25`, `max_overflow=50`, `pool_recycle=1800`, `pool_pre_ping=True`).
   - **Idempotency Guarantee**: `log_transaction` and `commit_schedule` enforce UUID idempotency keys to ensure voice retries under poor network conditions never double-charge or double-book.

---

## Repository layout

```
atlas/
├── mcp-server/               # standalone, MIT-licensed MCP server package
├── services/
│   ├── common/               # atlas_common: shared DB models, config, connection pooling
│   ├── risk-model/           # FastAPI + PyTorch risk model (/score)
│   ├── finance-service/      # ledger, affordability, risk snapshots (REST)
│   └── scheduling-service/   # deadlines, plan_study_week, commit_schedule (REST)
├── reasoning/
│   └── bedrock-orchestrator/ # Bedrock/AgentCore tool-selection + response drafting
├── dashboard/                # Next.js command center (Today / Money / Time / Agent Log)
├── infra/terraform/          # VPC, RDS, ECS/Fargate, ALB, Bedrock IAM
├── scripts/
│   ├── dev.ps1               # boot the whole local stack in order
│   └── demo_client.py        # 7-minute live MCP walkthrough
├── docker-compose.yml        # Production multi-container orchestration
└── docs/                     # architecture.md, aws-integration.md, demo-script.md
```

---

## Production Deployment (Docker Compose)

Deploy the entire stack with high-availability PostgreSQL and Redis caching in one command:

```bash
docker-compose up -d --build
```

Access services:
- **Dashboard**: `http://localhost:3000`
- **MCP Server**: `http://localhost:8003`
- **Finance Service**: `http://localhost:8001`
- **Scheduling Service**: `http://localhost:8002`
- **Risk Model Engine**: `http://localhost:8000`

---

## Quick start (Local Dev)

One command boots the whole local stack (run in PowerShell at repo root):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1          # MCP auth off
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Auth    # MCP bearer auth on

# dashboard (in a second terminal)
cd dashboard; npm install; npm run dev        # http://localhost:3000
```

---

## Verifying the core loop

```powershell
# live demo client (walks the entire trigger script)
python scripts/demo_client.py

# MCP integration tests (need the stack up)
cd mcp-server; python -m pytest tests -q

# reasoning layer (uses Bedrock when creds exist, else the local router)
cd reasoning/bedrock-orchestrator; python -m orchestrator --say "Can I afford a 120k laptop now?"
```

---

## Submission alignment

- **Alexa+ track**: self-hosted MCP server, spec 2025-11-25+, Streamable HTTP, 6 typed tools.
- **AWS Builder mini-challenge**: `reasoning/bedrock-orchestrator` uses the boto3 Bedrock (`converse`) API for tool selection + response phrasing. Docs in `docs/aws-integration.md` and `infra/terraform/`.
- **Open Source mini-challenge**: `mcp-server/` is a standalone MIT-licensed package.

---

## License

MIT — see each package `LICENSE` and repository root `LICENSE`.