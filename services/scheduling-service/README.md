# ATLAS scheduling service

Deadlines → proposed/committed calendar blocks, with strict overlap checks and
idempotent commits.

| Route | Purpose |
|---|---|
| `POST /deadlines` | upsert a deadline |
| `GET /users/{user_id}/deadlines` | list deadlines |
| `POST /plan/week` | **plan_study_week** — propose spaced study blocks + conflicts |
| `POST /schedule/commit` | **commit_schedule** — append committed blocks (idempotent, overlap-checked) |
| `GET /users/{user_id}/schedule?status=` | committed/proposed/completed blocks |
| `PATCH /schedule/block/{id}` | adjust a block (drag-to-adjust / mark completed) |
| `GET /users/{user_id}/brief/{date}` | time half of the daily brief |
| `POST /demo/seed` | seed demo deadlines + committed blocks for `u_demo` |

**Design notes**
- The planner is greedy + *spaced*: estimated effort per deadline
  (`2 + 2·weight` hours) is spread evenly over available windows before the due
  date, capped at 4h/day, instead of cramming the night before.
- Overlapping blocks are **never** written; they're reported as conflicts
  (Section 5: `conflicts[]`).
- `commit_schedule` is idempotent via `idempotency_key` — voice retries and
  network blips never double-book a slot (Section 8.5).

```bash
pip install -e .
uvicorn app.main:app --port 8002
```