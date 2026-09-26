"""SQLAlchemy models mirroring the Section 6 data model.

Tables:
  users            one row per linked Alexa+ account
  transactions     append-only ledger (never mutated, only inserted)
  risk_snapshots   cached model outputs
  deadlines        source data for the scheduler
  schedule_blocks  committed calendar blocks (status: proposed/committed/completed)
  mcp_tool_calls   audit + observability log for every MCP invocation
  auth_tokens      short-lived bearer tokens issued per Alexa+ session
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from atlas_common.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    alexa_account_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    locale: Mapped[str] = mapped_column(String(16), default="en-NG")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount_ngn: Mapped[float] = mapped_column(Float)  # >0 income, <0 spend
    category: Mapped[str] = mapped_column(String(64), default="general")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=_now)
    source: Mapped[str] = mapped_column(String(16), default="alexa")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_transactions_idem"),
        Index("ix_transactions_user_ts", "user_id", "ts"),
    )


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[float] = mapped_column(Float)  # 0..1; higher = riskier
    factors: Mapped[list] = mapped_column(JSON, default=list)
    window: Mapped[str] = mapped_column(String(8), default="30d")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=_now)


class Deadline(Base):
    __tablename__ = "deadlines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)  # course weight -> scheduling priority


class ScheduleBlock(Base):
    __tablename__ = "schedule_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    deadline_id: Mapped[str | None] = mapped_column(ForeignKey("deadlines.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed/committed/completed
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_schedule_user_status", "user_id", "status"),
        Index("ix_schedule_user_time", "user_id", "start_at"),
    )


class McpToolCall(Base):
    """Audit + observability log for every MCP invocation (Section 8.6)."""

    __tablename__ = "mcp_tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(64), index=True)
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=_now)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)