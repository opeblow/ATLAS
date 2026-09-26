"""Tool: plan_study_week — turn deadlines into spaced calendar blocks."""

from __future__ import annotations

from fastmcp import Context

from atlas_common.audit import timed_tool_call
from atlas_mcp_server import clients
from atlas_mcp_server.tools.identity import enforce_identity


def register(mcp: object) -> None:
    @mcp.tool()
    async def plan_study_week(
        user_id: str,
        deadlines: list[dict],
        available_hours: list[dict],
        ctx: Context | None = None,
    ) -> str:
        """Propose a study plan that turns deadlines into calendar blocks.

        Blocks are spread out across the availability before each due date
        instead of crammed onto the last day.

        Args:
            user_id: The ATLAS user identifier bound to this Alexa+ session.
            deadlines: [{title, due_at (ISO-8601), weight}] — weight scales effort.
            available_hours: [{date (YYYY-MM-DD), start_hour (0-23), end_hour (0-23)}].
        """
        enforce_identity(user_id)
        payload = {
            "user_id": user_id,
            "deadlines": deadlines,
            "available_hours": available_hours,
        }
        with timed_tool_call(user_id, "plan_study_week", payload):
            result = clients.scheduling_post("/plan/week", payload)

        blocks = result["proposed_blocks"]
        conflicts = result["conflicts"]
        if not blocks and not conflicts:
            return "Could not find any study windows for those deadlines."
        lines = [f"Proposed {len(blocks)} study session(s):"]
        for b in blocks:
            lines.append(f"- {b['title']}: {b['start_at'][:16]} to {b['end_at'][5:16]}")
        if conflicts:
            lines.append("Conflicts:")
            for c in conflicts:
                lines.append(f"- {c['reason']}")
        return "\n".join(lines)