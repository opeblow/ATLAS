# ATLAS risk model (FastAPI + PyTorch)

Out-of-process inference service for the finance domain (Section 7.1).

- `POST /score` — compute risk score (0..1) + `factors[]` over the 12 engineered features
- `GET /score/demo` — score a synthetic default aggregate
- `python -m app.train` — train the MLP (writes `app/artifacts/risk_mlp.pt` + `scaler.json`)
- `python -m app.model` — smoke-test inference + explainability

The model is **genuine**: an MLP trained with Adam on a principled synthetic
dataset whose target is a nonlinear function of balance coverage, spend trend,
subscription load, overdraft proximity, utilization and income stability.
Explainability is gradient-based attribution — `impact_i = x̂_i · ∂score/∂x̂_i`.

The MCP server never loads this model. It is reached via
`finance-service → risk-model`.

```bash
pip install -e .
python -m app.train
uvicorn app.main:app --port 8000
curl -X POST http://127.0.0.1:8000/score \
  -H 'Content-Type: application/json' \
  -d '{"balance_ngn":250000,"monthly_income_ngn":400000,"monthly_spend_ngn":320000,
       "last7d_spend_ngn":90000,"prev21d_spend_ngn":210000,"recurring_sub_spend_ngn":28000,
       "txn_count_7d":18,"daily_spend_std_ngn":6000,"projected_amount_ngn":45000}'
```