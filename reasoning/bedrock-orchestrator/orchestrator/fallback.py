"""Rule-based intent router — the offline twin of the Bedrock orchestrator.

Used when Bedrock is unreachable (no AWS credentials / offline demo) so the
system still demonstrates end-to-end reasoning behaviour: intent detection ->
tool selection -> execution -> spoken answer. Every tool call still lands in
mcp_tool_calls, so the dashboard Agent Log reflects the whole trajectory.
"""

from __future__ import annotations

import os
import re

from orchestrator import executor

# Surfaced on the answer object and in the audit trail so a demo viewer can see
# that this reply was routed locally rather than by a live Bedrock call.
SIMULATED = "simulated: rule-based router (no Bedrock credentials)"


def _mock_mode() -> bool:
    """True when the deployment is explicitly running without Bedrock.

    Reads the env directly rather than atlas_common.config so this module stays
    importable from the CLI without the shared package on the path.
    """
    return os.getenv("ATLAS_MOCK_BEDROCK", "1").strip().lower() in {"1", "true", "yes", "on"}


# Ordered intent rules. Order matters: the first match wins, so specific
# planning/booking phrasings are checked before the broad "spend"/"brief"
# fallbacks that would otherwise swallow them.
_INTENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "get_daily_brief",
        (
            "morning brief", "daily brief", "good morning", "brief me",
            "today's brief", "how am i doing today", "catch me up", "status update",
            "what's on today", "whats on today",
        ),
    ),
    (
        "commit_schedule",
        (
            "commit", "book it", "confirm", "lock it in", "lock in", "add to schedule",
            "save these blocks", "add these blocks", "yes do it", "schedule it",
        ),
    ),
    (
        "plan_study_week",
        (
            "plan my week", "plan my study", "plan the week", "study plan", "study week",
            "study blocks", "when should i study", "make a plan", "plan my",
            "organize my week", "organise my week", "schedule my week", "help me plan",
            "revise my plan", "tweak my plan",
        ),
    ),
    (
        "log_transaction",
        (
            "spent", "spend of", "bought", "paid", "withdrew", "record", "log ",
            "add expense", "just made", "i got paid", "i was paid", "charge",
        ),
    ),
    (
        "assess_affordability",
        (
            "afford", "can i buy", "should i buy", "safe to spend", "buying",
            "can i spend", "worth buying",
        ),
    ),
    (
        "get_risk_snapshot",
        (
            "risk", "financially", "financial health", "my score", "risk score",
            "money stress", "how stretched",
        ),
    ),
)


def classify(utterance: str) -> str:
    """Map a natural-language utterance to exactly one ATLAS capability."""
    u = f" {utterance.lower().strip()} "

    for tool, keywords in _INTENTS:
        if any(k in u for k in keywords):
            return tool
    return "get_daily_brief"


_ARGS = {
    "assess_affordability": lambda u, uid: {"user_id": uid, "amount_ngn": _amount(u, 50_000), "category": _category(u)},
    "get_risk_snapshot": lambda u, uid: {"user_id": uid, "window": "30d"},
    "log_transaction": lambda u, uid: {
        "user_id": uid,
        "amount_ngn": abs(_amount(u, 3_500)) * (-1 if _is_spend(u) else 1),
        "category": _category(u),
    },
    "plan_study_week": lambda u, uid: _plan_args(uid),
    "commit_schedule": lambda u, uid: {"user_id": uid},
    "get_daily_brief": lambda u, uid: {"user_id": uid},
}


def _amount(u: str, default: float) -> float:
    # Prefer an explicitly unit-suffixed figure ("120k", "3 million"), then fall
    # back to a bare number ("spent 4500 on groceries"). A bare number alone used
    # to be ignored, so natural speech silently logged the placeholder default.
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(ngn|k|thousand|million)?\b", u, re.IGNORECASE)
    if not m:
        return default
    raw = m.group(1).replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return default
    unit = (m.group(2) or "").lower()
    if unit in ("k", "thousand"):
        val *= 1_000
    elif unit == "million":
        val *= 1_000_000
    return val


# Words that should land in a category without literally naming it. Without
# these, "groceries" and "laptop" both fell through to "general".
_CATEGORY_WORDS = {
    "food": ("grocer", "grocery", "groceries", "meal", "lunch", "dinner", "breakfast", "cafe", "restaurant", "snack"),
    "transport": ("uber", "bolt", "taxi", "bus", "fuel", "petrol", "fuel", "metro", "train ride", "airbnb"),
    "electronics": ("laptop", "phone", "headphone", "cable", "charger", "tv", "monitor", "keyboard"),
    "rent": ("house", "apartment", "flat", "hostel", "mortgage"),
    "salary": ("payroll", "wages", "stipend"),
    "entertainment": ("movie", "concert", "game", "subscription", "spotify", "netflix", "show"),
}


def _category(u: str) -> str:
    text = u.lower()
    for cat in ("food", "transport", "electronics", "fashion", "rent", "salary", "entertainment"):
        if re.search(rf"\b{cat}\w*\b", text):
            return cat
    for cat, words in _CATEGORY_WORDS.items():
        if any(w in text for w in words):
            return cat
    return "general"


# Signs drive the ledger, so the direction has to come from the words rather than
# from assuming every utterance is a spend. "I got paid 200k" is income.
_INCOME_WORDS = re.compile(
    r"\b(paid|salary|salaries|income|earned|received|deposit|bonus|refund|credited)\b",
    re.IGNORECASE,
)


def _is_spend(u: str) -> bool:
    return not _INCOME_WORDS.search(u)


def _plan_args(user_id: str) -> dict:
    import datetime

    def iso(d: str, h: int = 18) -> str:
        return f"{d}T{h:02d}:00:00"

    # Always relative to today. The window used to be pinned to hardcoded
    # September 2026 dates, so a plan created after that produced blocks in the
    # past.
    today = datetime.date.today()
    days = [(today + datetime.timedelta(days=i)).isoformat() for i in range(6)]
    return {
        "user_id": user_id,
        "deadlines": [
            {"title": "AI Systems Assignment", "due_at": iso(days[4], 23), "weight": 3},
            {"title": "Math Midterm", "due_at": iso(days[5], 12), "weight": 2},
        ],
        "available_hours": [
            {"date": d, "start_hour": 18, "end_hour": 21} for d in days
        ],
    }


def think(utterance: str, user_id: str = "u_demo") -> dict:
    tool = classify(utterance)
    args = _ARGS[tool](utterance, user_id)
    memory = executor.SessionMemory()
    result = executor.execute_tool(tool, args, memory)
    answer = _draft(tool, result)
    return {
        "front_door": "fallback",
        "simulated": _mock_mode(),
        "note": SIMULATED if _mock_mode() else None,
        "tool": tool,
        "utterance": utterance,
        "answer": answer,
        "tool_output": result,
    }


def _draft(tool: str, result: dict) -> str:
    if tool == "assess_affordability":
        v = result.get("verdict", "unknown")
        return (
            f"Here's my take: it's {v} to go ahead. "
            f"Your balance is {result.get('balance_ngn'):,.0f} NGN and your "
            f"risk would move from {result.get('baseline_risk_score', 0):.2f} to "
            f"{result.get('risk_score', 0):.2f}. {result.get('explanation', '')}"
        )
    if tool == "get_risk_snapshot":
        factors = result.get("factors") or []
        part = "; ".join(
            f"{f.get('label', f.get('feature', '?'))} {'raises' if f.get('direction') != 'lowers risk' else 'lowers'} risk"
            for f in factors[:4]
        ) or "no dominant factors."
        return (
            f"Your financial risk level is {result.get('score', 0):.2f} "
            f"({'elevated' if result.get('score', 0) >= 0.5 else 'low'}). "
            f"Top drivers: {part}."
        )
    if tool == "log_transaction":
        # The ledger nests the row under "transaction"; reading the top level
        # reported every recorded spend as 0 NGN.
        row = result.get("transaction") or result
        amount = row.get("amount_ngn", 0) or 0
        return (
            f"Noted — recorded {'income' if amount > 0 else 'spend'} of "
            f"{abs(amount):,.0f} NGN as {row.get('category', 'general')}. "
            f"Balance is now {result.get('new_balance', 0):,.0f} NGN."
            + (" It was a duplicate, so I didn't double-count it." if result.get("duplicate") else "")
        )
    if tool == "plan_study_week":
        blocks = result.get("proposed_blocks", [])
        if not blocks:
            return "I tried to draft a study plan but found no usable blocks."
        first = blocks[0]
        return (
            f"I've drafted a plan: {len(blocks)} blocks before your deadlines, "
            f"starting with {first['title']} on {first['start_at'][:10]} at "
            f"{first['start_at'][11:16]}. Say 'commit it' when you're happy."
        )
    if tool == "commit_schedule":
        # The scheduling service reports counts under calendar_diff; reading
        # top-level "committed"/"conflicts" keys reported 0 every time.
        diff = result.get("calendar_diff") or {}
        added = diff.get("added", len(result.get("blocks") or []))
        skipped = diff.get("skipped_conflicts", 0)
        if result.get("duplicate"):
            return "Those blocks were already committed, so I left them as they were."
        if not added:
            return "I couldn't commit those blocks — they all overlapped blocks you already have."
        msg = f"Locked in {added} study block{'s' if added != 1 else ''}."
        if skipped:
            msg += f" {skipped} overlapped your calendar and {'were' if skipped != 1 else 'was'} skipped."
        return msg
    if tool == "get_daily_brief":
        return (
            f"Good morning! Balance {result.get('balance_ngn', 0):,.0f} NGN, "
            f"risk {result.get('risk_score', 0):.2f}. "
            f"{sum(1 for b in result.get('today_blocks', []))} study sessions today, "
            f"and {len(result.get('next_deadlines', []))} deadline(s) ahead."
        )
    return "Done."