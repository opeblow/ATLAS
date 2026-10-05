"""ATLAS scheduling service (Section 5, 6).

Deadlines -> proposed/committed calendar blocks with strict overlap checks and
idempotent commits (voice retries never double-book a slot, Section 8.5).

Routes:
  POST   /deadlines                       upsert the user's deadlines
  GET    /users/{user_id}/deadlines
  POST   /plan/week                       propose a study week (plan_study_week)
  POST   /schedule/commit                 persist committed blocks (idempotent)
  GET    /users/{user_id}/schedule        blocks by status
  PATCH  /schedule/block/{block_id}       adjust a block (drag-to-adjust / completed)
  GET    /users/{user_id}/brief/{date}    time half of the daily brief
  POST   /demo/seed                       seed demo deadlines + blocks
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from atlas_common.config import settings
from atlas_common.auth import authenticated_user, require_user_id
from atlas_common.db import get_session, init_db
from atlas_common.models import Deadline, ScheduleBlock, User

from app.scheduler import _aware, plan_study_week, select_non_overlapping

app = FastAPI(title="ATLAS Scheduling Service", version="0.1.0")
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "scheduling"}


class DeadlineIn(BaseModel):
    id: str | None = None
    user_id: str
    title: str
    due_at: datetime
    weight: float = 1.0


class PlanDeadlineIn(BaseModel):
    id: str | None = None
    title: str
    due_at: datetime
    weight: float = 1.0


class PlanWeekIn(BaseModel):
    user_id: str
    deadlines: list[PlanDeadlineIn]
    available_hours: list[dict]


class BlockIn(BaseModel):
    id: str | None = None
    deadline_id: str | None = None
    title: str
    start_at: datetime
    end_at: datetime
    status: str = "proposed"


class CommitIn(BaseModel):
    user_id: str
    blocks: list[BlockIn]
    idempotency_key: str | None = None


def _ensure_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        user = User(id=user_id, alexa_account_id=f"alexa::{user_id}")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _block_json(b: ScheduleBlock) -> dict:
    return {
        "id": b.id,
        "deadline_id": b.deadline_id,
        "title": b.title,
        "start_at": b.start_at.isoformat(),
        "end_at": b.end_at.isoformat(),
        "status": b.status,
    }


# ---------------------------------------------------------------- deadlines
@app.post("/deadlines")
def upsert_deadlines(
    inp: DeadlineIn,
    db: Session = Depends(get_session),
    auth_user_id: str = Depends(authenticated_user),
) -> dict:
    require_user_id(inp.user_id, auth_user_id)
    _ensure_user(db, inp.user_id)
    if inp.id:
        deadline = db.get(Deadline, inp.id)
        if deadline and deadline.user_id != inp.user_id:
            raise HTTPException(status_code=403, detail="not your deadline")
    else:
        deadline = Deadline(user_id=inp.user_id)
    deadline.title = inp.title
    deadline.due_at = inp.due_at
    deadline.weight = inp.weight
    db.add(deadline)
    db.commit()
    db.refresh(deadline)
    return {"id": deadline.id, "title": deadline.title, "due_at": deadline.due_at.isoformat()}


@app.get("/users/{user_id}/deadlines")
def list_deadlines(
    user_id: str,
    db: Session = Depends(get_session),
    auth_user_id: str = Depends(authenticated_user),
) -> dict:
    require_user_id(user_id, auth_user_id)
    _ensure_user(db, user_id)
    rows = (
        db.query(Deadline)
        .filter(Deadline.user_id == user_id)
        .order_by(Deadline.due_at.asc())
        .all()
    )
    return {
        "user_id": user_id,
        "deadlines": [
            {"id": d.id, "title": d.title, "due_at": d.due_at.isoformat(), "weight": d.weight}
            for d in rows
        ],
    }


# ---------------------------------------------------------------- plan
@app.post("/plan/week")
def plan_week(
    inp: PlanWeekIn,
    db: Session = Depends(get_session),
    auth_user_id: str = Depends(authenticated_user),
) -> dict:
    require_user_id(inp.user_id, auth_user_id)
    _ensure_user(db, inp.user_id)
    deadlines = [d.model_dump() for d in inp.deadlines]
    blocks, conflicts = plan_study_week(deadlines, inp.available_hours)
    return {"user_id": inp.user_id, "proposed_blocks": blocks, "conflicts": conflicts}


# ---------------------------------------------------------------- commit
@app.post("/schedule/commit")
def commit_schedule(
    inp: CommitIn,
    db: Session = Depends(get_session),
    auth_user_id: str = Depends(authenticated_user),
) -> dict:
    require_user_id(inp.user_id, auth_user_id)
    _ensure_user(db, inp.user_id)

    if inp.idempotency_key:
        prior = (
            db.query(ScheduleBlock)
            .filter(
                ScheduleBlock.user_id == inp.user_id,
                ScheduleBlock.idempotency_key == inp.idempotency_key,
            )
            .all()
        )
        if prior:
            return {
                "confirmation": "already-committed",
                "blocks": [_block_json(b) for b in prior],
                "calendar_diff": {"added": 0, "skipped_conflicts": 0},
                "duplicate": True,
            }
    if not inp.blocks:
        raise HTTPException(status_code=422, detail="no blocks to commit")

    committed = (
        db.query(ScheduleBlock)
        .filter(
            ScheduleBlock.user_id == inp.user_id,
            ScheduleBlock.status == "committed",
        )
        .all()
    )
    proposed = [block.model_dump() for block in inp.blocks]
    for block in proposed:
        if block["end_at"] <= block["start_at"]:
            raise HTTPException(status_code=422, detail="end_at must be after start_at")

    accepted, conflicts = select_non_overlapping(
        proposed, [_block_json(block) for block in committed]
    )
    added = 0
    saved: list[ScheduleBlock] = []
    for block in accepted:
        bs, be = _aware(block["start_at"]), _aware(block["end_at"])
        row = ScheduleBlock(
            id=(block["id"] or str(uuid.uuid4())),
            user_id=inp.user_id,
            deadline_id=block["deadline_id"],
            title=block["title"],
            start_at=bs,
            end_at=be,
            status="committed",
            idempotency_key=inp.idempotency_key,
        )
        db.add(row)
        saved.append(row)
        added += 1
    db.commit()

    # calendar_diff: newly committed count vs. what was previously committed today.
    prev_count = len(committed)
    return {
        "confirmation": "committed" if added else "nothing-committed",
        "blocks": [_block_json(b) for b in saved],
        "conflicts": conflicts,
        "calendar_diff": {
            "added": added,
            "previous_committed": prev_count,
            "skipped_conflicts": len(conflicts),
        },
        "duplicate": False,
    }


# ---------------------------------------------------------------- read / adjust
@app.get("/users/{user_id}/schedule")
def list_schedule(
    user_id: str,
    db: Session = Depends(get_session),
    status: str = Query("committed", pattern="^(proposed|committed|completed)$"),
    auth_user_id: str = Depends(authenticated_user),
) -> dict:
    require_user_id(user_id, auth_user_id)
    _ensure_user(db, user_id)
    rows = (
        db.query(ScheduleBlock)
        .filter(ScheduleBlock.user_id == user_id, ScheduleBlock.status == status)
        .order_by(ScheduleBlock.start_at.asc())
        .all()
    )
    return {"user_id": user_id, "blocks": [_block_json(b) for b in rows]}


@app.patch("/schedule/block/{block_id}")
def patch_block(
    block_id: str,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    status: str | None = None,
    db: Session = Depends(get_session),
    auth_user_id: str = Depends(authenticated_user),
) -> dict:
    block = db.get(ScheduleBlock, block_id)
    if block is None or block.user_id != auth_user_id:
        raise HTTPException(status_code=404, detail="block not found")
    if start_at is not None:
        block.start_at = start_at
    if end_at is not None:
        block.end_at = end_at
    if status is not None:
        if status not in {"proposed", "committed", "completed"}:
            raise HTTPException(status_code=422, detail="invalid block status")
        block.status = status
    if _aware(block.end_at) <= _aware(block.start_at):
        raise HTTPException(status_code=422, detail="end_at must be after start_at")
    db.commit()
    db.refresh(block)
    return _block_json(block)


# ---------------------------------------------------------------- brief
@app.get("/users/{user_id}/brief/{date}")
def get_time_brief(
    user_id: str,
    date: str,
    db: Session = Depends(get_session),
    auth_user_id: str = Depends(authenticated_user),
) -> dict:
    require_user_id(user_id, auth_user_id)
    _ensure_user(db, user_id)
    try:
        day = datetime.fromisoformat(date).date()
    except ValueError:
        day = datetime.strptime(date, "%Y-%m-%d").date()

    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    today_blocks = (
        db.query(ScheduleBlock)
        .filter(
            ScheduleBlock.user_id == user_id,
            and_(ScheduleBlock.start_at < end, ScheduleBlock.end_at > start),
        )
        .order_by(ScheduleBlock.start_at.asc())
        .all()
    )
    next_deadlines = (
        db.query(Deadline)
        .filter(
            Deadline.user_id == user_id,
            Deadline.due_at < start + timedelta(days=14),
        )
        .order_by(Deadline.due_at.asc())
        .limit(5)
        .all()
    )
    return {
        "user_id": user_id,
        "date": day.isoformat(),
        "today_blocks": [_block_json(b) for b in today_blocks if _aware(b.end_at) >= start],
        "next_deadlines": [
            {"id": d.id, "title": d.title, "due_at": d.due_at.isoformat(), "weight": d.weight}
            for d in next_deadlines
        ],
    }


# ---------------------------------------------------------------- demo seed
@app.post("/demo/seed")
def demo_seed(db: Session = Depends(get_session)) -> dict:
    if settings.auth_mode != "dev":
        raise HTTPException(status_code=404, detail="Not found")
    user_id = "u_demo"
    _ensure_user(db, user_id)
    now = datetime.now(timezone.utc)

    if db.query(Deadline).filter(Deadline.user_id == user_id).count() == 0:
        for i, (title, days_ahead, weight) in enumerate(
            [
                ("Physics Midterm", 4, 2.0),
                ("Compiler Design Assignment", 6, 1.5),
                ("Final Project Draft", 12, 2.5),
                ("Algorithms Problem Set", 3, 1.0),
            ]
        ):
            db.add(
                Deadline(
                    user_id=user_id,
                    title=title,
                    due_at=now + timedelta(days=days_ahead, hours=i),
                    weight=weight,
                )
            )
        db.commit()

    if (
        db.query(ScheduleBlock)
        .filter(ScheduleBlock.user_id == user_id, ScheduleBlock.status == "committed")
        .count()
        == 0
    ):
        today = now.date()
        for d in range(2):
            day = today + timedelta(days=d)
            for h, title in [(9, "Deep work: Physics"), (14, "Deep work: Algorithms")]:
                s = datetime.combine(day, time(h, 0), tzinfo=timezone.utc)
                db.add(
                    ScheduleBlock(
                        user_id=user_id,
                        title=title,
                        start_at=s,
                        end_at=s + timedelta(hours=1.5),
                        status="committed",
                    )
                )
        db.commit()

    return {
        "user_id": user_id,
        "deadlines": 4,
        "committed_blocks": 4,
        "note": "Try POST /plan/week with available_hours, then POST /schedule/commit",
    }