"""Tool: get_daily_brief — morning summary across money and time.

Composes the finance half and the scheduling half into one speakable brief.
"""

from __future__ import annotations

from datetime import date as DateCls

from fastmcp import Context

from atlas_common.audit import timed_tool_call
from atlas_mcp_server import clients
from atlas_mcp_server.tools.identity import enforce_identity


def register(mcp: object) -> None:
    @mcp.tool()
    async def get_daily_brief(
        user_id: str,
        date: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Morning brief: today's financial state + schedule + next deadlines.

        Args:
            user_id: The ATLAS user identifier bound to this Alexa+ session.
            date: Optional ISO date (YYYY-MM-DD); defaults to today.
        """
        enforce_identity(user_id)
        if date is None:
            date = DateCls.today().isoformat()

        with timed_tool_call(user_id, "get_daily_brief", {"date": date}):
            finance = clients.finance_get(f"/users/{user_id}/brief")
            time_brief = clients.scheduling_get(f"/users/{user_id}/brief/{date}")

        risk = finance["risk_score"]
        loss = "low" if risk < 0.4 else "elevated" if risk < 0.7 else "high"
        balance = finance["balance_ngn"]
        spend_7d = finance["spend_7d_ngn"]

        blocks = time_brief["today_blocks"]
        if blocks:
            schedule = ", ".join(
                f"{b['title']} at {b['start_at'][11:16]}" for b in blocks
            )
        else:
            schedule = "nothing committed for today"

        next_d = time_brief["next_deadlines"][:3]
        if next_d:
            led = "; ".join(f"{d['title']} due {d['due_at'][:10]}" for d in next_d)
        else:
            led = "no deadlines in the next two weeks"

        factors = finance.get("top_factors", [])
        factor_line = ""
        if factors:
            top = factors[:3]
            factor_line = " Top drivers: " + "; ".join(
                f"{f['label']} {f['direction']}" for f in top
            ) + "."

        stale = " (risk may be a few minutes old)" if finance.get("stale") else ""
        return (
            f"Good morning. Your balance is {balance:,.0f} NGN and your financial "
            f"risk level is {loss}: {risk:.2f}{stale}. "
            f"You spent {spend_7d:,.0f} NGN in the last 7 days.{factor_line} "
            f"Today's schedule: {schedule}. "
            f"Close deadlines: {led}."
        )