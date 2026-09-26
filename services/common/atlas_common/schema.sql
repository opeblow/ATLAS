-- ATLAS production schema (PostgreSQL / RDS).
-- The development services auto-create an equivalent schema via SQLAlchemy,
-- so this DDL is the authoritative production reference (Sections 6 & 8.3:
-- append-only tables designed for monthly partitioning + user_id-hash sharding).

CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- gen_random_uuid()

CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alexa_account_id TEXT NOT NULL UNIQUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    locale           TEXT NOT NULL DEFAULT 'en-NG'
);

-- Append-only ledger: never UPDATE, only INSERT. Partition by month.
CREATE TABLE transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    amount_ngn      DOUBLE PRECISION NOT NULL,   -- > 0 income, < 0 spend
    category        TEXT NOT NULL DEFAULT 'general',
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          TEXT NOT NULL DEFAULT 'alexa',
    idempotency_key TEXT,
    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX ix_transactions_user_ts ON transactions (user_id, ts);

CREATE TABLE risk_snapshots (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id),
    score       DOUBLE PRECISION NOT NULL,
    factors     JSONB NOT NULL DEFAULT '[]',
    window      TEXT NOT NULL DEFAULT '30d',
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_risk_snapshots_user ON risk_snapshots (user_id, computed_at);

CREATE TABLE deadlines (
    id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    title   TEXT NOT NULL,
    due_at  TIMESTAMPTZ NOT NULL,
    weight  DOUBLE PRECISION NOT NULL DEFAULT 1.0
);
CREATE INDEX ix_deadlines_user ON deadlines (user_id, due_at);

CREATE TABLE schedule_blocks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    deadline_id     UUID REFERENCES deadlines(id),
    title           TEXT NOT NULL,
    start_at        TIMESTAMPTZ NOT NULL,
    end_at          TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL DEFAULT 'proposed', -- proposed/committed/completed
    idempotency_key TEXT
);
CREATE INDEX ix_schedule_user_status ON schedule_blocks (user_id, status);
CREATE INDEX ix_schedule_user_time   ON schedule_blocks (user_id, start_at);

-- Audit + observability log: append-only, partition by month. Doubles as
-- the security log for anomaly detection (Section 9).
CREATE TABLE mcp_tool_calls (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id),
    tool_name   TEXT NOT NULL,
    input       JSONB,
    output      JSONB,
    latency_ms  INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_mcp_tool_calls_user ON mcp_tool_calls (user_id, ts);
CREATE INDEX ix_mcp_tool_calls_tool ON mcp_tool_calls (tool_name);

CREATE TABLE auth_tokens (
    token      TEXT PRIMARY KEY,
    user_id    UUID NOT NULL REFERENCES users(id),
    issued_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_auth_tokens_user ON auth_tokens (user_id);

-- Partitioned append-only variants (scale target, Section 8.3). Enable when a
-- single instance's write volume becomes the bottleneck.
--
--   CREATE TABLE transactions_m Y_2026 PARTITION OF transactions
--     FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
--
-- Sharding by user_id hash is a mechanical next step given the append-only
-- design (create_hash_partitions('transactions', 16)).