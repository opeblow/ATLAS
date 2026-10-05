"""Risk computation pipeline for economics (Section 7.1 + 7.3).

- build_aggregates()      : derive the model's input from the append-only ledger
                            (no raw transactions ever leave this service)
- compute_risk()          : call the risk model out-of-process with a circuit
                            breaker + cached/stale fallback (Section 8.5)
- snapshot_risk()         : persist risk_snapshots rows on schedule + on new
                            transactions
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from atlas_common.auth import current_bearer
from atlas_common.config import settings
from atlas_common.models import RiskSnapshot, Transaction

from app.cache import cache

RISK_CACHE_KEY = "risk:{user_id}:{window}"


class CircuitBreaker:
    """Sliding-window breaker: after `threshold` consecutive failures, open for
    `cooldown` seconds and serve nothing (caller falls back to cached value)."""

    def __init__(self, threshold: int = 3, cooldown: float = 30.0) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self.failures = 0
        self.opened_at: datetime | None = None

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        return datetime.now(timezone.utc) - self.opened_at < timedelta(seconds=self.cooldown)

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = datetime.now(timezone.utc)


breaker = CircuitBreaker()


def build_aggregates(
    db: Session, user_id: str, projected_amount_ngn: float | None = None
) -> dict:
    """Aggregate the ledger into the risk-model's input contract."""
    now = datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    def _sum_since(since: datetime, income: bool = False) -> float:
        q = (
            db.query(func.coalesce(func.sum(Transaction.amount_ngn), 0.0))
            .filter(Transaction.user_id == user_id, Transaction.ts >= since)
        )
        if income:
            q = q.filter(Transaction.amount_ngn > 0)
        else:
            q = q.filter(Transaction.amount_ngn < 0)
        return abs(float(q.scalar() or 0.0))

    def _balance() -> float:
        return float(
            db.query(func.coalesce(func.sum(Transaction.amount_ngn), 0.0))
            .filter(Transaction.user_id == user_id)
            .scalar()
            or 0.0
        )

    spend_7d = _sum_since(since_7d)
    spend_30d = _sum_since(since_30d)
    prev21_30 = _sum_since(since_30d) - spend_7d
    income_30d = _sum_since(since_30d, income=True)

    category_spend: dict[str, float] = {}
    for cat, total in (
        db.query(Transaction.category, func.sum(Transaction.amount_ngn))
        .filter(
            Transaction.user_id == user_id,
            Transaction.ts >= since_7d,
            Transaction.amount_ngn < 0,
        )
        .group_by(Transaction.category)
        .all()
    ):
        category_spend[cat] = abs(float(total))

    recur_cats = {"subscriptions", "streaming", "software", "rent"}
    recurring_sub_spend = sum(v for k, v in category_spend.items() if k in recur_cats)

    totals_by_day = (
        db.query(func.date(Transaction.ts), func.sum(Transaction.amount_ngn))
        .filter(Transaction.user_id == user_id, Transaction.ts >= since_7d)
        .group_by(func.date(Transaction.ts))
        .all()
    )
    signed = [float(t) for _, t in totals_by_day if t is not None]
    daily_std = _std(signed)

    txn_count_7d = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.user_id == user_id, Transaction.ts >= since_7d)
        .scalar()
        or 0
    )

    return {
        "balance_ngn": _balance(),
        "monthly_income_ngn": income_30d,
        "monthly_spend_ngn": spend_30d,
        "last7d_spend_ngn": spend_7d,
        "prev21d_spend_ngn": prev21_30,
        "recurring_sub_spend_ngn": recurring_sub_spend,
        "txn_count_7d": int(txn_count_7d),
        "category_spend": category_spend,
        "daily_spend_std_ngn": daily_std,
        "income_received_30d": income_30d > 0,
        "projected_amount_ngn": float(projected_amount_ngn or 0),
    }


def _std(values: list[float]) -> float:
    import statistics

    if len(values) < 2:
        return 0.0
    return statistics.pstdev(values)


def _call_risk_model(agg: dict) -> tuple[float, list[dict]]:
    token = current_bearer.get()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = httpx.post(
        f"{settings.risk_model_url}/score",
        json=agg,
        headers=headers,
        timeout=5.0,
    )
    r.raise_for_status()
    data = r.json()
    return float(data["score"]), data["factors"]


def compute_risk(
    db: Session,
    user_id: str,
    window: str = "30d",
    projected_amount_ngn: float | None = None,
    *,
    force: bool = False,
    stale_ok: bool = True,
    persist: bool = True,
) -> dict:
    """Return a risk assessment.

    Fresh path: aggregator -> model (with circuit breaker). Degraded path: most
    recent risk_snapshots row (with `stale: true`), so a slow/derailed model
    never fails the whole voice turn (Section 8.5).
    """
    if projected_amount_ngn is not None:
        key = f"risk_proj:{user_id}:{window}:{projected_amount_ngn:.2f}"
    else:
        key = RISK_CACHE_KEY.format(user_id=user_id, window=window)

    def _fresh() -> dict:
        agg = build_aggregates(db, user_id, projected_amount_ngn)
        score, factors = _call_risk_model(agg)
        result = {
            "score": round(float(score), 4),
            "factors": factors,
            "stale": False,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
        breaker.record_success()
        return result

    if not force:
        cached = cache.get(key)
        if cached is not None:
            return cached

    if breaker.is_open() and stale_ok:
        return _stale(db, user_id, window)

    try:
        result = _fresh()
        cache.set(key, result, ttl=30)
        if persist and projected_amount_ngn is None:
            _persist_snapshot(db, user_id, result, window)
        return result
    except Exception as exc:  # network / model transient failure
        breaker.record_failure()
        if stale_ok:
            stale = _stale(db, user_id, window)
            if stale:
                return stale
        raise RuntimeError(f"risk model unavailable and no cached value: {exc}") from exc


def _stale(db: Session, user_id: str, window: str) -> dict | None:
    snap = (
        db.query(RiskSnapshot)
        .filter(RiskSnapshot.user_id == user_id, RiskSnapshot.window == window)
        .order_by(RiskSnapshot.computed_at.desc())
        .first()
    )
    if snap is None:
        return None
    return {
        "score": float(snap.score),
        "factors": list(snap.factors or []),
        "stale": True,
        "computed_at": snap.computed_at.isoformat(),
    }


def _persist_snapshot(db: Session, user_id: str, result: dict, window: str) -> None:
    db.add(
        RiskSnapshot(
            user_id=user_id,
            score=result["score"],
            factors=result["factors"],
            window=window,
        )
    )
    db.commit()
    cache.delete(f"trend:{user_id}")


def risk_trend(db: Session, user_id: str, limit: int = 60) -> list[dict]:
    """Latest snapshots in ascending time order (dashboard Money chart)."""
    snaps = (
        db.query(RiskSnapshot)
        .filter(RiskSnapshot.user_id == user_id)
        .order_by(RiskSnapshot.computed_at.asc())
        .limit(limit)
        .all()
    )
    return [
        {"score": s.score, "computed_at": s.computed_at.isoformat(), "window": s.window}
        for s in snaps
    ]


def invalidate_hot_cache(user_id: str) -> None:
    cache.delete(f"balance:{user_id}")
    cache.delete(f"risk:{user_id}:30d")
    cache.delete(f"risk:{user_id}:7d")
    cache.delete(f"trend:{user_id}")