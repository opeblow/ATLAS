"""Deadline -> study-week planner (Section 5: plan_study_week).

Greedy, *spaced* allocation: a deadline's estimated study hours are spread
evenly across the user's available windows that fall before the due date
(capped per day) instead of crammed onto the last day. Conflicts are reported
when availability can't cover the estimated effort.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

DEFAULT_MAX_HOURS_PER_DAY = 4.0
BLOCK_HOURS = 1.5  # 90-minute study blocks


def estimate_hours(weight: float) -> float:
    """Rough effort model: heavier courses need more hours."""
    return round(2.0 + max(0.0, weight) * 2.0, 1)


def _as_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _aware(dt: datetime) -> datetime:
    """Normalize to UTC-aware so naive/aware comparisons always work."""
    if dt.tzinfo is None:
        from datetime import timezone as _tz

        return dt.replace(tzinfo=_tz.utc)
    return dt


def _window_before(w: dict, deadline_dt: datetime) -> bool:
    try:
        day = datetime.fromisoformat(str(w["date"])).date()
    except ValueError:
        day = datetime.strptime(str(w["date"]), "%Y-%m-%d").date()
    return day <= deadline_dt.date()


def plan_study_week(
    deadlines: list[dict],
    availability: list[dict],
    max_hours_per_day: float = DEFAULT_MAX_HOURS_PER_DAY,
) -> tuple[list[dict], list[dict]]:
    """Return (proposed_blocks, conflicts).

    Input shapes:
      deadlines:    [{id?, title, due_at (ISO), weight}]
      availability: [{date (YYYY-MM-DD), start_hour (0-23), end_hour (0-23)}]

    Output block shape:
      {deadline_id?, title, start_at (ISO), end_at (ISO), status: "proposed"}
    """
    blocks: list[dict] = []
    conflicts: list[dict] = []

    ordered = sorted(
        deadlines,
        key=lambda d: (_as_dt(d["due_at"]), -float(d.get("weight", 1.0))),
    )

    for deadline in ordered:
        due_at = _as_dt(deadline["due_at"])
        needed = estimate_hours(float(deadline.get("weight", 1.0)))
        title = deadline.get("title", "Study")

        windows = [w for w in availability if _window_before(w, due_at)]
        windows = _to_hour_windows(windows, due_at)
        if not windows:
            conflicts.append(
                {
                    "deadline": title,
                    "reason": f"no available study windows before {due_at.date()}"
                }
            )
            continue

        # Even spread: per-day target, capped by both max_hours_per_day and the
        # window's own capacity. Work lands early-ish, not the night before.
        per_day = min(max_hours_per_day, needed / len(windows))
        remaining = needed
        assigned = 0.0
        for window in windows:
            if remaining <= 0:
                break
            take = min(per_day, remaining, window["hours"])
            if take <= 0:
                continue
            blocks.extend(
                _make_blocks(
                    deadline_id=deadline.get("id"),
                    title=f"Study: {title}",
                    start=window["start"],
                    take=take,
                )
            )
            remaining -= take
            assigned += take
            window["hours"] -= take

        if remaining > 1e-6:
            # Over-committed or no room -> report rather than silently cramming.
            conflicts.append(
                {
                    "deadline": title,
                    "reason": (
                        f"{title} needs ~{needed:.1f}h but only {assigned:.1f}h of study time "
                        f"fits before {due_at.date()}."
                    ),
                }
            )

    return blocks, conflicts


def commit_as_conflicts(proposed: list[dict], committed: list[dict]) -> list[dict]:
    """Overlap check between proposed and already-committed blocks."""
    conflicts = []
    for block in proposed:
        s = _aware(_as_dt(block["start_at"]))
        e = _aware(_as_dt(block["end_at"]))
        for c in committed:
            cs = _aware(_as_dt(c["start_at"]))
            ce = _aware(_as_dt(c["end_at"]))
            if s < ce and cs < e:
                conflicts.append(
                    {
                        "block": block.get("title", block.get("id")),
                        "overlaps": c.get("title", c.get("id")),
                        "overlap_start": max(s, cs).isoformat(),
                        "overlap_end": min(e, ce).isoformat(),
                    }
                )
    return conflicts


def _to_hour_windows(availability: list[dict], due_at: datetime) -> list[dict]:
    out = []
    for w in availability:
        try:
            day = datetime.fromisoformat(str(w["date"])).date()
        except ValueError:
            day = datetime.strptime(str(w["date"]), "%Y-%m-%d").date()
        start_h = float(w.get("start_hour", 9))
        end_h = float(w.get("end_hour", 18))
        tzinfo = due_at.tzinfo
        start = datetime.combine(day, datetime.min.time(), tzinfo=tzinfo) + timedelta(hours=start_h)
        end = start + timedelta(hours=max(0.0, end_h - start_h))
        if start >= due_at:
            continue
        out.append({"start": start, "hours": max(0.0, min(end_h - start_h, (due_at - start).total_seconds() / 3600.0))})
    return out


def _make_blocks(deadline_id, title, start: datetime, take: float) -> list[dict]:
    blocks = []
    cursor = start
    while take > 0:
        chunk = min(BLOCK_HOURS, take)
        blk = {
            "deadline_id": deadline_id,
            "title": title,
            "start_at": cursor.isoformat(),
            "end_at": (cursor + timedelta(hours=chunk)).isoformat(),
            "status": "proposed",
        }
        blocks.append(blk)
        cursor += timedelta(hours=chunk)
        take -= chunk
    return blocks