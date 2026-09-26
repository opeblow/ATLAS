"""Rule-based intent router — the offline twin of the Bedrock orchestrator.

Used when Bedrock is unreachable (no AWS credentials / offline demo) so the
system still demonstrates end-to-end reasoning behaviour: intent detection ->
tool selection -> execution -> spoken answer. Every tool call still lands in
mcp_tool_calls, so the dashboard Agent Log reflects the whole trajectory.
"""

from __future__ import annotations

import re

from orchestrator import executor


def classify(utterance: str) -> str:
    """Map a natural-language utterance to exactly one ATLAS capability."""
    u = utterance.lower()

    if any(k in u for k in ("morning brief", "daily brief", "good morning", "brief me", "today's brief")):
        return "get_daily_brief"
    if any(k in u for k in ("commit", "book", "confirm", "lock in", "add to schedule", "save these blocks")):
        return "commit_schedule"
    if any(k in u for k in ("plan my week", "study plan", "plan the week", "when should i study", "make a plan")):
        return "plan_study_week"
    if any(k in u for k in ("spent", "bought", "paid", "withdrew", "record", "log a", "add expense", "just made")):
        return "log_transaction"
    if any(k in u for k in ("risk", "financially", "how am i doing", "financial health", "my score")):
        return "get_risk_snapshot"
    if any(k in u for k in ("afford", "affordable", "can i buy", "should i buy", "safe to spend", "buying")):
        return "assess_affordability"
    return "get_daily_brief"


_ARGS = {
    "assess_affordability": lambda u, uid: {"user_id": uid, "amount_ngn": _amount(u, 50_000), "category": _category(u)},
    "get_risk_snapshot": lambda u, uid: {"user_id": uid, "window": "30d"},
    "log_transaction": lambda u, uid: {"user_id": uid, "amount_ngn": -_amount(u, 3_500), "category": _category(u)},
    "plan_study_week": lambda u, uid: _plan_args(),
    "commit_schedule": lambda u, uid: {"user_id": uid},
    "get_daily_brief": lambda u, uid: {"user_id": uid},
}


def _amount(u: str, default: float) -> float:
    m = re.search(r"([\d,]+)\s*(ngn|k|thousand|million)", u)
    if not m:
        return default
    val = float(m.group(1).replace(",", ""))
    unit = m.group(2)
    if unit in ("k", "thousand"):
        val *= 1000
    elif unit == "million":
        val *= 1_000_000
    return val


def _category(u: str) -> str:
    for cat in ("food", "transport", "electronics", "fashion", "rent", "salary", "entertainment"):
        if re.search(rf"\b{cat}\b", u):
            return cat
    return "general"


def _plan_args() -> dict:
    def iso(d: str, h: int = 18) -> str:
        return f"{d}T{h:02d}:00:00"

    days = [f"2026-09-{d:02d}" for d in range(24, 31)]
    import datetime

    today = datetime.date.today()
    offset = (today - datetime.date(2026, 9, 4)).days
    if not (0 <= offset < len(days)):
        import random

        random.seed(42)
        days = [(datetime.date.today() + datetime.timedelta(days=i)).isoformat() for i in range(6)]
    return {
        "user_id": "u_demo",
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
        return (
            f"Noted — recorded {'income' if result.get('amount_ngn', 0) > 0 else 'spend'} of "
            f"{abs(result.get('amount_ngn', 0)):,.0f} NGN as {result.get('category', 'general')}."
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
        added = result.get("committed", 0)
        conflicts = result.get("conflicts", [])
        msg = f"Locked in {added} study blocks."
        if conflicts:
            msg += f" {len(conflicts)} overlapped your calendar and were skipped."
        return msg
    if tool == "get_daily_brief":
        return (
            f"Good morning! Balance {result.get('balance_ngn', 0):,.0f} NGN, "
            f"risk {result.get('risk_score', 0):.2f}. "
            f"{sum(1 for b in result.get('today_blocks', []))} study sessions today, "
            f"and {len(result.get('next_deadlines', []))} deadline(s) ahead."
        )
    return "Done."