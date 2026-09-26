# atlas_common

Shared data layer for the ATLAS services — *one* source of truth for the
Section 6 data model across `finance-service`, `scheduling-service` and
`mcp-server`.

- `models.py` — SQLAlchemy models (`users`, `transactions`, `risk_snapshots`,
  `deadlines`, `schedule_blocks`, `mcp_tool_calls`, `auth_tokens`)
- `config.py` — env-driven settings (`ATLAS_DATABASE_URL`, `REDIS_URL`, service URLs)
- `db.py` — engine + session factory (SQLite dev default, Postgres in prod)
- `audit.py` — append-only `mcp_tool_calls` logging with latency capture
- `schema.sql` — authoritative Postgres/RDS DDL (partitioning-ready)

Install: `pip install -e services/common`