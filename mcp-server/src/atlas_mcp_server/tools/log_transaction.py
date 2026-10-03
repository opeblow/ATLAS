"""Tool: log_transaction — record a spend/income event and re-check risk.

Idempotent via idempotency_key so a voice retry never double-logs (Section 8.5).
"""

from __future__ import annotations

from fastmcp import Context

from atlas_common.audit import timed_tool_call
from atlas_mcp_server import clients
from atlas_mcp_server.tools.identity import enforce_identity


def register(mcp: object) -> None:
    @mcp.tool()
    async def log_transaction(
        user_id: str,
        amount_ngn: float,
        category: str = "general",
        ts: str | None = None,
        idempotency_key: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Record a spend (negative) or income (positive) amount in the ledger.

        Recomputes the user's risk score and cached balance.

        Args:
            user_id: The ATLAS user identifier bound to this Alexa+ session.
            amount_ngn: Signed amount in NGN — negative for a spend, positive for income.
            category: Category label, e.g. 'food', 'transport', 'salary'.
            ts: Optional ISO-8601 timestamp; defaults to now.
            idempotency_key: Dedup key; a repeated call with the same key is a no-op.
        """
        enforce_identity(user_id)
        payload = {
            "user_id": user_id,
            "amount_ngn": amount_ngn,
            "category": category,
            "source": "alexa",
        }
        if ts:
            payload["ts"] = ts
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key

        with timed_tool_call(user_id, "log_transaction", payload):
            result = await clients.finance_post_async("/transactions", payload)

        if result.get("duplicate"):
            prefix = "Duplicate — already logged, nothing changed."
        else:
            prefix = "Logged."
        return (
            f"{prefix} New balance: {result['new_balance']:,.0f} NGN. "
            f"Updated risk score: {result['updated_risk_score']:.2f}."
        )