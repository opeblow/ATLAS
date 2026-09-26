"""Tool: assess_affordability — "can I afford this?"

Answers against real balance + spending pattern: runs a *projected* risk probe
(never a write) through finance-service, which scores it with the PyTorch
model and returns a verdict + explanation.
"""

from __future__ import annotations

from fastmcp import Context

from atlas_common.audit import timed_tool_call
from atlas_mcp_server import clients
from atlas_mcp_server.tools.identity import enforce_identity


def register(mcp: object) -> None:
    @mcp.tool()
    async def assess_affordability(
        user_id: str,
        amount_ngn: float,
        category: str = "general",
        ctx: Context | None = None,
    ) -> str:
        """Check whether a purchase is safe given the user's balance and spending pattern.

        Args:
            user_id: The ATLAS user identifier bound to this Alexa+ session.
            amount_ngn: Purchase amount in NGN (positive).
            category: Optional spending category, e.g. 'electronics', 'food'.
        """
        enforce_identity(user_id)
        with timed_tool_call(
            user_id,
            "assess_affordability",
            {"amount_ngn": amount_ngn, "category": category},
        ):
            result = clients.finance_post(
                "/assess/affordability",
                {"user_id": user_id, "amount_ngn": amount_ngn, "category": category},
            )
        return (
            f"Verdict: {result['verdict']}. Risk score {result['risk_score']:.2f} "
            f"(baseline {result['baseline_risk_score']:.2f}). Balance: "
            f"{result['balance_ngn']:,.0f} NGN. {result['explanation']}"
        )