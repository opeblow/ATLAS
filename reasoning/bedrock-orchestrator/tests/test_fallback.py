"""Unit tests for the offline intent router (no services required)."""

from orchestrator import fallback


def test_classify_affordability():
    assert fallback.classify("Can I afford a 120k laptop?") == "assess_affordability"
    assert fallback.classify("should I buy that camera") == "assess_affordability"


def test_classify_risk():
    assert fallback.classify("How is my financial risk today?") == "get_risk_snapshot"
    assert fallback.classify("what's my risk level") == "get_risk_snapshot"


def test_classify_spend():
    assert fallback.classify("I just spent 4500 on transport") == "log_transaction"
    assert fallback.classify("add expense of 2000") == "log_transaction"


def test_classify_plan_and_commit():
    assert fallback.classify("plan my week around my exams") == "plan_study_week"
    assert fallback.classify("commit it") == "commit_schedule"


def test_classify_brief():
    assert fallback.classify("Good morning") == "get_daily_brief"
    assert fallback.classify("daily brief please") == "get_daily_brief"


def test_amount_parsing():
    assert fallback._amount("120k laptop", 0) == 120_000
    assert fallback._amount("4000 ngn", 0) == 4_000
    assert fallback._amount("2 million home", 0) == 2_000_000
    assert fallback._amount("no numbers here", 7) == 7


def test_category_word_boundaries():
    # "rent" must not match inside "current"
    assert fallback._category("is the rent due") == "rent"
    assert fallback._category("food run") == "food"
    assert fallback._category("a new keyboard") == "general"


def test_draft_affordability():
    out = fallback._draft(
        "assess_affordability",
        {
            "verdict": "safe",
            "balance_ngn": 267000,
            "baseline_risk_score": 0.09,
            "risk_score": 0.16,
            "explanation": "reason",
        },
    )
    assert "safe" in out and "0.16" in out


def test_draft_risk_lists_factors():
    out = fallback._draft(
        "get_risk_snapshot",
        {"score": 0.4, "factors": [{"label": "income", "direction": "lowers risk"}]},
    )
    assert "income lowers risk" in out


def test_draft_commit_conflicts_counted():
    out = fallback._draft(
        "commit_schedule",
        {"committed": 8, "conflicts": [{"x": 1}, {"x": 2}]},
    )
    assert "8 study blocks" in out and "2 overlapped" in out