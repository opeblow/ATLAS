from __future__ import annotations

import os


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> list[str]:
    return [p.strip() for p in os.getenv(name, default).split(",") if p.strip()]


class Settings:
    """Environment-driven configuration.

    Defaults to a local SQLite dev database. Set ATLAS_DATABASE_URL to a Postgres
    DSN (e.g. postgresql://atlas:atlas@localhost:5432/atlas) for production-style
    deployments. The schema in schema.sql is the Postgres DDL; SQLAlchemy
    auto-creates an equivalent schema on first use for dev convenience.
    """

    db_url: str = os.getenv(
        "ATLAS_DATABASE_URL",
        os.getenv("DATABASE_URL", "sqlite:///./atlas.db"),
    )
    redis_url: str | None = os.getenv("REDIS_URL") or None
    echo_sql: bool = _flag("ATLAS_ECHO_SQL", "0")

    # Service ports / base URLs (used by the MCP server and dashboard).
    finance_url: str = os.getenv("ATLAS_FINANCE_URL", "http://127.0.0.1:8001")
    scheduling_url: str = os.getenv("ATLAS_SCHEDULING_URL", "http://127.0.0.1:8002")
    risk_model_url: str = os.getenv("ATLAS_RISK_MODEL_URL", "http://127.0.0.1:8000")

    # Bearer-token auth for the MCP surface. In dev, any token issued by
    # /auth/token passes; in production these are short-lived, per-session tokens.
    require_auth: bool = _flag("ATLAS_REQUIRE_AUTH", "1")

    # Browser origins allowed to call the REST services. The dashboard is
    # client-side, so a deployed build is cross-origin and CORS must be explicit.
    cors_origins: list[str] = _csv(
        "ATLAS_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )

    # Seed u_demo on boot so a cold deploy is never an empty dashboard.
    seed_on_start: bool = _flag("ATLAS_SEED_ON_START", "0")

    # Force the orchestrator onto the local rule-based router even when AWS
    # credentials happen to be present. Used for keyless demo deployments.
    mock_bedrock: bool = _flag("ATLAS_MOCK_BEDROCK", "1")

    @property
    def is_sqlite(self) -> bool:
        return self.db_url.startswith("sqlite")


settings = Settings()