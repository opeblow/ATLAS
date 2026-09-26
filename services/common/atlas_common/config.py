from __future__ import annotations

import os


class Settings:
    """Environment-driven configuration.

    Defaults to a local SQLite dev database. Set DATABASE_URL to a Postgres
    DSN (e.g. postgresql://atlas:atlas@localhost:5432/atlas) for production-style
    deployments. The schema in schema.sql is the Postgres DDL; SQLAlchemy
    auto-creates an equivalent schema on first use for dev convenience.
    """

    db_url: str = os.getenv(
        "ATLAS_DATABASE_URL",
        os.getenv("DATABASE_URL", "sqlite:///./atlas.db"),
    )
    redis_url: str | None = os.getenv("REDIS_URL") or None
    echo_sql: bool = os.getenv("ATLAS_ECHO_SQL", "0") == "1"

    # Service ports / base URLs (used by the MCP server and dashboard).
    finance_url: str = os.getenv("ATLAS_FINANCE_URL", "http://127.0.0.1:8001")
    scheduling_url: str = os.getenv("ATLAS_SCHEDULING_URL", "http://127.0.0.1:8002")
    risk_model_url: str = os.getenv("ATLAS_RISK_MODEL_URL", "http://127.0.0.1:8000")

    # Bearer-token auth for the MCP surface. In dev, any token issued by
    # /auth/token passes; in production these are short-lived, per-session tokens.
    require_auth: bool = os.getenv("ATLAS_REQUIRE_AUTH", "1") == "1"


settings = Settings()