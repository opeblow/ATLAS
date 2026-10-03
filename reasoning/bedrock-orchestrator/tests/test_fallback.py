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
    assert fallback._category("check my current account") == "general"


def test_category_synonyms():
    # Words that imply a category without naming it, so they don't fall through
    # to "general".
    assert fallback._category("spent 4500 on groceries") == "food"
    assert fallback._category("bought a new laptop for 850k") == "electronics"
    assert fallback._category("uber to campus 3000") == "transport"


def test_amount_falls_back_to_bare_number():
    # A bare figure used to be ignored, silently logging the placeholder default.
    assert fallback._amount("spent 4500 on groceries", 99) == 4_500
    assert fallback._amount("no numbers here", 7) == 7


def test_log_transaction_sign_follows_words():
    args = fallback._ARGS["log_transaction"]
    assert args("log that I spent 4500 on groceries", "u_demo")["amount_ngn"] == -4_500
    assert args("I got paid 200k salary", "u_demo")["amount_ngn"] == 200_000


def test_plan_args_are_relative_to_today():
    import datetime

    args = fallback._plan_args("u_x")
    today = datetime.date.today()
    assert args["user_id"] == "u_x"
    assert all(
        datetime.date.fromisoformat(d["due_at"][:10]) > today for d in args["deadlines"]
    )


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


def test_draft_commit_counts_from_calendar_diff():
    # The scheduling service nests counts under calendar_diff; reading
    # top-level keys reported 0 committed blocks for every successful commit.
    out = fallback._draft(
        "commit_schedule",
        {"calendar_diff": {"added": 8, "skipped_conflicts": 2}, "blocks": [{}] * 8},
    )
    assert "8 study blocks" in out and "2 overlapped" in out


def test_draft_commit_nothing_committed():
    out = fallback._draft(
        "commit_schedule",
        {"calendar_diff": {"added": 0, "skipped_conflicts": 5}, "blocks": []},
    )
    assert "couldn't commit" in out


def test_draft_log_transaction_reads_nested_row():
    out = fallback._draft(
        "log_transaction",
        {
            "transaction": {"amount_ngn": -4_500.0, "category": "food"},
            "new_balance": 262_500.0,
            "duplicate": False,
        },
    )
    assert "4,500 NGN" in out and "food" in out and "262,500" in out


def test_classify_plan_phrasing():
    assert fallback.classify("plan my study week") == "plan_study_week"
    assert fallback.classify("help me plan") == "plan_study_week"
    assert fallback.classify("how many deadlines do I have?") == "get_daily_brief"