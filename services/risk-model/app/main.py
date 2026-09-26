"""ATLAS risk-model microservice — FastAPI + PyTorch, exposed via POST /score.

Out-of-process inference: the MCP server never loads PyTorch; it talks to the
finance service, which calls this service. Circuit breakers + cached fallbacks
are the responsibility of the calling services (Section 8.5).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.features import compute_features, generate_aggregate_from_seed
from app.model import get_model

app = FastAPI(title="ATLAS Risk Model", version="0.1.0")


class ScoreRequest(BaseModel):
    balance_ngn: float = 0
    monthly_income_ngn: float = 0
    monthly_spend_ngn: float = 0
    last7d_spend_ngn: float = 0
    prev21d_spend_ngn: float = 0
    recurring_sub_spend_ngn: float = 0
    txn_count_7d: int = 0
    category_spend: dict[str, float] = {}
    daily_spend_std_ngn: float = 0
    income_received_30d: bool = True
    projected_amount_ngn: float | None = None


class ScoreResponse(BaseModel):
    score: float
    factors: list[dict]
    version: str = "risk-mlp-0.1"


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    try:
        model = get_model()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    agg = req.model_dump()
    features = compute_features(agg)
    s, factors = model.score_with_factors(features)
    return ScoreResponse(score=round(float(s), 4), factors=factors)


@app.get("/score/demo")
def demo_score() -> ScoreResponse:
    """Score a default (synthetic) aggregate — handy for smoke tests."""
    features = compute_features(generate_aggregate_from_seed({}))
    s, factors = get_model().score_with_factors(features)
    return ScoreResponse(score=round(float(s), 4), factors=factors)