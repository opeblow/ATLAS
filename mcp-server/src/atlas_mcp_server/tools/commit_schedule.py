"""Tool: commit_schedule — persist a proposed plan (idempotent, overlap-safe)."""

from __future__ import annotations

from fastmcp import Context

from atlas_common.audit import timed_tool_call
from atlas_mcp_server import clients
from atlas_mcp_server.tools.identity import enforce_identity


def register(mcp: object) -> None:
    @mcp.tool()
    async def commit_schedule(
        user_id: str,
        blocks: list[dict],
        idempotency_key: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Commit proposed calendar blocks to the user's real schedule.

        Overlapping blocks are refused and reported; a repeated commit with the
        same idempotency_key is a no-op (voice retries never double-book).

        Args:
            user_id: The ATLAS user identifier bound to this Alexa+ session.
            blocks: [{title, start_at (ISO), end_at (ISO), deadline_id?}].
            idempotency_key: Dedup key for this commit operation.
        """
        enforce_identity(user_id)
        payload = {"user_id": user_id, "blocks": blocks}
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key

        with timed_tool_call(user_id, "commit_schedule", payload):
            result = await clients.scheduling_post_async("/schedule/commit", payload)

        diff = result.get("calendar_diff", {})
        conflicts = result.get("conflicts", [])
        commit_state = result.get("confirmation", "committed")
        if result.get("duplicate"):
            return "That plan was already committed — nothing changed."
        lines = [
            f"{commit_state}: {diff.get('added', 0)} block(s) added to your calendar."
        ]
        for c in conflicts:
            lines.append(
                f"- conflict: {c['block']} overlaps {c['overlaps']} "
                f"({c['overlap_start'][:16]} to {c['overlap_end'][11:16]}) — skipped."
            )
        return "\n".join(lines)