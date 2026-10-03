"""ATLAS finance service (Section 5, 6).

Append-only ledger + affordability checks + explainable risk snapshots,
reading/writing the shared Postgres/SQLite schema via atlas_common.

Routes:
  POST   /users/{user_id}                      ensure user exists
  GET    /users/{user_id}/balance              hot cached balance
  GET    /users/{user_id}/transactions         ledger page
  POST   /transactions                         log a spend/income (idempotent)
  POST   /assess/affordability                 can-I-afford-this verdict
  GET    /users/{user_id}/risk                 risk snapshot + top_factors[]
  GET    /users/{user_id}/risk/trend           snapshot history (dashboard chart)
GET    /users/{user_id}/brief                finance half of the daily brief
    POST   /auth/token                           issue a scoped bearer token (dev)
    GET    /audit/tool_calls                     recent MCP/orchestrator call log (dashboard)
    POST   /demo/seed                            seed demo data for the dashboard
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from atlas_common.config import settings
from atlas_common.db import get_session, init_db
from atlas_common.models import AuthToken, McpToolCall, Transaction, User

from app import risk as riskmod
from app.cache import cache

app = FastAPI(title="ATLAS Finance Service", version="0.1.0")
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "finance"}


# ---------------------------------------------------------------- schemas
class UserIdIn(BaseModel):
    user_id: str


class TransactionIn(BaseModel):
    user_id: str
    amount_ngn: float
    category: str = "general"
    ts: datetime | None = None
    source: str = "alexa"
    idempotency_key: str | None = None


class AffordabilityIn(BaseModel):
    user_id: str
    amount_ngn: float = Field(gt=0)
    category: str = "general"


class TokenIn(BaseModel):
    user_id: str
    ttl_seconds: int = 3600


# ---------------------------------------------------------------- helpers
def _ensure_user(db: Session, user_id: str, locale: str = "en-NG") -> User:
    user = db.get(User, user_id)
    if user is None:
        user = User(id=user_id, alexa_account_id=f"alexa::{user_id}", locale=locale)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _balance_of(db: Session, user_id: str) -> float:
    return float(
        db.query(func.coalesce(func.sum(Transaction.amount_ngn), 0.0))
        .filter(Transaction.user_id == user_id)
        .scalar()
        or 0.0
    )


# ---------------------------------------------------------------- users
@app.post("/users/{user_id}")
def ensure_user(user_id: str, db: Session = Depends(get_session)) -> dict:
    user = _ensure_user(db, user_id)
    return {"user_id": user.id, "locale": user.locale, "created_at": user.created_at.isoformat()}


@app.get("/users/{user_id}/balance")
def get_balance(user_id: str, db: Session = Depends(get_session)) -> dict:
    _ensure_user(db, user_id)
    balance = cache.get_or_set(f"balance:{user_id}", lambda: _balance_of(db, user_id), ttl=15)
    return {"user_id": user_id, "balance_ngn": round(float(balance), 2)}


@app.get("/users/{user_id}/transactions")
def list_transactions(
    user_id: str,
    db: Session = Depends(get_session),
    limit: int = Query(100, le=1000),
    offset: int = 0,
) -> dict:
    _ensure_user(db, user_id)
    rows = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.ts.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "user_id": user_id,
        "transactions": [
            {
                "id": t.id,
                "amount_ngn": t.amount_ngn,
                "category": t.category,
                "ts": t.ts.isoformat(),
                "source": t.source,
            }
            for t in rows
        ],
    }


# ---------------------------------------------------------------- ledger
@app.post("/transactions")
def log_transaction(inp: TransactionIn, db: Session = Depends(get_session)) -> dict:
    """Append-only write. Idempotent via (user_id, idempotency_key)."""
    _ensure_user(db, inp.user_id)

    if inp.idempotency_key:
        existing = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == inp.user_id,
                Transaction.idempotency_key == inp.idempotency_key,
            )
            .first()
        )
        if existing is not None:
            return {
                "transaction": _tx(out:= existing),
                "new_balance": _balance_of(db, inp.user_id),
                "updated_risk_score": riskmod.compute_risk(db, inp.user_id)["score"],
                "duplicate": True,
            }
    if inp.amount_ngn == 0:
        raise HTTPException(status_code=422, detail="amount_ngn must be non-zero")

    tx = Transaction(
        user_id=inp.user_id,
        amount_ngn=inp.amount_ngn,
        category=inp.category,
        ts=inp.ts or datetime.now(timezone.utc),
        source=inp.source,
        idempotency_key=inp.idempotency_key,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    riskmod.invalidate_hot_cache(inp.user_id)
    score = riskmod.compute_risk(db, inp.user_id)["score"]

    return {
        "transaction": _tx(tx),
        "new_balance": _balance_of(db, inp.user_id),
        "updated_risk_score": round(float(score), 4),
        "duplicate": False,
    }


def _tx(t: Transaction) -> dict:
    return {
        "id": t.id,
        "amount_ngn": t.amount_ngn,
        "category": t.category,
        "ts": t.ts.isoformat(),
        "source": t.source,
    }


# ---------------------------------------------------------------- affordability
@app.post("/assess/affordability")
def assess_affordability(inp: AffordabilityIn, db: Session = Depends(get_session)) -> dict:
    _ensure_user(db, inp.user_id)
    balance = _balance_of(db, inp.user_id)

    baseline = riskmod.compute_risk(db, inp.user_id)["score"]
    projected = riskmod.compute_risk(
        db, inp.user_id, projected_amount_ngn=inp.amount_ngn, force=True, persist=False
    )["score"]

    buffer_needed = inp.amount_ngn * 0.10  # 10% safety buffer
    can_cover = (balance - inp.amount_ngn - buffer_needed) >= 0

    # Verdict policy on projected 0..1 risk
    if projected > 0.85:
        verdict = "blocked"
        reason = "this purchase would push your financial risk into a danger zone."
    elif projected > 0.6 or not can_cover:
        verdict = "risky"
        reason = "affordable on paper but risky given your spending pattern."
    else:
        verdict = "safe"
        reason = "this purchase fits comfortably within your current balance and pattern."

    explanation = _phrase(inp.amount_ngn, inp.category, balance, verdict, reason, projected, baseline)

    return {
        "verdict": verdict,
        "risk_score": round(float(projected), 4),
        "baseline_risk_score": round(float(baseline), 4),
        "balance_ngn": round(balance, 2),
        "explanation": explanation,
        "stale": False,
    }


def _phrase(amount, category, balance, verdict, reason, projected, baseline):
    direction = "rises" if projected > baseline else "stays roughly flat"
    can_cover = (balance - amount - amount * 0.10) >= 0
    if not can_cover:
        shortfall = amount * 1.10 - balance
        gap = f" You would be {shortfall:,.0f} NGN short after a 10% buffer."
    else:
        gap = f" You have enough for this and about {balance - amount * 1.10:,.0f} NGN left over."
    return (
        f"Spending {amount:,.0f} NGN on {category} — {reason}{gap} "
        f"Your risk score {direction} ({baseline:.2f} -> {projected:.2f})."
    )


# ---------------------------------------------------------------- risk
@app.get("/users/{user_id}/risk")
def get_risk(
    user_id: str,
    db: Session = Depends(get_session),
    window: str = Query("30d", pattern="^(7d|30d)$"),
) -> dict:
    _ensure_user(db, user_id)
    result = riskmod.compute_risk(db, user_id, window=window)
    trend = _window_trend(db, user_id, limit=7)
    return {**result, "user_id": user_id, "window": window, "trend": trend}


@app.get("/users/{user_id}/risk/trend")
def get_risk_trend(user_id: str, db: Session = Depends(get_session)) -> dict:
    _ensure_user(db, user_id)
    return {"user_id": user_id, "points": riskmod.risk_trend(db, user_id)}


def _window_trend(db: Session, user_id: str, limit: int = 7) -> list[dict]:
    snaps = riskmod.risk_trend(db, user_id, limit=limit)
    return [{"score": p["score"], "computed_at": p["computed_at"]} for p in snaps]


# ---------------------------------------------------------------- audit log
@app.get("/audit/tool_calls")
def list_tool_calls(
    db: Session = Depends(get_session),
    limit: int = Query(50, ge=1, le=500),
    user_id: str | None = None,
) -> dict:
    """Recent agent-tool activity — powers the dashboard's Agent Log screen."""
    q = db.query(McpToolCall).order_by(McpToolCall.id.desc())
    if user_id:
        q = q.filter(McpToolCall.user_id == user_id)
    rows = q.limit(limit).all()
    return {
        "rows": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "tool_name": r.tool_name,
                "input": r.input,
                "output": r.output,
                "error": r.error,
                "latency_ms": r.latency_ms,
                "created_at": r.ts.isoformat() if r.ts else None,
            }
            for r in rows
        ]
    }


# ---------------------------------------------------------------- brief
@app.get("/users/{user_id}/brief")
def get_finance_brief(user_id: str, db: Session = Depends(get_session)) -> dict:
    _ensure_user(db, user_id)
    balance = _balance_of(db, user_id)
    risk = riskmod.compute_risk(db, user_id)
    spend_7d = abs(
        float(
            db.query(func.coalesce(func.sum(Transaction.amount_ngn), 0.0))
            .filter(
                Transaction.user_id == user_id,
                Transaction.ts >= datetime.now(timezone.utc) - timedelta(days=7),
                Transaction.amount_ngn < 0,
            )
            .scalar()
            or 0.0
        )
    )
    return {
        "user_id": user_id,
        "balance_ngn": round(balance, 2),
        "risk_score": risk["score"],
        "top_factors": risk["factors"],
        "spend_7d_ngn": round(spend_7d, 2),
        "stale": risk["stale"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------- auth (dev)
@app.post("/auth/token")
def issue_token(inp: TokenIn, db: Session = Depends(get_session)) -> dict:
    _ensure_user(db, inp.user_id)
    token = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            token=token,
            user_id=inp.user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=inp.ttl_seconds),
        )
    )
    db.commit()
    return {
        "token": token,
        "user_id": inp.user_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=inp.ttl_seconds)).isoformat(),
    }


# ---------------------------------------------------------------- demo seed
@app.post("/demo/seed")
def demo_seed(db: Session = Depends(get_session)) -> dict:
    """Idempotent-ish demo dataset: one user, three weeks of history + snapshots."""
    user_id = "u_demo"
    _ensure_user(db, user_id)

    if db.query(Transaction).filter(Transaction.user_id == user_id).count() == 0:
        now = datetime.now(timezone.utc)
        plan = [
            (400_000, "opening_balance", 25),
            (150_000, "salary", 20),
            (-45_000, "food", 1),
            (-25_000, "transport", 1),
            (-12_000, "subscriptions", 3),
            (-85_000, "rent", 14),
            (-30_000, "shopping", 5),
            (-18_000, "entertainment", 4),
            (-8_000, "food", 2),
            (-60_000, "school_fees", 9),
        ]
        for hour_offset, (amount, cat, days_ago) in enumerate(plan, start=1):
            ts = now - timedelta(days=days_ago, hours=hour_offset % 11)
            db.add(
                Transaction(
                    user_id=user_id,
                    amount_ngn=amount,
                    category=cat,
                    ts=ts,
                    source="seed",
                    idempotency_key=f"seed:{amount}:{cat}:{days_ago}",
                )
            )
        db.commit()

    snapshot = riskmod.compute_risk(db, user_id, force=True)
    return {
        "user_id": user_id,
        "balance_ngn": _balance_of(db, user_id),
        "risk_score": snapshot["score"],
        "factors": snapshot["factors"][:4],
        "note": "Demo user seeded. Try /users/u_demo/brief",
    }