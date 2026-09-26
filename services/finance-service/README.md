# ATLAS finance service

Append-only ledger + affordability checks + explainable risk snapshots.

| Route | Purpose |
|---|---|
| `POST /demo/seed` | seed demo user (`u_demo`) with history |
| `POST /users/{user_id}` | ensure user |
| `GET /users/{user_id}/balance` | hot cached balance (Redis stand-in by default) |
| `GET /users/{user_id}/transactions` | ledger page |
| `POST /transactions` | **log_transaction** — append-only, idempotent (recomputes risk) |
| `POST /assess/affordability` | **assess_affordability** — verdict + projected risk + explanation |
| `GET /users/{user_id}/risk?window=30d` | **get_risk_snapshot** — score, trend, `top_factors[]` |
| `GET /users/{user_id}/risk/trend` | snapshot history for the Money chart |
| `GET /users/{user_id}/brief` | finance half of the daily brief |
| `POST /auth/token` | issue a short-lived scoped bearer token (dev auth) |

**Design notes**
- Never mutates `transactions` — insert-only, ready for monthly partitioning +
  sharding (Section 8.3).
- Computes aggregates from the ledger and posts **only aggregates** to the risk
  model; raw transactions never leave this service (Sections 7.3, 9).
- Circuit breaker around the risk-model call with stale-snapshot fallback
  (Section 8.5). Hot reads cached server-side (Section 8.2).
- Affordability checks are **observed, not replayed**: `POST /assess/affordability`
  never writes, `POST /transactions` is the only writer, keyed by idempotency.

```bash
pip install -e .
uvicorn app.main:app --port 8001
```