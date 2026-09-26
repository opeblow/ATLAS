"""Tool: get_risk_snapshot — explainable current risk state (Section 7.3)."""

from __future__ import annotations

from fastmcp import Context

from atlas_common.audit import timed_tool_call
from atlas_mcp_server import clients
from atlas_mcp_server.tools.identity import enforce_identity


def register(mcp: object) -> None:
    @mcp.tool()
    async def get_risk_snapshot(
        user_id: str,
        window: str = "30d",
        ctx: Context | None = None,
    ) -> str:
        """Return the user's current financial risk level with the top factors behind it.

        Args:
            user_id: The ATLAS user identifier bound to this Alexa+ session.
            window: Lookback window for the risk computation, '7d' or '30d'.
        """
        enforce_identity(user_id)
        with timed_tool_call(user_id, "get_risk_snapshot", {"window": window}):
            result = clients.finance_get(f"/users/{user_id}/risk", window=window)
        if result.get("stale"):
            note = " (based on the most recent snapshot we have — may be a few minutes old)"
        else:
            note = ""
        factors = _phrase_factors(result.get("factors", []))
        loss = "lower" if result["score"] < 0.5 else "elevated"
        return (
            f"Financial risk level: {result['score']:.2f} → {loss} risk{note}.\n{factors}"
        )


def _phrase_factors(factors: list[dict]) -> str:
    if not factors:
        return "No dominant factors detected."
    parts = []
    for f in factors:
        verb = "raises" if f["direction"] == "increases risk" else "lowers"
        parts.append(f"{f['label']} {verb} risk (impact {abs(f['impact']):.3f})")
    return "Top drivers: " + "; ".join(parts) + "."