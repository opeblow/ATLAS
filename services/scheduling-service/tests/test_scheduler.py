"""Pure unit tests for the spaced-allocation planner (no services required)."""

from datetime import datetime, timedelta

from app.scheduler import (
    BLOCK_HOURS,
    estimate_hours,
    plan_study_week,
    select_non_overlapping,
)

WEEK = ["2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28", "2026-09-29", "2026-09-30"]


def _available(start: int = 18, end: int = 21) -> list[dict]:
    return [{"date": d, "start_hour": start, "end_hour": end} for d in WEEK]


def test_estimate_hours_scales_with_weight():
    assert estimate_hours(0) == 2.0
    assert estimate_hours(0) == 2.0
    assert estimate_hours(1.0) == 4.0
    assert estimate_hours(3.0) == 8.0


def test_plan_returns_blocks_before_deadline():
    blocks, conflicts = plan_study_week(
        [{"title": "A", "due_at": f"{WEEK[3]}T23:00:00", "weight": 2.0}],
        _available(),
    )
    assert not conflicts
    assert blocks and all(b["status"] == "proposed" for b in blocks)
    for b in blocks:
        assert datetime.fromisoformat(b["start_at"]) < datetime.fromisoformat(f"{WEEK[3]}T23:00:00")


def test_blocks_are_90_minutes():
    blocks, _ = plan_study_week(
        [{"title": "A", "due_at": f"{WEEK[3]}T23:00:00", "weight": 2.0}],
        _available(),
    )
    for b in blocks:
        start = datetime.fromisoformat(b["start_at"])
        end = datetime.fromisoformat(b["end_at"])
        assert (end - start).total_seconds() / 3600 == BLOCK_HOURS


def test_per_day_cap_respected():
    blocks, _ = plan_study_week(
        [{"title": "A", "due_at": f"{WEEK[6]}T23:00:00", "weight": 3.0}],  # 8h needed
        _available(),
        max_hours_per_day=2.0,
    )
    # sum per day must stay within the cap
    from collections import defaultdict

    per_day = defaultdict(float)
    for b in blocks:
        day = datetime.fromisoformat(b["start_at"]).date().isoformat()
        per_day[day] += 1.5
    assert all(hours <= 2.0001 for hours in per_day.values())


def test_work_spreads_evenly_not_crammed():
    blocks, _ = plan_study_week(
        [{"title": "A", "due_at": f"{WEEK[5]}T23:00:00", "weight": 2.0}],
        _available(),
    )
    days = {datetime.fromisoformat(b["start_at"]).date() for b in blocks}
    assert len(days) > 1, "heavy work should spread across multiple days"


def test_conflict_when_no_window_before_deadline():
    blocks, conflicts = plan_study_week(
        [{"title": "A", "due_at": f"{WEEK[0]}T10:00:00", "weight": 1.0}],  # before any 18:00 window
        _available(),
    )
    assert not blocks
    assert any("no available study windows" in c["reason"] for c in conflicts)


def test_availability_after_deadline_filtered():
    late: list[dict] = [{"date": d, "start_hour": 18, "end_hour": 21} for d in WEEK[3:]]
    blocks, conflicts = plan_study_week(
        [{"title": "A", "due_at": f"{WEEK[2]}T23:00:00", "weight": 1.0}],
        late + _available(),
    )
    for b in blocks:
        assert datetime.fromisoformat(b["start_at"]).date().isoformat() <= WEEK[2]


def test_deadline_order_preferred():
    blocks, _ = plan_study_week(
        [
            {"title": "later", "due_at": f"{WEEK[4]}T23:00:00", "weight": 1.0},
            {"title": "earlier", "due_at": f"{WEEK[1]}T23:00:00", "weight": 1.0},
        ],
        _available(),
    )
    # the earliest deadline is staffed first (title keeps its "Study: " prefix)
    first_titles = [b["title"] for b in blocks[:3]]
    assert any("earlier" in t for t in first_titles)


def test_commit_rejects_overlapping_proposals_in_same_request():
    proposals = [
        {
            "title": "first",
            "start_at": "2026-10-04T18:00:00+00:00",
            "end_at": "2026-10-04T19:30:00+00:00",
        },
        {
            "title": "overlap",
            "start_at": "2026-10-04T19:00:00+00:00",
            "end_at": "2026-10-04T20:00:00+00:00",
        },
        {
            "title": "adjacent",
            "start_at": "2026-10-04T19:30:00+00:00",
            "end_at": "2026-10-04T20:30:00+00:00",
        },
    ]

    accepted, conflicts = select_non_overlapping(proposals, [])

    assert [block["title"] for block in accepted] == ["first", "adjacent"]
    assert len(conflicts) == 1
    assert conflicts[0]["block"] == "overlap"
    assert conflicts[0]["overlaps"] == "first"


def test_multiple_deadlines_share_windows_without_exceeding_daily_cap():
    availability = [{"date": WEEK[0], "start_hour": 18, "end_hour": 23}]
    deadlines = [
        {"title": "First", "due_at": f"{WEEK[0]}T23:00:00", "weight": 0},
        {"title": "Second", "due_at": f"{WEEK[0]}T23:00:00", "weight": 0},
    ]

    blocks, conflicts = plan_study_week(
        deadlines, availability, max_hours_per_day=2.0
    )

    assert sum(
        (datetime.fromisoformat(block["end_at"]) -
         datetime.fromisoformat(block["start_at"])).total_seconds() / 3600
        for block in blocks
    ) <= 2.0
    assert len(blocks) == 2
    assert any(conflict["deadline"] == "Second" for conflict in conflicts)